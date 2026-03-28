"""
D2S save file parser for Diablo 2 Resurrected.

Two header layouts are supported:

v96-99 (original D2R release):
  Offset 0x00  magic     uint32  0xAA55AA55
  Offset 0x04  version   uint32  96-99
  Offset 0x14  name      16s     null-padded latin-1
  Offset 0x24  status    uint8   bit 2=hardcore, bit 3=ever_died, bit 5=expansion
  Offset 0x28  class     uint8   0=Amazon … 6=Assassin
  Offset 0x2B  level     uint8

v100+ (D2R 2.x patches — name moved out of main header):
  Offset 0x00  magic     uint32  0xAA55AA55
  Offset 0x04  version   uint32  100+
  Offset 0x14  status    uint8   (same bit layout)
  Offset 0x18  class     uint8   0=Amazon … 7=Warlock
  Offset 0x1B  level     uint8
  Offset 0x12B name      16s     null-padded latin-1
"""
import struct
from dataclasses import dataclass, field, asdict
from pathlib import Path

MAGIC = 0xAA55AA55
MIN_VERSION = 96
MAX_VERSION = 200  # generous upper bound for future patches

# v96-99: name embedded at offset 20
_V99_FMT = "<IIIIi16sBBBBBBBB"
_V99_SIZE = struct.calcsize(_V99_FMT)  # 44 bytes

# v100+: name lives at 0x12B; class/level/status shifted 16 bytes earlier
_V100_FMT = "<IIIIiBBBBBBBB"
_V100_SIZE = struct.calcsize(_V100_FMT)  # 28 bytes
_V100_NAME_OFFSET = 0x12B  # 299
_V100_NAME_LEN = 16

CLASS_NAMES = {
    0: "Amazon",
    1: "Sorceress",
    2: "Necromancer",
    3: "Paladin",
    4: "Barbarian",
    5: "Druid",
    6: "Assassin",
    7: "Warlock",
}


_ACT_BOSS_OFFSETS = {1: 12, 2: 28, 3: 44, 4: 54, 5: 82}
_DIFF_NAMES = ["normal", "nightmare", "hell"]
_DIFF_BLOCK_SIZE = 94  # bytes per difficulty block within quest section


class D2SParseError(Exception):
    pass


@dataclass
class D2SCharacter:
    name: str
    class_name: str
    class_id: int
    level: int
    hardcore: bool
    ever_died: bool
    expansion: bool
    filename: str
    difficulty_active: int = 0  # 0=Normal, 1=Nightmare, 2=Hell
    acts_cleared: dict = field(default_factory=dict)  # e.g. {"cleared_act1_normal": True, ...}

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def parse_d2s(path: Path) -> D2SCharacter:
    data = path.read_bytes()

    if len(data) < 8:
        raise D2SParseError(f"{path.name}: file too small ({len(data)} bytes)")

    magic, version = struct.unpack_from("<II", data, 0)

    if magic != MAGIC:
        raise D2SParseError(
            f"{path.name}: bad magic 0x{magic:08X} (expected 0x{MAGIC:08X})"
        )

    if not (MIN_VERSION <= version <= MAX_VERSION):
        raise D2SParseError(
            f"{path.name}: unsupported version {version} (expected {MIN_VERSION}-{MAX_VERSION})"
        )

    if version >= 100:
        # D2R 2.x+ layout
        if len(data) < _V100_SIZE:
            raise D2SParseError(f"{path.name}: file too small for v100+ header")
        if len(data) < _V100_NAME_OFFSET + _V100_NAME_LEN:
            raise D2SParseError(f"{path.name}: file too small to read name at 0x12B")

        fields = struct.unpack_from(_V100_FMT, data, 0)
        # magic, version, unk1, unk2, unk3, status, unk, unk, unk, class, unk, unk, level
        _, _, _, _, _, status, _, _, _, class_id, _, _, level = fields

        name_bytes = data[_V100_NAME_OFFSET: _V100_NAME_OFFSET + _V100_NAME_LEN]
        name = name_bytes.decode("latin-1").split("\x00")[0]
    else:
        # v96-99 layout
        if len(data) < _V99_SIZE:
            raise D2SParseError(
                f"{path.name}: file too small ({len(data)} bytes, need {_V99_SIZE})"
            )

        fields = struct.unpack_from(_V99_FMT, data, 0)
        _, _, _, _, _, name_bytes, status, _, _, _, class_id, _, _, level = fields
        name = name_bytes.decode("latin-1").split("\x00")[0]

    hardcore = bool(status & (1 << 2))
    ever_died = bool(status & (1 << 3))
    expansion = bool(status & (1 << 5))

    # Difficulty / location block: 3 bytes at indices 0=Normal, 1=Nightmare, 2=Hell.
    # Bit 7 (0x80) of each byte = character is currently active at that difficulty.
    # Source: D2SLib-D2R (https://github.com/locbones/D2SLib-D2R) Locations.cs
    #
    # v96-99 layout: offset 0x00A8
    #   After header(16) + ActiveWeapon(4) + Name(16) + Status…Level(8) + Created(4) +
    #   LastPlayed(4) + Unk(4) + AssignedSkills[16](64) + MouseSkills(16) + Appearances(32)
    #
    # v100+ layout: offset 0x0098
    #   The 16-byte "Name (old)" field is absent from the header area (name moved to 0x12B),
    #   so every field from 0x14 onward shifts 16 bytes earlier: 0x00A8 - 0x10 = 0x0098
    difficulty_active = 0
    diff_offset = 0x0098 if version >= 100 else 0x00A8
    if len(data) >= diff_offset + 3:
        diff_data = data[diff_offset: diff_offset + 3]
        for i, b in enumerate(diff_data):
            if b & 0x80:
                difficulty_active = i

    # Quests section: "Woo!" header followed by 3 × QuestsDifficulty blocks.
    # Source: D2SLib-D2R Quests.cs
    #
    # Dynamic search for "Woo!" within the first 2048 bytes of the file.
    # The hardcoded offset (0x013B for v100+, 0x014B for v96-99) was unreliable
    # for some v100+ files (e.g. Tald.d2s has "Woo!" at 0x0193, not 0x013B).
    _WOO = b"Woo!"
    woo_pos = data.find(_WOO, 0, 2048)

    acts_cleared = _parse_quest_completions(data, woo_pos)

    return D2SCharacter(
        name=name,
        class_name=CLASS_NAMES.get(class_id, f"Unknown(class {class_id})"),
        class_id=class_id,
        level=level,
        hardcore=hardcore,
        ever_died=ever_died,
        expansion=expansion,
        filename=path.name,
        difficulty_active=difficulty_active,
        acts_cleared=acts_cleared,
    )


def read_map_seed(data: bytes) -> int:
    """Read the 4-byte little-endian map seed from raw .d2s bytes.

    Version-conditional offset:
      v100+  : 0x9B
      v96-99 : 0xAB
    """
    if len(data) < 8:
        raise D2SParseError("file too small to read version")
    _, version = struct.unpack_from("<II", data, 0)
    offset = 0x9B if version >= 100 else 0xAB
    if len(data) < offset + 4:
        raise D2SParseError(f"file too small to read seed at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def _parse_quest_completions(data: bytes, woo_pos: int) -> dict:
    """
    Parse act boss quest completions from the quest block.

    Returns a dict with all 15 cleared_actN_diffname keys set to bool.
    If "Woo!" is not found or the file is too short, all values are False.

    Each difficulty block is _DIFF_BLOCK_SIZE bytes.  The block for difficulty
    d starts at: woo_pos + 10 + d * _DIFF_BLOCK_SIZE

    Within each block, the word at _ACT_BOSS_OFFSETS[act_num] has bit 0
    (RewardGranted) set when the boss has been killed and the quest reward
    was granted.
    """
    result: dict = {}
    for diff_idx, diff_name in enumerate(_DIFF_NAMES):
        for act_num, boss_offset in _ACT_BOSS_OFFSETS.items():
            key = f"cleared_act{act_num}_{diff_name}"
            cleared = False
            if woo_pos >= 0:
                block_start = woo_pos + 10 + diff_idx * _DIFF_BLOCK_SIZE
                word_pos = block_start + boss_offset
                if word_pos + 2 <= len(data):
                    word = struct.unpack_from("<H", data, word_pos)[0]
                    cleared = bool(word & 0x0001)
            result[key] = cleared
    return result

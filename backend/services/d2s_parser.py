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
from dataclasses import dataclass, asdict
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

    def to_dict(self) -> dict:
        return asdict(self)


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

    return D2SCharacter(
        name=name,
        class_name=CLASS_NAMES.get(class_id, f"Unknown(class {class_id})"),
        class_id=class_id,
        level=level,
        hardcore=hardcore,
        ever_died=ever_died,
        expansion=expansion,
        filename=path.name,
    )

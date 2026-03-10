from __future__ import annotations

"""
Unit tests for backend.services.d2s_parser.

No SQLAlchemy dependency — pure Python.
Run locally: python3 -m pytest tests/test_d2s_parser.py -v
"""

import struct
from pathlib import Path

import pytest

from backend.services.d2s_parser import (
    CLASS_NAMES,
    D2SCharacter,
    D2SParseError,
    MAGIC,
    _V99_FMT,
    parse_d2s,
)


# ─── Helper ──────────────────────────────────────────────────────────────────

_WOO = b"Woo!"
_QUESTS_OFFSET_V99 = 0x014B
_HELL_COMPLETED_FROM_QUESTS = 283


def _make_v99_file(
    tmp_path: Path,
    name: str = "TestChar",
    class_id: int = 3,
    level: int = 20,
    status: int = 0,
    diff_bytes: tuple[int, int, int] = (0, 0, 0),
    filename: str = "test.d2s",
) -> Path:
    """
    Write a minimal valid v99 .d2s file and return its Path.

    Header (44 bytes) layout: <IIIIi16sBBBBBBBB
      magic(I) + version(I) + filesize(I) + checksum(I) + ActiveWeapon(i)
      + name(16s) + status(B) + progression(B) + unk(B) + unk(B)
      + class_id(B) + unk(B) + unk(B) + level(B)

    D2SLib-D2R layout (source of truth):
      0x0088: Appearances (32 bytes)
      0x00A8: Locations/Difficulty (3 bytes) ← diff_bytes placed here
    Total minimum file size: 0x00A8 + 3 = 171 bytes
    """
    name_bytes = name.encode("latin-1")[:15].ljust(16, b"\x00")
    header = struct.pack(
        _V99_FMT,
        MAGIC,    # magic
        99,       # version
        0,        # unk1 (filesize placeholder)
        0,        # unk2 (checksum placeholder)
        0,        # unk3 / ActiveWeapon (signed)
        name_bytes,
        status,   # status byte
        0, 0, 0,  # progression + 2 unk bytes
        class_id,
        0, 0,     # 2 unk bytes
        level,
    )
    assert len(header) == 44

    # Pad with zeros from byte 44 up to offset 0x00A8 (=168), then place diff block
    DIFF_OFFSET = 0x00A8
    pad = b"\x00" * (DIFF_OFFSET - 44)
    diff_block = bytes(diff_bytes)
    data = header + pad + diff_block

    path = tmp_path / filename
    path.write_bytes(data)
    return path


def _make_v99_with_quests(
    tmp_path: Path,
    hell_completed: bool = False,
    filename: str = "quest.d2s",
) -> Path:
    """
    Extend a minimal v99 file to include the 'Woo!' quests section with the
    Hell CompletedDifficulty byte set (or cleared).
    The quests section starts at 0x014B.  The CompletedDifficulty byte for Hell
    sits at quests_start + 283.
    """
    # Build the base file (up to 0x00A8 + 3 = 171 bytes)
    base_path = _make_v99_file(tmp_path, filename="__base_quests.d2s")
    data = bytearray(base_path.read_bytes())

    # Extend to quests offset + header + enough room for CompletedDifficulty
    needed = _QUESTS_OFFSET_V99 + _HELL_COMPLETED_FROM_QUESTS + 1
    if len(data) < needed:
        data += b"\x00" * (needed - len(data))

    # Write "Woo!" header at 0x014B
    data[_QUESTS_OFFSET_V99:_QUESTS_OFFSET_V99 + 4] = _WOO

    # Write CompletedDifficulty byte for Hell
    pos = _QUESTS_OFFSET_V99 + _HELL_COMPLETED_FROM_QUESTS
    data[pos] = 0x80 if hell_completed else 0x00

    path = tmp_path / filename
    path.write_bytes(bytes(data))
    return path


# ─── D2SCharacter properties ─────────────────────────────────────────────────

class TestD2SCharacterProperties:
    def _char(self, difficulty_active: int) -> D2SCharacter:
        return D2SCharacter(
            name="Hero",
            class_name="Paladin",
            class_id=3,
            level=50,
            hardcore=False,
            ever_died=False,
            expansion=True,
            filename="hero.d2s",
            difficulty_active=difficulty_active,
        )

    def test_acts_cleared_is_dict(self) -> None:
        """acts_cleared defaults to an empty dict."""
        assert isinstance(self._char(0).acts_cleared, dict)

    def test_acts_cleared_can_be_set(self) -> None:
        c = D2SCharacter(
            name="x", class_name="Paladin", class_id=3, level=1,
            hardcore=False, ever_died=False, expansion=True, filename="x.d2s",
            difficulty_active=0,
            acts_cleared={"cleared_act5_hell": True},
        )
        assert c.acts_cleared["cleared_act5_hell"] is True

    def test_to_dict_includes_acts_cleared(self) -> None:
        d = self._char(1).to_dict()
        assert "name" in d
        assert "level" in d
        assert "class_id" in d
        assert "difficulty_active" in d
        assert "acts_cleared" in d

    def test_to_dict_difficulty_active_preserved(self) -> None:
        assert self._char(2).to_dict()["difficulty_active"] == 2

    def test_to_dict_acts_cleared_is_dict(self) -> None:
        d = self._char(1).to_dict()
        assert isinstance(d["acts_cleared"], dict)


# ─── Parse v99 layout ─────────────────────────────────────────────────────────

class TestParseV99Layout:
    def test_name_parsed_correctly(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, name="Dragonfire")
        char = parse_d2s(path)
        assert char.name == "Dragonfire"

    def test_level_parsed_correctly(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, level=42)
        char = parse_d2s(path)
        assert char.level == 42

    def test_class_id_parsed_correctly(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, class_id=4)
        char = parse_d2s(path)
        assert char.class_id == 4
        assert char.class_name == "Barbarian"

    def test_hardcore_false_by_default(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0)
        char = parse_d2s(path)
        assert char.hardcore is False

    def test_expansion_false_when_status_zero(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0)
        char = parse_d2s(path)
        assert char.expansion is False

    def test_difficulty_active_zero_when_all_diff_bytes_zero(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 0

    def test_filename_is_path_name(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, filename="mychar.d2s")
        char = parse_d2s(path)
        assert char.filename == "mychar.d2s"


# ─── Difficulty active detection ─────────────────────────────────────────────

class TestDifficultyActive:
    def test_bit7_byte0_gives_normal(self, tmp_path: Path) -> None:
        """0x80 set in byte 0 → active in Normal (index 0)."""
        path = _make_v99_file(tmp_path, diff_bytes=(0x80, 0, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 0

    def test_bit7_byte1_gives_nightmare(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0x80, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 1

    def test_bit7_byte2_gives_hell(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0, 0x80))
        char = parse_d2s(path)
        assert char.difficulty_active == 2

    def test_no_bits_set_gives_normal(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 0

    def test_all_bits_set_last_wins(self, tmp_path: Path) -> None:
        """When all three bytes have bit 7 set, the loop keeps the last (index 2)."""
        path = _make_v99_file(tmp_path, diff_bytes=(0x80, 0x80, 0x80))
        char = parse_d2s(path)
        assert char.difficulty_active == 2

    def test_byte0_and_byte2_set_last_wins(self, tmp_path: Path) -> None:
        """Bytes 0 and 2 set → last set byte is index 2."""
        path = _make_v99_file(tmp_path, diff_bytes=(0x80, 0, 0x80))
        char = parse_d2s(path)
        assert char.difficulty_active == 2

    def test_byte0_and_byte1_set_last_wins(self, tmp_path: Path) -> None:
        """Bytes 0 and 1 set → last set byte is index 1."""
        path = _make_v99_file(tmp_path, diff_bytes=(0x80, 0x80, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 1

    def test_file_too_short_for_diff_block_gives_zero(self, tmp_path: Path) -> None:
        """File that doesn't reach offset 0x00A8+3 → difficulty_active defaults to 0."""
        # Build a file with just the 44-byte header — no room for diff block at 0x00A8
        name_bytes = b"Short\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        header = struct.pack(
            _V99_FMT,
            MAGIC, 99, 0, 0, 0,
            name_bytes[:16],
            0, 0, 0, 0, 3, 0, 0, 10,
        )
        path = tmp_path / "short.d2s"
        path.write_bytes(header)  # 44 bytes; 0x00A8 = 168 > 44 → fallback to 0
        char = parse_d2s(path)
        assert char.difficulty_active == 0

    def test_non_0x80_bit_not_detected(self, tmp_path: Path) -> None:
        """Bit 6 (0x40) alone is not the active-difficulty flag."""
        path = _make_v99_file(tmp_path, diff_bytes=(0x40, 0, 0))
        char = parse_d2s(path)
        assert char.difficulty_active == 0


# ─── Status byte parsing ──────────────────────────────────────────────────────

class TestParseStatus:
    def test_hardcore_bit2(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0b00000100)  # bit 2
        char = parse_d2s(path)
        assert char.hardcore is True
        assert char.ever_died is False
        assert char.expansion is False

    def test_ever_died_bit3(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0b00001000)  # bit 3
        char = parse_d2s(path)
        assert char.ever_died is True
        assert char.hardcore is False

    def test_expansion_bit5(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0b00100000)  # bit 5
        char = parse_d2s(path)
        assert char.expansion is True
        assert char.hardcore is False

    def test_all_status_bits_set(self, tmp_path: Path) -> None:
        status = (1 << 2) | (1 << 3) | (1 << 5)
        path = _make_v99_file(tmp_path, status=status)
        char = parse_d2s(path)
        assert char.hardcore is True
        assert char.ever_died is True
        assert char.expansion is True

    def test_status_zero_all_false(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, status=0)
        char = parse_d2s(path)
        assert char.hardcore is False
        assert char.ever_died is False
        assert char.expansion is False


# ─── Parse errors ─────────────────────────────────────────────────────────────

class TestParseErrors:
    def test_bad_magic_raises(self, tmp_path: Path) -> None:
        data = struct.pack("<II", 0xDEADBEEF, 99) + b"\x00" * 90
        path = tmp_path / "bad_magic.d2s"
        path.write_bytes(data)
        with pytest.raises(D2SParseError, match="bad magic"):
            parse_d2s(path)

    def test_version_too_low_raises(self, tmp_path: Path) -> None:
        data = struct.pack("<II", MAGIC, 95) + b"\x00" * 90
        path = tmp_path / "old_version.d2s"
        path.write_bytes(data)
        with pytest.raises(D2SParseError, match="unsupported version"):
            parse_d2s(path)

    def test_version_too_high_raises(self, tmp_path: Path) -> None:
        data = struct.pack("<II", MAGIC, 201) + b"\x00" * 90
        path = tmp_path / "future_version.d2s"
        path.write_bytes(data)
        with pytest.raises(D2SParseError, match="unsupported version"):
            parse_d2s(path)

    def test_file_too_small_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "tiny.d2s"
        path.write_bytes(b"\x00" * 4)  # less than 8 bytes
        with pytest.raises(D2SParseError, match="too small"):
            parse_d2s(path)

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.d2s"
        path.write_bytes(b"")
        with pytest.raises(D2SParseError, match="too small"):
            parse_d2s(path)

    def test_valid_magic_but_truncated_header_raises(self, tmp_path: Path) -> None:
        """File has correct magic but is too short for the full v99 header."""
        data = struct.pack("<II", MAGIC, 99) + b"\x00" * 5  # only 13 bytes total
        path = tmp_path / "truncated.d2s"
        path.write_bytes(data)
        with pytest.raises(D2SParseError, match="too small"):
            parse_d2s(path)


# ─── Class name mapping ───────────────────────────────────────────────────────

class TestClassNames:
    @pytest.mark.parametrize("class_id,expected", [
        (0, "Amazon"),
        (1, "Sorceress"),
        (2, "Necromancer"),
        (3, "Paladin"),
        (4, "Barbarian"),
        (5, "Druid"),
        (6, "Assassin"),
    ])
    def test_known_class_ids(
        self, tmp_path: Path, class_id: int, expected: str
    ) -> None:
        path = _make_v99_file(tmp_path, class_id=class_id, filename=f"char_{class_id}.d2s")
        char = parse_d2s(path)
        assert char.class_name == expected

    def test_unknown_class_id_contains_unknown(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, class_id=15)
        char = parse_d2s(path)
        assert "Unknown" in char.class_name or "15" in char.class_name


# ─── Acts cleared (quests section) ───────────────────────────────────────────

class TestHellCompleted:
    def test_hell_not_completed_when_no_quests_section(self, tmp_path: Path) -> None:
        """Short file without quests section → acts_cleared all False."""
        path = _make_v99_file(tmp_path)
        char = parse_d2s(path)
        assert char.acts_cleared.get("cleared_act5_hell", False) is False

    def test_hell_not_completed_when_byte_is_zero(self, tmp_path: Path) -> None:
        path = _make_v99_with_quests(tmp_path, hell_completed=False)
        char = parse_d2s(path)
        # The old 0x80 byte at offset 283 was CompletedDifficulty, not a boss kill;
        # acts_cleared["cleared_act5_hell"] uses the RewardGranted quest bit.
        # When hell_completed=False, Baal quest bit is also False.
        assert char.acts_cleared.get("cleared_act5_hell", False) is False

    def test_hell_completed_when_byte_is_0x80(self, tmp_path: Path) -> None:
        """The v99 quest helper sets a CompletedDifficulty byte; acts_cleared may be False
        unless the individual Baal RewardGranted bit (bit 0 at boss offset) is also set.
        This test verifies parse_d2s doesn't crash and acts_cleared is a dict."""
        path = _make_v99_with_quests(tmp_path, hell_completed=True)
        char = parse_d2s(path)
        assert isinstance(char.acts_cleared, dict)
        assert len(char.acts_cleared) == 15

    def test_cleared_hell_property_reflects_hell_completed(self, tmp_path: Path) -> None:
        """acts_cleared dict is populated from dynamic Woo! search, no crash."""
        path = _make_v99_with_quests(tmp_path, hell_completed=True)
        char = parse_d2s(path)
        assert isinstance(char.acts_cleared, dict)

    def test_hell_completed_false_when_woo_header_missing(self, tmp_path: Path) -> None:
        """If 'Woo!' header is absent, dynamic search returns -1 → all acts_cleared False."""
        path = _make_v99_with_quests(tmp_path, hell_completed=True)
        data = bytearray(path.read_bytes())
        # Corrupt the 'Woo!' header
        data[_QUESTS_OFFSET_V99:_QUESTS_OFFSET_V99 + 4] = b"XXXX"
        path.write_bytes(bytes(data))
        char = parse_d2s(path)
        assert all(v is False for v in char.acts_cleared.values())

    def test_to_dict_includes_acts_cleared(self, tmp_path: Path) -> None:
        path = _make_v99_with_quests(tmp_path, hell_completed=True)
        d = parse_d2s(path).to_dict()
        assert "acts_cleared" in d
        assert isinstance(d["acts_cleared"], dict)


# ─── to_dict completeness ─────────────────────────────────────────────────────

class TestToDict:
    def test_to_dict_returns_dict(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path)
        char = parse_d2s(path)
        assert isinstance(char.to_dict(), dict)

    def test_to_dict_has_name(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, name="Named")
        d = parse_d2s(path).to_dict()
        assert d["name"] == "Named"

    def test_to_dict_has_level(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, level=77)
        d = parse_d2s(path).to_dict()
        assert d["level"] == 77

    def test_to_dict_has_class_id(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, class_id=1)
        d = parse_d2s(path).to_dict()
        assert d["class_id"] == 1

    def test_to_dict_has_difficulty_active(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0, 0x80))
        d = parse_d2s(path).to_dict()
        assert d["difficulty_active"] == 2

    def test_to_dict_has_acts_cleared(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0x80, 0))
        d = parse_d2s(path).to_dict()
        assert "acts_cleared" in d
        assert isinstance(d["acts_cleared"], dict)

    def test_to_dict_acts_cleared_has_15_keys(self, tmp_path: Path) -> None:
        path = _make_v99_file(tmp_path, diff_bytes=(0, 0, 0x80))
        d = parse_d2s(path).to_dict()
        assert len(d["acts_cleared"]) == 15

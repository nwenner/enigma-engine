from __future__ import annotations

"""
Tests for quest completion parsing in backend.services.d2s_parser.

Integration tests run against the real Tald.d2s fixture.
Unit tests use a synthetic _make_quest_file() helper.

Run (no Docker needed — pure Python):
  python3 -m pytest tests/quest_parsing/test_quest_parsing.py -v
"""

import struct
from pathlib import Path

import pytest

from backend.services.d2s_parser import (
    MAGIC,
    _ACT_BOSS_OFFSETS,
    _DIFF_BLOCK_SIZE,
    _DIFF_NAMES,
    _parse_quest_completions,
    parse_d2s,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TALD = FIXTURE_DIR / "Tald.d2s"

# "Woo!" is at 0x0193 in Tald.d2s (v105), NOT at the old hardcoded 0x013B.
_OLD_V100_HARDCODED_OFFSET = 0x013B
_TALD_WOO_OFFSET = 0x0193

_WOO = b"Woo!"


# ─── Integration tests against Tald.d2s ──────────────────────────────────────


class TestTaldFixture:
    """
    Tald.d2s (v105, 3512 bytes):
      Normal: all 5 bosses cleared
      Nightmare: acts 1-4 cleared, Baal = False
      Hell: none cleared
    """

    def test_fixture_exists(self) -> None:
        assert TALD.exists(), f"Fixture not found: {TALD}"

    def test_woo_not_at_hardcoded_v100_offset(self) -> None:
        """The old hardcoded offset is wrong for this file."""
        data = TALD.read_bytes()
        assert data[_OLD_V100_HARDCODED_OFFSET : _OLD_V100_HARDCODED_OFFSET + 4] != _WOO

    def test_woo_found_dynamically(self) -> None:
        """Dynamic search correctly locates 'Woo!' at 0x0193."""
        data = TALD.read_bytes()
        pos = data.find(_WOO, 0, 2048)
        assert pos == _TALD_WOO_OFFSET

    def test_normal_all_bosses_cleared(self) -> None:
        char = parse_d2s(TALD)
        for act in range(1, 6):
            key = f"cleared_act{act}_normal"
            assert char.acts_cleared[key] is True, f"{key} should be True"

    def test_nightmare_acts_1_to_4_cleared(self) -> None:
        char = parse_d2s(TALD)
        for act in range(1, 5):
            key = f"cleared_act{act}_nightmare"
            assert char.acts_cleared[key] is True, f"{key} should be True"

    def test_nightmare_act5_not_cleared(self) -> None:
        char = parse_d2s(TALD)
        assert char.acts_cleared["cleared_act5_nightmare"] is False

    def test_hell_all_false(self) -> None:
        char = parse_d2s(TALD)
        for act in range(1, 6):
            key = f"cleared_act{act}_hell"
            assert char.acts_cleared[key] is False, f"{key} should be False"

    def test_parse_d2s_acts_cleared_populated(self) -> None:
        """Full parse_d2s() round-trip: acts_cleared dict has all 15 keys."""
        char = parse_d2s(TALD)
        assert isinstance(char.acts_cleared, dict)
        assert len(char.acts_cleared) == 15
        for diff in _DIFF_NAMES:
            for act in range(1, 6):
                assert f"cleared_act{act}_{diff}" in char.acts_cleared


# ─── Synthetic unit tests ─────────────────────────────────────────────────────

# v100+ header layout (28 bytes): <IIIIiBBBBBBBB
_V100_FMT = "<IIIIiBBBBBBBB"
_V100_HEADER_SIZE = struct.calcsize(_V100_FMT)  # 28

# Locations of the difficulty active block (v100+)
_DIFF_ACTIVE_OFFSET = 0x0098

# Name slot at 0x12B (16 bytes)
_V100_NAME_OFFSET = 0x12B
_V100_NAME_LEN = 16

# Minimum file size to hold all three quest blocks
# We'll place "Woo!" at 0x0193 (same as Tald) and need 10 + 3*94 = 292 bytes after it
_WOO_AT = 0x0193
_MIN_LEN = _WOO_AT + 10 + 3 * _DIFF_BLOCK_SIZE + 2  # +2 for last word read


def _make_quest_file(
    boss_bits: dict | None = None,
    include_woo: bool = True,
    truncate_after_woo: bool = False,
) -> bytes:
    """
    Build a minimal syntactically-valid v105 .d2s binary with quest data.

    boss_bits: dict mapping (act_num, diff_idx) → bool
      where act_num in 1-5, diff_idx in 0=Normal/1=Nightmare/2=Hell
    include_woo: if False, omit the "Woo!" marker entirely
    truncate_after_woo: if True, file ends right after "Woo!" (4 bytes)
    """
    if boss_bits is None:
        boss_bits = {}

    size = _MIN_LEN if not truncate_after_woo else _WOO_AT + 6
    data = bytearray(size)

    # Magic + version
    struct.pack_into("<I", data, 0, MAGIC)
    struct.pack_into("<I", data, 4, 105)  # version 105 (v100+)

    # File size field (offset 8)
    struct.pack_into("<I", data, 8, size)

    # Status byte at offset 0x14 (v100+): bit 5 = expansion
    data[0x14] = 1 << 5

    # Class id at offset 0x18: 3 = Paladin
    data[0x18] = 3

    # Level at offset 0x1B
    data[0x1B] = 1

    # Name at 0x12B
    if size > _V100_NAME_OFFSET + _V100_NAME_LEN:
        name_bytes = b"Synthetic\x00\x00\x00\x00\x00\x00\x00"
        data[_V100_NAME_OFFSET : _V100_NAME_OFFSET + _V100_NAME_LEN] = name_bytes

    # Difficulty active block (3 bytes at 0x0098)
    if size > _DIFF_ACTIVE_OFFSET + 3:
        data[_DIFF_ACTIVE_OFFSET] = 0x80  # active in Normal

    if not include_woo:
        return bytes(data)

    # Write "Woo!" marker
    data[_WOO_AT : _WOO_AT + 4] = _WOO

    if truncate_after_woo:
        return bytes(data[: _WOO_AT + 6])

    # Write quest version bytes (2 bytes after "Woo!" = header start)
    # Then set boss bits in diff blocks
    for (act_num, diff_idx), cleared in boss_bits.items():
        if not cleared:
            continue
        block_start = _WOO_AT + 10 + diff_idx * _DIFF_BLOCK_SIZE
        word_pos = block_start + _ACT_BOSS_OFFSETS[act_num]
        struct.pack_into("<H", data, word_pos, 0x0001)  # RewardGranted bit

    return bytes(data)


class TestSyntheticQuestParsing:
    def test_single_boss_cleared(self) -> None:
        """Set only act 3 Normal (Mephisto), all others False."""
        data = _make_quest_file(boss_bits={(3, 0): True})
        woo_pos = data.find(_WOO, 0, 2048)
        result = _parse_quest_completions(data, woo_pos)
        assert result["cleared_act3_normal"] is True
        # others are False
        for key, val in result.items():
            if key != "cleared_act3_normal":
                assert val is False, f"Expected {key}=False, got {val}"

    def test_act_boss_offsets_independent(self) -> None:
        """Setting act4_normal does not affect act4_nightmare."""
        data = _make_quest_file(boss_bits={(4, 0): True})
        woo_pos = data.find(_WOO, 0, 2048)
        result = _parse_quest_completions(data, woo_pos)
        assert result["cleared_act4_normal"] is True
        assert result["cleared_act4_nightmare"] is False
        assert result["cleared_act4_hell"] is False

    def test_woo_missing_returns_all_false(self) -> None:
        """No 'Woo!' in file → all False (woo_pos = -1)."""
        data = _make_quest_file(include_woo=False)
        result = _parse_quest_completions(data, -1)
        assert all(v is False for v in result.values())
        assert len(result) == 15

    def test_file_too_short_for_quest_block(self) -> None:
        """File truncated right after 'Woo!' → all False (no crash)."""
        data = _make_quest_file(truncate_after_woo=True)
        woo_pos = data.find(_WOO, 0, 2048)
        assert woo_pos >= 0
        result = _parse_quest_completions(data, woo_pos)
        assert all(v is False for v in result.values())

    def test_all_15_combos(self) -> None:
        """Set all 15 boss bits, verify all True."""
        bits = {}
        for act in range(1, 6):
            for diff in range(3):
                bits[(act, diff)] = True
        data = _make_quest_file(boss_bits=bits)
        woo_pos = data.find(_WOO, 0, 2048)
        result = _parse_quest_completions(data, woo_pos)
        assert len(result) == 15
        assert all(v is True for v in result.values()), result

    def test_reward_granted_bit_only(self) -> None:
        """Only bit 0 (RewardGranted) matters; other bits in the word are ignored."""
        # Build a file where the act1 normal word has bits 1,2,3 set but NOT bit 0
        data = bytearray(_make_quest_file())
        block_start = _WOO_AT + 10 + 0 * _DIFF_BLOCK_SIZE
        word_pos = block_start + _ACT_BOSS_OFFSETS[1]
        # Set bits 1-7 but not bit 0
        struct.pack_into("<H", data, word_pos, 0x00FE)
        result = _parse_quest_completions(bytes(data), _WOO_AT)
        assert result["cleared_act1_normal"] is False

    def test_reward_granted_bit_set(self) -> None:
        """Bit 0 set → cleared."""
        data = bytearray(_make_quest_file())
        block_start = _WOO_AT + 10 + 0 * _DIFF_BLOCK_SIZE
        word_pos = block_start + _ACT_BOSS_OFFSETS[1]
        struct.pack_into("<H", data, word_pos, 0x0001)
        result = _parse_quest_completions(bytes(data), _WOO_AT)
        assert result["cleared_act1_normal"] is True

from __future__ import annotations

"""
Unit tests for the pure-Python helpers in backend.routers.seasons:
  _hex_to_bytes, _ms_out, _ach_out

Needs SQLAlchemy — run inside Docker:
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.routers.seasons import _hex_to_bytes, _ms_out, _ach_out


# ─── _hex_to_bytes ────────────────────────────────────────────────────────────

class TestHexToBytes:
    def test_space_separated_hex(self) -> None:
        assert _hex_to_bytes("10 0f 00 00") == bytes([0x10, 0x0F, 0x00, 0x00])

    def test_continuous_no_spaces(self) -> None:
        assert _hex_to_bytes("100f0000") == bytes([0x10, 0x0F, 0x00, 0x00])

    def test_mixed_whitespace(self) -> None:
        assert _hex_to_bytes("10\n0f\t00 00") == bytes([0x10, 0x0F, 0x00, 0x00])

    def test_empty_string_returns_empty_bytes(self) -> None:
        assert _hex_to_bytes("") == b""

    def test_whitespace_only_returns_empty_bytes(self) -> None:
        assert _hex_to_bytes("   \t\n  ") == b""

    def test_invalid_hex_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _hex_to_bytes("ZZ")

    def test_odd_length_continuous_raises_value_error(self) -> None:
        """'0f0' without spaces = 3 hex chars = odd length → ValueError."""
        with pytest.raises(ValueError):
            _hex_to_bytes("0f0")

    def test_single_byte(self) -> None:
        assert _hex_to_bytes("ff") == bytes([0xFF])

    def test_uppercase_hex(self) -> None:
        assert _hex_to_bytes("10 0F AB CD") == bytes([0x10, 0x0F, 0xAB, 0xCD])

    def test_longer_sequence(self) -> None:
        result = _hex_to_bytes("de ad be ef ca fe")
        assert result == bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE])


# ─── _ms_out ─────────────────────────────────────────────────────────────────

def _make_milestone(
    ms_id: int = 1,
    season_id: int = 10,
    name: str = "Reach Level 30",
    milestone_type: str = "level",
    level_target: int | None = 30,
    reward_item_bytes: bytes | None = b"\x10\x00\x00\x00",
    reward_item_name: str | None = "Horadric Cube",
    reward_item_code: str | None = "box ",
    time_limit_hours: int | None = None,
    sort_order: int = 0,
) -> MagicMock:
    ms = MagicMock()
    ms.id = ms_id
    ms.season_id = season_id
    ms.name = name
    ms.milestone_type = milestone_type
    ms.level_target = level_target
    ms.reward_item_bytes = reward_item_bytes
    ms.reward_item_name = reward_item_name
    ms.reward_item_code = reward_item_code
    ms.time_limit_hours = time_limit_hours
    ms.sort_order = sort_order
    return ms


class TestMsOut:
    def test_id_passed_through(self) -> None:
        out = _ms_out(_make_milestone(ms_id=42))
        assert out.id == 42

    def test_season_id_passed_through(self) -> None:
        out = _ms_out(_make_milestone(season_id=7))
        assert out.season_id == 7

    def test_name_passed_through(self) -> None:
        out = _ms_out(_make_milestone(name="Clear Normal"))
        assert out.name == "Clear Normal"

    def test_milestone_type_passed_through(self) -> None:
        out = _ms_out(_make_milestone(milestone_type="cleared_normal"))
        assert out.milestone_type == "cleared_normal"

    def test_level_target_preserved_as_int(self) -> None:
        out = _ms_out(_make_milestone(level_target=50))
        assert out.level_target == 50

    def test_level_target_none_preserved(self) -> None:
        out = _ms_out(_make_milestone(level_target=None))
        assert out.level_target is None

    def test_has_reward_true_when_bytes_present(self) -> None:
        out = _ms_out(_make_milestone(reward_item_bytes=b"\x10\x00"))
        assert out.has_reward is True

    def test_has_reward_false_when_bytes_none(self) -> None:
        out = _ms_out(_make_milestone(reward_item_bytes=None))
        assert out.has_reward is False

    def test_reward_item_name_passed_through(self) -> None:
        out = _ms_out(_make_milestone(reward_item_name="Stones of Jordan"))
        assert out.reward_item_name == "Stones of Jordan"

    def test_reward_item_name_none(self) -> None:
        out = _ms_out(_make_milestone(reward_item_name=None))
        assert out.reward_item_name is None

    def test_reward_item_code_passed_through(self) -> None:
        out = _ms_out(_make_milestone(reward_item_code="rin "))
        assert out.reward_item_code == "rin "

    def test_reward_item_code_none(self) -> None:
        out = _ms_out(_make_milestone(reward_item_code=None))
        assert out.reward_item_code is None

    def test_sort_order_passed_through(self) -> None:
        out = _ms_out(_make_milestone(sort_order=5))
        assert out.sort_order == 5

    def test_time_limit_hours_none_by_default(self) -> None:
        out = _ms_out(_make_milestone(time_limit_hours=None))
        assert out.time_limit_hours is None

    def test_time_limit_hours_passed_through(self) -> None:
        out = _ms_out(_make_milestone(time_limit_hours=48))
        assert out.time_limit_hours == 48

    def test_is_expired_false_when_no_time_limit(self) -> None:
        out = _ms_out(_make_milestone(time_limit_hours=None))
        assert out.is_expired is False

    def test_is_expired_false_when_no_season_started_at(self) -> None:
        out = _ms_out(_make_milestone(time_limit_hours=24), season_started_at=None)
        assert out.is_expired is False

    def test_is_expired_false_when_window_open(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=1)
        out = _ms_out(_make_milestone(time_limit_hours=48), season_started_at=started)
        assert out.is_expired is False

    def test_is_expired_true_when_window_closed(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=73)
        out = _ms_out(_make_milestone(time_limit_hours=48), season_started_at=started)
        assert out.is_expired is True

    def test_cleared_hell_milestone_type_passed_through(self) -> None:
        out = _ms_out(_make_milestone(milestone_type="cleared_hell"))
        assert out.milestone_type == "cleared_hell"


# ─── _ach_out ─────────────────────────────────────────────────────────────────

def _make_achievement(
    ach_id: int = 1,
    season_id: int = 10,
    milestone_id: int = 2,
    character_name: str = "Frostblaze",
    character_class: str = "Sorceress",
    character_level: int = 30,
    achieved_at: datetime | None = None,
    claimed_at: datetime | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = ach_id
    a.season_id = season_id
    a.milestone_id = milestone_id
    a.character_name = character_name
    a.character_class = character_class
    a.character_level = character_level
    a.achieved_at = achieved_at or datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    a.claimed_at = claimed_at
    return a


class TestAchOut:
    def test_id_passed_through(self) -> None:
        out = _ach_out(_make_achievement(ach_id=99))
        assert out.id == 99

    def test_season_id_passed_through(self) -> None:
        out = _ach_out(_make_achievement(season_id=5))
        assert out.season_id == 5

    def test_milestone_id_passed_through(self) -> None:
        out = _ach_out(_make_achievement(milestone_id=3))
        assert out.milestone_id == 3

    def test_character_name_passed_through(self) -> None:
        out = _ach_out(_make_achievement(character_name="Iceblast"))
        assert out.character_name == "Iceblast"

    def test_character_class_passed_through(self) -> None:
        out = _ach_out(_make_achievement(character_class="Necromancer"))
        assert out.character_class == "Necromancer"

    def test_character_level_passed_through(self) -> None:
        out = _ach_out(_make_achievement(character_level=75))
        assert out.character_level == 75

    def test_achieved_at_is_iso_string(self) -> None:
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        out = _ach_out(_make_achievement(achieved_at=dt))
        assert isinstance(out.achieved_at, str)
        assert "2026" in out.achieved_at

    def test_achieved_at_isoformat_round_trip(self) -> None:
        dt = datetime(2026, 3, 1, 14, 30, 0, tzinfo=timezone.utc)
        out = _ach_out(_make_achievement(achieved_at=dt))
        assert out.achieved_at == dt.isoformat()

    def test_claimed_at_none_when_not_claimed(self) -> None:
        out = _ach_out(_make_achievement(claimed_at=None))
        assert out.claimed_at is None

    def test_claimed_at_is_iso_string_when_present(self) -> None:
        claimed = datetime(2026, 3, 5, 9, 0, 0, tzinfo=timezone.utc)
        out = _ach_out(_make_achievement(claimed_at=claimed))
        assert isinstance(out.claimed_at, str)
        assert out.claimed_at == claimed.isoformat()

    def test_claimed_at_different_from_achieved_at(self) -> None:
        achieved = datetime(2026, 3, 1, tzinfo=timezone.utc)
        claimed = datetime(2026, 3, 2, tzinfo=timezone.utc)
        out = _ach_out(_make_achievement(achieved_at=achieved, claimed_at=claimed))
        assert out.achieved_at != out.claimed_at

from __future__ import annotations

"""
Unit tests for backend.services.seasons_service.

Needs SQLAlchemy — run inside Docker:
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.seasons_service import (
    _milestone_met,
    _check_char_milestones,
    check_season_milestones,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _char(
    level: int = 1,
    difficulty_active: int = 0,
    hardcore: bool = False,
    name: str = "TestChar",
    class_name: str = "Paladin",
    hell_completed: bool = False,
) -> MagicMock:
    """Return a mock object resembling a D2SCharacter."""
    c = MagicMock()
    c.name = name
    c.class_name = class_name
    c.level = level
    c.hardcore = hardcore
    c.difficulty_active = difficulty_active
    c.cleared_normal = difficulty_active >= 1
    c.cleared_nightmare = difficulty_active >= 2
    c.cleared_hell = hell_completed
    return c


def _ms(
    milestone_type: str,
    level_target: int | None = None,
    ms_id: int = 1,
    ms_name: str = "Test Milestone",
    time_limit_hours: int | None = None,
) -> MagicMock:
    """Return a mock SeasonMilestone."""
    m = MagicMock()
    m.id = ms_id
    m.name = ms_name
    m.milestone_type = milestone_type
    m.level_target = level_target
    m.time_limit_hours = time_limit_hours
    return m


def _season(season_id: int = 1, started_at=None) -> MagicMock:
    from datetime import datetime, timezone
    s = MagicMock()
    s.id = season_id
    s.started_at = started_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return s


def _session_no_existing() -> AsyncMock:
    """Session where no existing achievement is found."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _session_existing_achievement() -> AsyncMock:
    """Session where an achievement already exists (deduplication)."""
    existing = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


# ─── _milestone_met ───────────────────────────────────────────────────────────

class TestMilestoneMet:
    # --- level milestones ---

    def test_level_met_when_ge_target(self) -> None:
        assert _milestone_met(_ms("level", level_target=30), _char(level=30)) is True

    def test_level_met_when_above_target(self) -> None:
        assert _milestone_met(_ms("level", level_target=20), _char(level=99)) is True

    def test_level_not_met_when_below_target(self) -> None:
        assert _milestone_met(_ms("level", level_target=30), _char(level=29)) is False

    def test_level_not_met_when_target_is_none(self) -> None:
        assert _milestone_met(_ms("level", level_target=None), _char(level=99)) is False

    def test_level_target_1_met_by_level_1(self) -> None:
        assert _milestone_met(_ms("level", level_target=1), _char(level=1)) is True

    # --- cleared_normal milestones ---

    def test_cleared_normal_false_when_difficulty_active_0(self) -> None:
        assert _milestone_met(_ms("cleared_normal"), _char(difficulty_active=0)) is False

    def test_cleared_normal_true_when_difficulty_active_1(self) -> None:
        assert _milestone_met(_ms("cleared_normal"), _char(difficulty_active=1)) is True

    def test_cleared_normal_true_when_difficulty_active_2(self) -> None:
        assert _milestone_met(_ms("cleared_normal"), _char(difficulty_active=2)) is True

    # --- cleared_nightmare milestones ---

    def test_cleared_nightmare_false_when_difficulty_active_0(self) -> None:
        assert _milestone_met(_ms("cleared_nightmare"), _char(difficulty_active=0)) is False

    def test_cleared_nightmare_false_when_difficulty_active_1(self) -> None:
        assert _milestone_met(_ms("cleared_nightmare"), _char(difficulty_active=1)) is False

    def test_cleared_nightmare_true_when_difficulty_active_2(self) -> None:
        assert _milestone_met(_ms("cleared_nightmare"), _char(difficulty_active=2)) is True

    # --- cleared_hell milestones ---

    def test_cleared_hell_false_when_not_completed(self) -> None:
        assert _milestone_met(_ms("cleared_hell"), _char(hell_completed=False)) is False

    def test_cleared_hell_true_when_completed(self) -> None:
        assert _milestone_met(_ms("cleared_hell"), _char(hell_completed=True)) is True

    def test_cleared_hell_true_regardless_of_difficulty_active(self) -> None:
        """hell_completed flag is independent of difficulty_active."""
        assert _milestone_met(_ms("cleared_hell"), _char(difficulty_active=0, hell_completed=True)) is True

    # --- time limit ---

    def test_time_limit_not_expired_allows_achievement(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=1)
        ms = _ms("level", level_target=1, time_limit_hours=48)  # 2 days, only 1h elapsed
        assert _milestone_met(ms, _char(level=1), season_started_at=started) is True

    def test_time_limit_expired_blocks_achievement(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=73)  # 3 days ago
        ms = _ms("level", level_target=1, time_limit_hours=48)  # 2-day limit
        assert _milestone_met(ms, _char(level=1), season_started_at=started) is False

    def test_time_limit_exactly_at_boundary_is_expired(self) -> None:
        """Just past the deadline → expired."""
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=48, seconds=1)
        ms = _ms("level", level_target=1, time_limit_hours=48)
        assert _milestone_met(ms, _char(level=1), season_started_at=started) is False

    def test_no_time_limit_always_eligible(self) -> None:
        """time_limit_hours=None → no time restriction."""
        ms = _ms("level", level_target=1, time_limit_hours=None)
        assert _milestone_met(ms, _char(level=1)) is True

    def test_time_limit_with_no_started_at_ignores_limit(self) -> None:
        """If season_started_at is None, time limit cannot be checked → condition skipped."""
        ms = _ms("level", level_target=1, time_limit_hours=1)  # 1-hour limit
        assert _milestone_met(ms, _char(level=1), season_started_at=None) is True

    # --- unknown milestone type ---

    def test_unknown_milestone_type_returns_false(self) -> None:
        assert _milestone_met(_ms("killed_diablo_twice"), _char(level=99)) is False

    def test_empty_milestone_type_returns_false(self) -> None:
        assert _milestone_met(_ms(""), _char(level=99)) is False


# ─── _check_char_milestones ───────────────────────────────────────────────────

class TestCheckCharMilestones:
    async def test_achievement_added_when_milestone_met(self) -> None:
        session = _session_no_existing()
        char = _char(level=30)
        milestones = [_ms("level", level_target=30)]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_achievement_not_added_when_already_exists(self) -> None:
        session = _session_existing_achievement()
        char = _char(level=30)
        milestones = [_ms("level", level_target=30)]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.add.assert_not_called()

    async def test_achievement_not_added_when_milestone_not_met(self) -> None:
        session = _session_no_existing()
        char = _char(level=10)
        milestones = [_ms("level", level_target=30)]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.add.assert_not_called()

    async def test_commit_always_called(self) -> None:
        """commit() is called even when no new achievements are recorded."""
        session = _session_no_existing()
        char = _char(level=1)
        milestones = [_ms("level", level_target=99)]  # not met
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.commit.assert_called_once()

    async def test_multiple_milestones_all_met(self) -> None:
        session = _session_no_existing()
        char = _char(level=50, difficulty_active=2, hell_completed=True)
        milestones = [
            _ms("level", level_target=30, ms_id=1),
            _ms("cleared_normal", ms_id=2),
            _ms("cleared_nightmare", ms_id=3),
            _ms("cleared_hell", ms_id=4),
        ]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        assert session.add.call_count == 4

    async def test_cleared_hell_achievement_added(self) -> None:
        session = _session_no_existing()
        char = _char(hell_completed=True)
        milestones = [_ms("cleared_hell")]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.add.assert_called_once()

    async def test_time_limited_milestone_expired_no_achievement(self) -> None:
        from datetime import datetime, timedelta, timezone
        session = _session_no_existing()
        char = _char(level=99)
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Milestone expired 72h ago
        ms = _ms("level", level_target=1, time_limit_hours=24)
        season = _season(started_at=started)
        # now - started >> 24h, so expired

        # Patch datetime.now inside the service to be 100 hours later
        from unittest.mock import patch
        fake_now = started + timedelta(hours=100)
        with patch("backend.services.seasons_service.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await _check_char_milestones(session, season, [ms], char)

        session.add.assert_not_called()

    async def test_cleared_normal_achievement_added(self) -> None:
        session = _session_no_existing()
        char = _char(difficulty_active=1)
        milestones = [_ms("cleared_normal")]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        session.add.assert_called_once()

    async def test_achievement_stores_character_name(self) -> None:
        session = _session_no_existing()
        char = _char(level=30, name="Frostblaze")
        milestones = [_ms("level", level_target=30)]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        added = session.add.call_args[0][0]
        assert added.character_name == "Frostblaze"

    async def test_achievement_stores_season_id(self) -> None:
        session = _session_no_existing()
        char = _char(level=30)
        milestones = [_ms("level", level_target=30)]
        season = _season(season_id=7)

        await _check_char_milestones(session, season, milestones, char)

        added = session.add.call_args[0][0]
        assert added.season_id == 7


# ─── check_season_milestones ──────────────────────────────────────────────────

class TestCheckSeasonMilestones:
    def _downloaded(self, filenames: list[str], tmp_path: Path) -> list[dict]:
        """Build a minimal downloaded list; local_part is a fake Path per file."""
        items = []
        for fname in filenames:
            p = tmp_path / fname
            p.write_bytes(b"\x00" * 4)  # placeholder — parse_d2s will be mocked
            items.append({"filename": fname, "local_part": p})
        return items

    async def test_no_active_season_returns_early(self, tmp_path: Path) -> None:
        session = AsyncMock()

        with patch(
            "backend.services.seasons_service._get_active_season",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await check_season_milestones(session, self._downloaded(["hero.d2s"], tmp_path))

        session.add.assert_not_called()

    async def test_hardcore_character_is_skipped(self, tmp_path: Path) -> None:
        """HC chars → no achievement, even if milestone is met."""
        hc_char = _char(hardcore=True, level=99)
        session = _session_no_existing()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("level", level_target=1)],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=hc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["hc_hero.d2s"], tmp_path)
            )

        session.add.assert_not_called()

    async def test_sc_char_not_meeting_milestone_no_achievement(
        self, tmp_path: Path
    ) -> None:
        sc_char = _char(hardcore=False, level=5)
        session = _session_no_existing()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("level", level_target=30)],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=sc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["sc_hero.d2s"], tmp_path)
            )

        session.add.assert_not_called()

    async def test_sc_char_meeting_level_milestone_creates_achievement(
        self, tmp_path: Path
    ) -> None:
        sc_char = _char(hardcore=False, level=30)
        session = _session_no_existing()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("level", level_target=30)],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=sc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["sc_hero.d2s"], tmp_path)
            )

        session.add.assert_called_once()

    async def test_sc_char_cleared_normal_creates_achievement(
        self, tmp_path: Path
    ) -> None:
        sc_char = _char(hardcore=False, difficulty_active=1)
        session = _session_no_existing()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("cleared_normal")],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=sc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["sc_hero.d2s"], tmp_path)
            )

        session.add.assert_called_once()

    async def test_non_d2s_filename_skipped(self, tmp_path: Path) -> None:
        """Files that don't end in .d2s are ignored entirely."""
        session = _session_no_existing()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("level", level_target=1)],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
            ) as mock_parse,
        ):
            stash_items = self._downloaded(
                ["ModernSharedStashSoftCoreV2.d2i", "Settings.json"], tmp_path
            )
            await check_season_milestones(session, stash_items)
            mock_parse.assert_not_called()

        session.add.assert_not_called()

    async def test_deduplication_no_double_achievement(self, tmp_path: Path) -> None:
        """When achievement already exists, session.add is NOT called again."""
        sc_char = _char(hardcore=False, level=99)
        session = _session_existing_achievement()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[_ms("level", level_target=1)],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=sc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["sc_hero.d2s"], tmp_path)
            )

        session.add.assert_not_called()

    async def test_no_milestones_no_achievements(self, tmp_path: Path) -> None:
        """If the active season has no milestones, no achievements are created."""
        sc_char = _char(hardcore=False, level=99)
        session = AsyncMock()

        with (
            patch(
                "backend.services.seasons_service._get_active_season",
                new_callable=AsyncMock,
                return_value=_season(),
            ),
            patch(
                "backend.services.seasons_service._get_milestones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.services.seasons_service.parse_d2s",
                return_value=sc_char,
            ),
        ):
            await check_season_milestones(
                session, self._downloaded(["sc_hero.d2s"], tmp_path)
            )

        session.add.assert_not_called()

from __future__ import annotations

"""
Tests for the gold_vault milestone type added 2026-03-10.

Covers
------
  _milestone_met          — extended to handle "gold_vault" type
  check_gold_milestones   — detects vault balance >= threshold, creates achievements
                            with "(Season)" sentinel, skips expired / already-achieved

The function is called:
  - After every deposit_gold() in the stash router
  - At the end of check_season_milestones() during check-in

To run (inside Docker):
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine \\
      python3 -m pytest tests/test_gold_milestone.py -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.seasons_service import (
    _milestone_met,
    _SEASON_SENTINEL,
    check_gold_milestones,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ms(
    milestone_type: str = "gold_vault",
    numeric_target: int | None = 500_000,
    level_target: int | None = None,
    time_limit_hours: int | None = None,
) -> MagicMock:
    ms = MagicMock()
    ms.id = 1
    ms.milestone_type = milestone_type
    ms.numeric_target = numeric_target
    ms.level_target = level_target
    ms.time_limit_hours = time_limit_hours
    return ms


def _season(started_at: datetime | None = None) -> MagicMock:
    s = MagicMock()
    s.id = 1
    s.started_at = started_at
    return s


def _vault(amount: int) -> MagicMock:
    v = MagicMock()
    v.amount = amount
    v.hardcore = False
    return v


def _session(vault: MagicMock | None, existing_achievement=None) -> AsyncMock:
    """
    Session that returns `vault` for the vault query and `existing_achievement`
    for the achievement deduplication query.
    """
    vault_result = MagicMock()
    vault_result.scalar_one_or_none.return_value = vault

    ach_result = MagicMock()
    ach_result.scalar_one_or_none.return_value = existing_achievement

    s = AsyncMock()
    s.execute = AsyncMock(side_effect=[vault_result, ach_result])
    s.add = MagicMock()
    s.commit = AsyncMock()
    return s


# ─── _milestone_met: gold_vault type ─────────────────────────────────────────

class TestMilestoneMetGoldVault:

    def test_met_when_vault_equals_target(self) -> None:
        ms = _ms(numeric_target=1_000_000)
        assert _milestone_met(ms, vault_gold_sc=1_000_000) is True

    def test_met_when_vault_exceeds_target(self) -> None:
        ms = _ms(numeric_target=500_000)
        assert _milestone_met(ms, vault_gold_sc=2_000_000) is True

    def test_not_met_when_vault_below_target(self) -> None:
        ms = _ms(numeric_target=1_000_000)
        assert _milestone_met(ms, vault_gold_sc=999_999) is False

    def test_not_met_when_vault_is_zero(self) -> None:
        ms = _ms(numeric_target=500_000)
        assert _milestone_met(ms, vault_gold_sc=0) is False

    def test_not_met_when_numeric_target_is_none(self) -> None:
        ms = _ms(numeric_target=None)
        assert _milestone_met(ms, vault_gold_sc=99_999_999) is False

    def test_not_met_when_time_limit_expired(self) -> None:
        started = _now_utc() - timedelta(hours=49)
        ms = _ms(numeric_target=100, time_limit_hours=48)
        assert _milestone_met(ms, season_started_at=started, vault_gold_sc=999_999) is False

    def test_met_when_time_limit_not_yet_expired(self) -> None:
        started = _now_utc() - timedelta(hours=23)
        ms = _ms(numeric_target=100, time_limit_hours=48)
        assert _milestone_met(ms, season_started_at=started, vault_gold_sc=999_999) is True

    def test_char_argument_ignored_for_gold_vault(self) -> None:
        """gold_vault milestone should not depend on char at all."""
        ms = _ms(numeric_target=100)
        char = MagicMock()
        char.level = 1
        assert _milestone_met(ms, char=char, vault_gold_sc=100) is True


class TestMilestoneMetExistingTypes:
    """Ensure existing character-based types still work after the refactor."""

    def _char(self, level=1, cleared_normal=False, cleared_nightmare=False, cleared_hell=False):
        c = MagicMock()
        c.level = level
        c.cleared_normal = cleared_normal
        c.cleared_nightmare = cleared_nightmare
        c.cleared_hell = cleared_hell
        return c

    def test_level_still_works(self) -> None:
        ms = _ms(milestone_type="level", numeric_target=None, level_target=30)
        assert _milestone_met(ms, char=self._char(level=30)) is True
        assert _milestone_met(ms, char=self._char(level=29)) is False

    def test_cleared_normal_still_works(self) -> None:
        ms = _ms(milestone_type="cleared_normal", numeric_target=None)
        assert _milestone_met(ms, char=self._char(cleared_normal=True)) is True
        assert _milestone_met(ms, char=self._char(cleared_normal=False)) is False

    def test_char_none_returns_false_for_char_based(self) -> None:
        ms = _ms(milestone_type="level", numeric_target=None, level_target=10)
        assert _milestone_met(ms, char=None, vault_gold_sc=99999) is False


# ─── check_gold_milestones ────────────────────────────────────────────────────

class TestCheckGoldMilestones:

    async def test_creates_achievement_when_vault_meets_threshold(self) -> None:
        season = _season()
        milestones = [_ms(numeric_target=500_000)]
        session = _session(vault=_vault(600_000), existing_achievement=None)

        await check_gold_milestones(session, active_season=season, milestones=milestones)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.character_name == _SEASON_SENTINEL
        assert added.character_class == ""
        assert added.character_level == 0
        assert added.milestone_id == 1
        session.commit.assert_awaited_once()

    async def test_does_not_create_achievement_when_vault_below_threshold(self) -> None:
        season = _season()
        milestones = [_ms(numeric_target=1_000_000)]
        session = _session(vault=_vault(999_999), existing_achievement=None)

        await check_gold_milestones(session, active_season=season, milestones=milestones)

        session.add.assert_not_called()

    async def test_does_not_create_duplicate_achievement(self) -> None:
        season = _season()
        milestones = [_ms(numeric_target=100)]
        existing = MagicMock()  # already achieved
        session = _session(vault=_vault(999_999), existing_achievement=existing)

        await check_gold_milestones(session, active_season=season, milestones=milestones)

        session.add.assert_not_called()

    async def test_skips_non_gold_vault_milestones(self) -> None:
        """check_gold_milestones only processes gold_vault type."""
        season = _season()
        level_ms = _ms(milestone_type="level", numeric_target=None, level_target=30)
        milestones = [level_ms]

        # Session only needs to handle no gold queries (no gold_vault milestones)
        s = AsyncMock()
        s.add = MagicMock()
        s.commit = AsyncMock()

        await check_gold_milestones(s, active_season=season, milestones=milestones)

        s.add.assert_not_called()
        # execute never called because no gold_vault milestones to process
        s.execute.assert_not_called()

    async def test_no_active_season_returns_early(self) -> None:
        s = AsyncMock()
        # execute returns no season
        no_season_result = MagicMock()
        no_season_result.scalar_one_or_none.return_value = None
        s.execute = AsyncMock(return_value=no_season_result)
        s.add = MagicMock()

        await check_gold_milestones(s)  # no season/milestones passed — fetches from DB

        s.add.assert_not_called()

    async def test_no_vault_row_treated_as_zero_gold(self) -> None:
        season = _season()
        milestones = [_ms(numeric_target=1)]
        # vault query returns None (no row)
        session = _session(vault=None, existing_achievement=None)

        await check_gold_milestones(session, active_season=season, milestones=milestones)

        # vault_gold_sc = 0, threshold = 1 → not met
        session.add.assert_not_called()

    async def test_time_expired_milestone_not_triggered(self) -> None:
        started = _now_utc() - timedelta(hours=73)
        season = _season(started_at=started)
        milestones = [_ms(numeric_target=100, time_limit_hours=72)]
        session = _session(vault=_vault(999_999), existing_achievement=None)

        await check_gold_milestones(session, active_season=season, milestones=milestones)

        session.add.assert_not_called()

    async def test_multiple_milestones_both_triggered(self) -> None:
        season = _season()
        ms1 = _ms(milestone_type="gold_vault", numeric_target=100)
        ms1.id = 1
        ms2 = MagicMock()
        ms2.id = 2
        ms2.milestone_type = "gold_vault"
        ms2.numeric_target = 200
        ms2.time_limit_hours = None
        milestones = [ms1, ms2]

        vault_result = MagicMock()
        vault_result.scalar_one_or_none.return_value = _vault(500)

        no_ach = MagicMock()
        no_ach.scalar_one_or_none.return_value = None

        s = AsyncMock()
        s.execute = AsyncMock(side_effect=[vault_result, no_ach, no_ach])
        s.add = MagicMock()
        s.commit = AsyncMock()

        await check_gold_milestones(s, active_season=season, milestones=milestones)

        assert s.add.call_count == 2

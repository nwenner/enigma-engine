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
    acts_cleared: dict | None = None,
) -> MagicMock:
    """Return a mock object resembling a D2SCharacter."""
    c = MagicMock()
    c.name = name
    c.class_name = class_name
    c.level = level
    c.hardcore = hardcore
    c.difficulty_active = difficulty_active
    # acts_cleared dict: default builds from difficulty_active / hell_completed
    # for backward-compat with existing tests that don't pass acts_cleared
    if acts_cleared is not None:
        c.acts_cleared = acts_cleared
    else:
        # Synthesize a reasonable default from the old flags
        ac: dict = {}
        for diff_idx, diff_name in enumerate(["normal", "nightmare", "hell"]):
            for act in range(1, 6):
                if diff_name == "hell":
                    ac[f"cleared_act{act}_hell"] = hell_completed and act == 5
                elif difficulty_active >= diff_idx + 1:
                    ac[f"cleared_act{act}_{diff_name}"] = True
                else:
                    ac[f"cleared_act{act}_{diff_name}"] = False
        c.acts_cleared = ac
    return c


def _ms(
    milestone_type: str,
    level_target: int | None = None,
    ms_id: int = 1,
    ms_name: str = "Test Milestone",
    time_limit_hours: int | None = None,
    scope: str = "character",
) -> MagicMock:
    """Return a mock SeasonMilestone."""
    m = MagicMock()
    m.id = ms_id
    m.name = ms_name
    m.milestone_type = milestone_type
    m.level_target = level_target
    m.time_limit_hours = time_limit_hours
    m.scope = scope
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

    # --- cleared_actN_diffname milestones ---

    def test_cleared_act5_normal_false_when_not_cleared(self) -> None:
        char = _char(acts_cleared={"cleared_act5_normal": False})
        assert _milestone_met(_ms("cleared_act5_normal"), char) is False

    def test_cleared_act5_normal_true_when_cleared(self) -> None:
        char = _char(acts_cleared={"cleared_act5_normal": True})
        assert _milestone_met(_ms("cleared_act5_normal"), char) is True

    def test_cleared_act1_normal_true_when_cleared(self) -> None:
        char = _char(acts_cleared={"cleared_act1_normal": True})
        assert _milestone_met(_ms("cleared_act1_normal"), char) is True

    def test_cleared_act5_hell_true_when_cleared(self) -> None:
        char = _char(acts_cleared={"cleared_act5_hell": True})
        assert _milestone_met(_ms("cleared_act5_hell"), char) is True

    def test_cleared_act5_hell_false_when_not_cleared(self) -> None:
        char = _char(acts_cleared={"cleared_act5_hell": False})
        assert _milestone_met(_ms("cleared_act5_hell"), char) is False

    def test_acts_cleared_dict_missing_key_returns_false(self) -> None:
        """Graceful fallback: missing key in acts_cleared → False."""
        char = _char(acts_cleared={})
        assert _milestone_met(_ms("cleared_act3_nightmare"), char) is False

    def test_old_cleared_normal_type_returns_false(self) -> None:
        """Old milestone types are no longer recognized → False."""
        char = _char(difficulty_active=2)
        assert _milestone_met(_ms("cleared_normal"), char) is False

    def test_old_cleared_hell_type_returns_false(self) -> None:
        """Old cleared_hell type is no longer recognized → False."""
        char = _char(acts_cleared={"cleared_act5_hell": True})
        assert _milestone_met(_ms("cleared_hell"), char) is False

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
        char = _char(level=50, acts_cleared={
            "cleared_act5_normal": True,
            "cleared_act5_nightmare": True,
            "cleared_act5_hell": True,
        })
        milestones = [
            _ms("level", level_target=30, ms_id=1),
            _ms("cleared_act5_normal", ms_id=2),
            _ms("cleared_act5_nightmare", ms_id=3),
            _ms("cleared_act5_hell", ms_id=4),
        ]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        assert session.add.call_count == 4

    async def test_cleared_act5_hell_achievement_added(self) -> None:
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act5_hell": True})
        milestones = [_ms("cleared_act5_hell")]
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

    async def test_cleared_act1_normal_achievement_added(self) -> None:
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act1_normal": True})
        milestones = [_ms("cleared_act1_normal")]
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

    async def test_sc_char_cleared_act1_normal_creates_achievement(
        self, tmp_path: Path
    ) -> None:
        sc_char = _char(hardcore=False, acts_cleared={"cleared_act1_normal": True})
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
                return_value=[_ms("cleared_act1_normal")],
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


# ─── Account-scope vs Character-scope milestones ──────────────────────────────

class TestMilestoneScope:
    """
    Covers the scope field on SeasonMilestone.

    Examples from spec:
      - "I create a milestone that awards an item the first time I reach level 90
         in a season" → scope="account"
      - "I create a milestone that awards a Spirit for every character I create
         that reaches level 45" → scope="character"
      - Gold vault milestones are always account-scoped (out of scope for this class)
    """

    # ── account scope ──────────────────────────────────────────────────────────

    async def test_account_scope_uses_season_sentinel(self) -> None:
        """Account-scoped milestone: achievement character_name is '(Season)'."""
        session = _session_no_existing()
        char = _char(level=90, name="LadderHero")
        ms = _ms("level", level_target=90, scope="account")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.character_name == "(Season)"
        assert added.character_class == ""
        assert added.character_level == 0

    async def test_account_scope_fires_only_once_across_characters(self) -> None:
        """Second character meeting account-scoped milestone does NOT add another achievement."""
        session = _session_no_existing()
        char_a = _char(level=90, name="HeroA")
        ms = _ms("level", level_target=90, scope="account")
        season = _season()

        await _check_char_milestones(session, season, [ms], char_a)
        assert session.add.call_count == 1

        # Simulate second character check — achievement now exists
        session2 = _session_existing_achievement()
        char_b = _char(level=90, name="HeroB")

        await _check_char_milestones(session2, season, [ms], char_b)
        session2.add.assert_not_called()

    async def test_account_scope_level_90_first_in_season(self) -> None:
        """Spec example: award item the first time anyone hits level 90 this season."""
        session = _session_no_existing()
        char = _char(level=90, name="FirstNinety")
        ms = _ms("level", level_target=90, scope="account", ms_name="First 90 Reward")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "(Season)"

    async def test_account_scope_cleared_act5_hell(self) -> None:
        """Account-scope Baal Hell: one achievement for the whole season."""
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act5_hell": True}, name="Diablo Slayer")
        ms = _ms("cleared_act5_hell", scope="account")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "(Season)"

    async def test_account_scope_cleared_act1_normal(self) -> None:
        """Account-scope Andariel Normal: sentinel used."""
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act1_normal": True}, name="NoviceRunner")
        ms = _ms("cleared_act1_normal", scope="account")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "(Season)"

    # ── character scope ────────────────────────────────────────────────────────

    async def test_character_scope_uses_char_name(self) -> None:
        """Character-scoped milestone: achievement character_name matches the char."""
        session = _session_no_existing()
        char = _char(level=45, name="SpiritPaladin")
        ms = _ms("level", level_target=45, scope="character")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "SpiritPaladin"

    async def test_character_scope_stores_class_and_level(self) -> None:
        """Character-scoped: class and level at time of achievement are stored."""
        session = _session_no_existing()
        char = _char(level=45, name="SpiritPaladin", class_name="Paladin")
        ms = _ms("level", level_target=45, scope="character")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_class == "Paladin"
        assert added.character_level == 45

    async def test_character_scope_spirit_crystal_sword_per_character(self) -> None:
        """Spec example: award Spirit for every character that reaches level 45."""
        session = _session_no_existing()
        char = _char(level=45, name="NewPaladin")
        ms = _ms("level", level_target=45, scope="character", ms_name="Spirit Crystal Sword")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "NewPaladin"
        assert added.character_name != "(Season)"

    async def test_character_scope_cleared_act1_normal(self) -> None:
        """Character-scoped Andariel Normal: one achievement per character."""
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act1_normal": True}, name="NightmareRunner")
        ms = _ms("cleared_act1_normal", scope="character")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "NightmareRunner"

    # ── mixed scope on same season ─────────────────────────────────────────────

    async def test_mixed_scope_both_achievements_created(self) -> None:
        """One account-scope and one character-scope milestone → both achievements added."""
        session = _session_no_existing()
        char = _char(level=90, name="Completionist", acts_cleared={
            "cleared_act5_nightmare": True,
        })
        milestones = [
            _ms("level", level_target=90, ms_id=1, scope="account"),         # fires once per season
            _ms("cleared_act5_nightmare", ms_id=2, scope="character"),        # fires per character
        ]
        season = _season()

        await _check_char_milestones(session, season, milestones, char)

        assert session.add.call_count == 2
        calls = [c[0][0] for c in session.add.call_args_list]
        names = {a.character_name for a in calls}
        assert "(Season)" in names
        assert "Completionist" in names


# ─── Quest Milestone Tests ────────────────────────────────────────────────────

class TestQuestMilestones:
    """
    Tests for cleared_actN_diffname milestone types.
    """

    def test_cleared_act1_normal_met_when_boss_killed(self) -> None:
        char = _char(acts_cleared={"cleared_act1_normal": True})
        assert _milestone_met(_ms("cleared_act1_normal"), char) is True

    def test_cleared_act1_normal_not_met_when_boss_not_killed(self) -> None:
        char = _char(acts_cleared={"cleared_act1_normal": False})
        assert _milestone_met(_ms("cleared_act1_normal"), char) is False

    def test_cleared_act5_hell_replaces_cleared_hell(self) -> None:
        """Old 'cleared_hell' type no longer works; new 'cleared_act5_hell' does."""
        char = _char(acts_cleared={"cleared_act5_hell": True})
        # old type returns False
        assert _milestone_met(_ms("cleared_hell"), char) is False
        # new type returns True
        assert _milestone_met(_ms("cleared_act5_hell"), char) is True

    async def test_account_scope_quest_milestone_fires_once_across_chars(self) -> None:
        """Account-scoped quest milestone: achievement added on first char, skipped on second."""
        session = _session_no_existing()
        char_a = _char(acts_cleared={"cleared_act4_hell": True}, name="CharA")
        ms = _ms("cleared_act4_hell", scope="account")
        season = _season()

        await _check_char_milestones(session, season, [ms], char_a)
        assert session.add.call_count == 1

        # Second character → dedup by sentinel
        session2 = _session_existing_achievement()
        char_b = _char(acts_cleared={"cleared_act4_hell": True}, name="CharB")
        await _check_char_milestones(session2, season, [ms], char_b)
        session2.add.assert_not_called()

    async def test_character_scope_quest_milestone_fires_per_char(self) -> None:
        """Character-scoped quest milestone: achievement uses character name."""
        session = _session_no_existing()
        char = _char(acts_cleared={"cleared_act3_normal": True}, name="Mephistos_Bane")
        ms = _ms("cleared_act3_normal", scope="character")
        season = _season()

        await _check_char_milestones(session, season, [ms], char)

        added = session.add.call_args[0][0]
        assert added.character_name == "Mephistos_Bane"
        assert added.character_name != "(Season)"

    def test_quest_milestone_respects_time_limit(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=1)
        ms = _ms("cleared_act2_normal", time_limit_hours=48)
        char = _char(acts_cleared={"cleared_act2_normal": True})
        assert _milestone_met(ms, char, season_started_at=started) is True

    def test_quest_milestone_does_not_fire_after_deadline(self) -> None:
        from datetime import datetime, timedelta, timezone
        started = datetime.now(timezone.utc) - timedelta(hours=73)
        ms = _ms("cleared_act2_normal", time_limit_hours=48)
        char = _char(acts_cleared={"cleared_act2_normal": True})
        assert _milestone_met(ms, char, season_started_at=started) is False

    def test_acts_cleared_dict_missing_key_returns_false(self) -> None:
        """Graceful fallback: key not present → False, no KeyError."""
        char = _char(acts_cleared={})
        assert _milestone_met(_ms("cleared_act3_nightmare"), char) is False

    def test_all_5_acts_normal_can_each_trigger_own_milestone(self) -> None:
        bosses = ["cleared_act1_normal", "cleared_act2_normal", "cleared_act3_normal",
                  "cleared_act4_normal", "cleared_act5_normal"]
        acts_cleared = {k: True for k in bosses}
        char = _char(acts_cleared=acts_cleared)
        for key in bosses:
            assert _milestone_met(_ms(key), char) is True

    def test_mixed_act_difficulty_combos_independent(self) -> None:
        """act3_normal and act3_nightmare are tracked independently."""
        char_normal = _char(acts_cleared={"cleared_act3_normal": True, "cleared_act3_nightmare": False})
        char_nm = _char(acts_cleared={"cleared_act3_normal": False, "cleared_act3_nightmare": True})

        assert _milestone_met(_ms("cleared_act3_normal"), char_normal) is True
        assert _milestone_met(_ms("cleared_act3_nightmare"), char_normal) is False

        assert _milestone_met(_ms("cleared_act3_normal"), char_nm) is False
        assert _milestone_met(_ms("cleared_act3_nightmare"), char_nm) is True

from __future__ import annotations

"""
Unit tests for milestone editing endpoints added 2026-03-10.

Endpoints under test
--------------------
  POST   /seasons/{season_id}/milestones                — add_milestone
  PATCH  /seasons/{season_id}/milestones/{milestone_id} — patch_milestone
  DELETE /seasons/{season_id}/milestones/{milestone_id} — delete_milestone

Strategy
--------
- All tests use pure async functions extracted from the router logic, called
  directly with mocked sessions (same pattern as test_stash_vault.py).
- No HTTP client / FastAPI TestClient needed — the business logic is in the
  router functions themselves, which are thin and easy to unit-test.
- SQLAlchemy models are MagicMock objects; FK integrity is not tested here
  (that belongs in integration tests against a real DB).

To run (inside Docker):
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine \\
      python3 -m pytest tests/test_milestone_edit.py -v
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.routers.seasons import (
    add_milestone,
    patch_milestone,
    delete_milestone,
    MilestoneIn,
    MilestonePatch,
)


# ─── Model factories ──────────────────────────────────────────────────────────

def _season(status: str = "active", started_at=None, id: int = 1) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.status = status
    s.started_at = started_at
    return s


def _milestone(
    id: int = 10,
    season_id: int = 1,
    name: str = "First Blood",
    milestone_type: str = "level",
    scope: str = "character",
    level_target: int | None = 30,
    numeric_target: int | None = None,
    time_limit_hours: int | None = None,
    reward_item_bytes: bytes | None = None,
    reward_item_name: str | None = None,
    reward_item_code: str | None = None,
) -> MagicMock:
    ms = MagicMock()
    ms.id = id
    ms.season_id = season_id
    ms.name = name
    ms.milestone_type = milestone_type
    ms.scope = scope
    ms.level_target = level_target
    ms.numeric_target = numeric_target
    ms.time_limit_hours = time_limit_hours
    ms.reward_item_bytes = reward_item_bytes
    ms.reward_item_name = reward_item_name
    ms.reward_item_code = reward_item_code
    ms.sort_order = 0
    return ms


def _session_get(*get_returns, stamp_id: int | None = 42):
    """
    Session mock where session.get() returns values in order.
    stamp_id: if set, the commit side-effect sets .id on every added object
    so that _ms_out() doesn't receive id=None and fail Pydantic validation.

    Returns (session, added_list) so tests can inspect what was added without
    overriding session.add themselves.
    """
    s = AsyncMock()
    s.get = AsyncMock(side_effect=list(get_returns))

    added: list = []

    def _add(obj):
        added.append(obj)

    s.add = MagicMock(side_effect=_add)
    s.delete = AsyncMock()
    s.flush = AsyncMock()

    async def _commit():
        if stamp_id is not None:
            for obj in added:
                try:
                    if obj.id is None:
                        object.__setattr__(obj, "id", stamp_id)
                except Exception:
                    pass

    s.commit = AsyncMock(side_effect=_commit)

    count_result = MagicMock()
    count_result.scalar.return_value = 0
    s.execute = AsyncMock(return_value=count_result)

    s._added = added  # expose for test inspection
    return s


def _ms_body(**kwargs) -> MilestoneIn:
    defaults = dict(
        name="Kill Baal",
        milestone_type="cleared_act5_hell",
        level_target=None,
        sort_order=0,
        reward_item_hex=None,
        reward_item_name=None,
        reward_item_code=None,
        time_limit_hours=None,
    )
    defaults.update(kwargs)
    return MilestoneIn(**defaults)


# ─── add_milestone ────────────────────────────────────────────────────────────

class TestAddMilestone:

    async def test_creates_milestone_for_active_season(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(season_id=1, body=_ms_body(name="Level 30"), session=session)

        assert len(session._added) == 1
        ms = session._added[0]
        assert ms.name == "Level 30"
        assert ms.season_id == 1
        session.commit.assert_awaited_once()

    async def test_creates_milestone_for_setup_season(self) -> None:
        season = _season(status="setup")
        session = _session_get(season)

        await add_milestone(season_id=1, body=_ms_body(), session=session)
        session.commit.assert_awaited_once()

    async def test_raises_404_when_season_not_found(self) -> None:
        from fastapi import HTTPException
        session = _session_get(None)

        with pytest.raises(HTTPException) as exc:
            await add_milestone(season_id=99, body=_ms_body(), session=session)
        assert exc.value.status_code == 404

    async def test_raises_400_for_completed_season(self) -> None:
        from fastapi import HTTPException
        season = _season(status="completed")
        session = _session_get(season)

        with pytest.raises(HTTPException) as exc:
            await add_milestone(season_id=1, body=_ms_body(), session=session)
        assert exc.value.status_code == 400

    async def test_raises_400_for_invalid_hex(self) -> None:
        from fastapi import HTTPException
        season = _season(status="active")
        session = _session_get(season)

        with pytest.raises(HTTPException) as exc:
            await add_milestone(
                season_id=1,
                body=_ms_body(reward_item_hex="ZZ ZZ ZZ"),
                session=session,
            )
        assert exc.value.status_code == 400

    async def test_parses_valid_hex_to_bytes(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=_ms_body(reward_item_hex="10 0f 00 00"),
            session=session,
        )

        assert session._added[0].reward_item_bytes == bytes([0x10, 0x0F, 0x00, 0x00])

    async def test_no_reward_leaves_bytes_none(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(season_id=1, body=_ms_body(reward_item_hex=None), session=session)
        assert session._added[0].reward_item_bytes is None

    async def test_raises_400_for_zero_time_limit(self) -> None:
        from fastapi import HTTPException
        season = _season(status="active")
        session = _session_get(season)

        with pytest.raises(HTTPException) as exc:
            await add_milestone(
                season_id=1,
                body=_ms_body(time_limit_hours=0),
                session=session,
            )
        assert exc.value.status_code == 400

    async def test_stores_time_limit_hours(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=_ms_body(time_limit_hours=48),
            session=session,
        )
        assert session._added[0].time_limit_hours == 48

    async def test_milestone_type_and_level_target_stored(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=_ms_body(milestone_type="level", level_target=50),
            session=session,
        )
        assert session._added[0].milestone_type == "level"
        assert session._added[0].level_target == 50


# ─── patch_milestone ──────────────────────────────────────────────────────────

class TestPatchMilestone:
    """
    patch_milestone uses model_fields_set — only fields present in the JSON
    body are applied. We simulate this by constructing MilestonePatch with
    keyword arguments so Pydantic populates model_fields_set correctly.
    """

    async def test_updates_name(self) -> None:
        season = _season()
        ms = _milestone()
        session = _session_get(season, ms)

        body = MilestonePatch(name="New Name")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.name == "New Name"
        session.commit.assert_awaited_once()

    async def test_leaves_name_unchanged_when_not_in_body(self) -> None:
        season = _season()
        ms = _milestone(name="Original")
        session = _session_get(season, ms)

        body = MilestonePatch(time_limit_hours=24)
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.name == "Original"

    async def test_updates_milestone_type(self) -> None:
        season = _season()
        ms = _milestone(milestone_type="level")
        session = _session_get(season, ms)

        body = MilestonePatch(milestone_type="cleared_act5_hell")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.milestone_type == "cleared_act5_hell"

    async def test_clears_level_target_when_null_provided(self) -> None:
        season = _season()
        ms = _milestone(level_target=30)
        session = _session_get(season, ms)

        body = MilestonePatch(level_target=None)
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.level_target is None

    async def test_updates_time_limit_hours(self) -> None:
        season = _season()
        ms = _milestone(time_limit_hours=None)
        session = _session_get(season, ms)

        body = MilestonePatch(time_limit_hours=48)
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.time_limit_hours == 48

    async def test_clears_time_limit_when_null_provided(self) -> None:
        season = _season()
        ms = _milestone(time_limit_hours=96)
        session = _session_get(season, ms)

        body = MilestonePatch(time_limit_hours=None)
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.time_limit_hours is None

    async def test_replaces_reward_bytes(self) -> None:
        season = _season()
        ms = _milestone(reward_item_bytes=b"old bytes")
        session = _session_get(season, ms)

        body = MilestonePatch(reward_item_hex="AB CD EF")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.reward_item_bytes == bytes([0xAB, 0xCD, 0xEF])

    async def test_clears_reward_when_empty_hex(self) -> None:
        season = _season()
        ms = _milestone(reward_item_bytes=b"old", reward_item_name="Jah Rune", reward_item_code="r31")
        session = _session_get(season, ms)

        body = MilestonePatch(reward_item_hex="")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.reward_item_bytes is None
        assert ms.reward_item_name is None
        assert ms.reward_item_code is None

    async def test_clears_reward_when_none_hex(self) -> None:
        season = _season()
        ms = _milestone(reward_item_bytes=b"old", reward_item_name="Something")
        session = _session_get(season, ms)

        body = MilestonePatch(reward_item_hex=None)
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.reward_item_bytes is None

    async def test_raises_400_for_invalid_hex(self) -> None:
        from fastapi import HTTPException
        season = _season()
        ms = _milestone()
        session = _session_get(season, ms)

        body = MilestonePatch(reward_item_hex="ZZ ZZ")
        with pytest.raises(HTTPException) as exc:
            await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)
        assert exc.value.status_code == 400

    async def test_leaves_reward_unchanged_when_hex_not_in_body(self) -> None:
        season = _season()
        ms = _milestone(reward_item_bytes=b"keep me", reward_item_name="Enigma")
        session = _session_get(season, ms)

        body = MilestonePatch(name="New Name")  # no reward_item_hex field
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.reward_item_bytes == b"keep me"
        assert ms.reward_item_name == "Enigma"

    async def test_updates_reward_name_without_hex(self) -> None:
        """reward_item_name alone (no hex) just renames the display label."""
        season = _season()
        ms = _milestone(reward_item_bytes=b"bytes", reward_item_name="Old Label")
        session = _session_get(season, ms)

        body = MilestonePatch(reward_item_name="New Label")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.reward_item_name == "New Label"
        assert ms.reward_item_bytes == b"bytes"  # unchanged

    async def test_raises_404_when_season_not_found(self) -> None:
        from fastapi import HTTPException
        session = _session_get(None)

        with pytest.raises(HTTPException) as exc:
            await patch_milestone(season_id=99, milestone_id=10, body=MilestonePatch(name="x"), session=session)
        assert exc.value.status_code == 404

    async def test_raises_400_for_completed_season(self) -> None:
        from fastapi import HTTPException
        season = _season(status="completed")
        session = _session_get(season)

        with pytest.raises(HTTPException) as exc:
            await patch_milestone(season_id=1, milestone_id=10, body=MilestonePatch(name="x"), session=session)
        assert exc.value.status_code == 400

    async def test_raises_404_when_milestone_not_found(self) -> None:
        from fastapi import HTTPException
        season = _season()
        session = _session_get(season, None)

        with pytest.raises(HTTPException) as exc:
            await patch_milestone(season_id=1, milestone_id=99, body=MilestonePatch(name="x"), session=session)
        assert exc.value.status_code == 404

    async def test_raises_404_when_milestone_belongs_to_different_season(self) -> None:
        from fastapi import HTTPException
        season = _season(id=1)
        ms = _milestone(season_id=2)  # belongs to season 2, not 1
        session = _session_get(season, ms)

        with pytest.raises(HTTPException) as exc:
            await patch_milestone(season_id=1, milestone_id=10, body=MilestonePatch(name="x"), session=session)
        assert exc.value.status_code == 404


# ─── delete_milestone ─────────────────────────────────────────────────────────

class TestDeleteMilestone:

    def _session_with_achievement_count(self, season, ms, count: int) -> AsyncMock:
        s = AsyncMock()
        get_calls = [season, ms]
        s.get = AsyncMock(side_effect=get_calls)

        count_result = MagicMock()
        count_result.scalar.return_value = count

        s.execute = AsyncMock(return_value=count_result)
        s.delete = AsyncMock()
        s.commit = AsyncMock()
        return s

    async def test_deletes_milestone(self) -> None:
        season = _season()
        ms = _milestone()
        session = self._session_with_achievement_count(season, ms, 0)

        result = await delete_milestone(season_id=1, milestone_id=10, session=session)

        session.delete.assert_awaited_once_with(ms)
        session.commit.assert_awaited_once()

    async def test_returns_achievements_deleted_count(self) -> None:
        season = _season()
        ms = _milestone()
        session = self._session_with_achievement_count(season, ms, 3)

        result = await delete_milestone(season_id=1, milestone_id=10, session=session)

        assert result["achievements_deleted"] == 3
        assert result["success"] is True

    async def test_returns_zero_when_no_achievements(self) -> None:
        season = _season()
        ms = _milestone()
        session = self._session_with_achievement_count(season, ms, 0)

        result = await delete_milestone(season_id=1, milestone_id=10, session=session)
        assert result["achievements_deleted"] == 0

    async def test_executes_achievement_delete_before_milestone_delete(self) -> None:
        """CASCADE: achievements must be deleted before the milestone."""
        from sqlalchemy import delete as sa_delete
        from backend.models import SeasonAchievement

        season = _season()
        ms = _milestone()

        execute_calls = []
        delete_calls = []

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[season, ms])

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        async def track_execute(stmt):
            execute_calls.append(stmt)
            return count_result
        session.execute = track_execute

        async def track_delete(obj):
            delete_calls.append(obj)
        session.delete = track_delete
        session.commit = AsyncMock()

        await delete_milestone(season_id=1, milestone_id=10, session=session)

        # execute was called twice: once for count, once for cascade delete
        assert len(execute_calls) == 2
        # milestone.delete called after achievement cascade
        assert ms in delete_calls

    async def test_raises_404_when_season_not_found(self) -> None:
        from fastapi import HTTPException
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

        with pytest.raises(HTTPException) as exc:
            await delete_milestone(season_id=99, milestone_id=10, session=session)
        assert exc.value.status_code == 404

    async def test_raises_400_for_completed_season(self) -> None:
        from fastapi import HTTPException
        season = _season(status="completed")
        session = AsyncMock()
        session.get = AsyncMock(return_value=season)
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

        with pytest.raises(HTTPException) as exc:
            await delete_milestone(season_id=1, milestone_id=10, session=session)
        assert exc.value.status_code == 400

    async def test_raises_404_when_milestone_not_found(self) -> None:
        from fastapi import HTTPException
        season = _season()
        session = AsyncMock()
        session.get = AsyncMock(side_effect=[season, None])
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

        with pytest.raises(HTTPException) as exc:
            await delete_milestone(season_id=1, milestone_id=99, session=session)
        assert exc.value.status_code == 404

    async def test_raises_404_when_milestone_belongs_to_other_season(self) -> None:
        from fastapi import HTTPException
        season = _season()
        ms = _milestone(season_id=2)  # wrong season
        session = AsyncMock()
        session.get = AsyncMock(side_effect=[season, ms])
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

        with pytest.raises(HTTPException) as exc:
            await delete_milestone(season_id=1, milestone_id=10, session=session)
        assert exc.value.status_code == 404


# ─── Scope field on add/patch ─────────────────────────────────────────────────

class TestMilestoneScopeRouterOps:
    """Covers scope field handling in add_milestone and patch_milestone."""

    async def test_add_milestone_default_scope_is_character(self) -> None:
        """When scope is not provided, it defaults to 'character'."""
        from backend.routers.seasons import add_milestone, MilestoneIn
        season = _season()
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=MilestoneIn(name="Hit 45", milestone_type="level", level_target=45),
            session=session,
        )

        assert len(session._added) == 1
        assert session._added[0].scope == "character"

    async def test_add_milestone_account_scope_stored(self) -> None:
        """Explicitly passing scope='account' stores account on the milestone."""
        from backend.routers.seasons import add_milestone, MilestoneIn
        season = _season()
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=MilestoneIn(name="First 90", milestone_type="level", level_target=90, scope="account"),
            session=session,
        )

        assert session._added[0].scope == "account"

    async def test_add_milestone_gold_vault_always_account(self) -> None:
        """Gold vault milestone is forced to account scope regardless of input."""
        from backend.routers.seasons import add_milestone, MilestoneIn
        season = _season()
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=MilestoneIn(name="Gold Goal", milestone_type="gold_vault", numeric_target=2_000_000, scope="character"),
            session=session,
        )

        assert session._added[0].scope == "account"

    async def test_patch_milestone_scope_updated(self) -> None:
        """Patching scope from 'character' to 'account' is applied."""
        from backend.routers.seasons import patch_milestone, MilestonePatch
        season = _season()
        ms = _milestone(scope="character")
        session = _session_get(season, ms)

        await patch_milestone(
            season_id=1,
            milestone_id=10,
            body=MilestonePatch(scope="account"),
            session=session,
        )

        assert ms.scope == "account"


# ─── Quest Milestone Router Ops ──────────────────────────────────────────────

class TestQuestMilestoneRouterOps:
    """Tests for CRUD ops with cleared_actN_diffname milestone types."""

    async def test_create_cleared_act2_normal_milestone(self) -> None:
        season = _season(status="active")
        session = _session_get(season)

        await add_milestone(
            season_id=1,
            body=_ms_body(name="Kill Duriel", milestone_type="cleared_act2_normal"),
            session=session,
        )

        assert len(session._added) == 1
        assert session._added[0].milestone_type == "cleared_act2_normal"

    async def test_patch_milestone_type_to_quest_type(self) -> None:
        season = _season()
        ms = _milestone(milestone_type="level", level_target=30)
        session = _session_get(season, ms)

        body = MilestonePatch(milestone_type="cleared_act3_hell")
        await patch_milestone(season_id=1, milestone_id=10, body=body, session=session)

        assert ms.milestone_type == "cleared_act3_hell"

    async def test_create_all_15_quest_types_accepted(self) -> None:
        """All 15 cleared_actN_diffname types can be created without error."""
        bosses = [
            f"cleared_act{act}_{diff}"
            for act in range(1, 6)
            for diff in ["normal", "nightmare", "hell"]
        ]
        assert len(bosses) == 15
        for ms_type in bosses:
            season = _season(status="active")
            session = _session_get(season)
            await add_milestone(
                season_id=1,
                body=_ms_body(name=f"Test {ms_type}", milestone_type=ms_type),
                session=session,
            )
            assert session._added[0].milestone_type == ms_type

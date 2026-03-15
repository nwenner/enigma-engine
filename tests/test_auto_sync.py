from __future__ import annotations

"""
Unit tests for backend.services.auto_sync.

Coverage:
  _snapshot_source
      - all three hooks called (grail, seasons, boss summon)
      - returns (snapshot_dir, file_count)
      - snapshot created with game_close label
      - individual hook failures are isolated (snapshot still succeeds)

  _auto_push_to_dest
      - pc_to_deck pushes to deck; deck_to_pc pushes to pc
      - is_windows set correctly per dest
      - conn failure logs and returns without raising
      - push failure logs and returns without raising

  _push_to_machine (new — mothership auto-push)
      - "pc" → is_windows=True passed to push_snapshot_to_machine
      - "deck" → is_windows=False passed to push_snapshot_to_machine
      - conn failure is swallowed (best-effort)
      - push failure is swallowed (best-effort)

  trigger_mothership_push (new)
      - disabled → no background tasks added
      - both pc+deck enabled → two tasks added
      - only pc enabled → one task for "pc"
      - only deck enabled → one task for "deck"
      - neither machine enabled (but master switch on) → no tasks

  guard_mothership_write (new)
      - disabled → no-op, no exception
      - D2R running on pc → HTTPException 409
      - D2R running on deck → HTTPException 409
      - D2R not running on either → no exception
      - both machines unreachable (None) → no exception
      - pc not in enabled list → pc skipped, only deck checked
      - no machines enabled → no-op, no exception

  _has_new_saves
      - True when any mtime exceeds since + threshold
      - False when all mtimes within threshold
      - None when dest unreachable

  run_auto_sync_watcher (one or two iterations via mocked asyncio.sleep)
      disabled            → D2R not polled
      game-close, dest online   → snapshot taken, push fires immediately
      game-close, dest offline  → snapshot taken, state=pending
      game-close, conflict      → state=conflict, notify fired, no snapshot
      game-close, existing conflict in state → skipped entirely
      game-close, snapshot fails → no push, no pending state written
      game-close, no prior sync  → conflict check skipped, proceeds normally
      pending, dest comes online → push fires, state cleared to idle
      pending, dest still offline → state unchanged
      pending expired            → state cleared to idle, no push
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.auto_sync import (
    _auto_push_to_dest,
    _has_new_saves,
    _push_to_machine,
    _snapshot_source,
    guard_mothership_write,
    run_auto_sync_watcher,
    trigger_mothership_push,
    CONFLICT_THRESHOLD_SECONDS,
    PENDING_EXPIRY_DAYS,
)


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _ctx() -> AsyncMock:
    """Return a re-usable async context-manager mock for AsyncSessionLocal."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


_IDLE = {
    "status": "idle",
    "direction": None,
    "detected_at": None,
    "expires_at": None,
    "reason": None,
}


def _ts(delta_seconds: float = 0.0) -> float:
    """Return a timestamp offset from now."""
    return datetime.now(timezone.utc).timestamp() + delta_seconds


def _dt(delta_seconds: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)


# ─── _snapshot_source ─────────────────────────────────────────────────────────

class TestSnapshotSource:
    """_snapshot_source creates a game_close snapshot and runs all three hooks."""

    def _make_snap(self, tmp_path: Path) -> tuple[MagicMock, Path, MagicMock]:
        snap = MagicMock()
        snap.file_count = 2
        snap.snapshot_path = "backups/pc/snap1"
        snap_dir = tmp_path / "backups" / "pc" / "snap1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 4)
        cfg = MagicMock()
        cfg.data_dir = tmp_path
        return snap, snap_dir, cfg

    def _base_patches(self, snap: MagicMock, cfg: MagicMock, **hook_overrides):
        """Return patch context managers common to all _snapshot_source tests."""
        return (
            patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()),
            patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}),
            patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"),
            patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap),
            patch("backend.services.auto_sync.get_settings", return_value=cfg),
            patch(
                "backend.services.grail_service.process_portal_tab_hook",
                hook_overrides.get("grail", AsyncMock()),
            ),
            patch(
                "backend.services.seasons_service.check_season_milestones",
                hook_overrides.get("seasons", AsyncMock()),
            ),
            patch(
                "backend.services.boss_summon_service.check_boss_summon_progress",
                hook_overrides.get("boss", AsyncMock()),
            ),
        )

    async def test_returns_snapshot_dir_and_file_count(self, tmp_path: Path) -> None:
        snap, snap_dir, cfg = self._make_snap(tmp_path)
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap), \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock), \
             patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", new_callable=AsyncMock):
            result_dir, count = await _snapshot_source("pc", True)

        assert count == 2
        assert result_dir == snap_dir

    async def test_snapshot_created_with_game_close_label(self, tmp_path: Path) -> None:
        snap, _, cfg = self._make_snap(tmp_path)
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap) as mock_cs, \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock), \
             patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", new_callable=AsyncMock):
            await _snapshot_source("pc", True)

        kw = mock_cs.call_args.kwargs
        assert kw["label"] == "game_close"
        assert kw["machine"] == "pc"

    async def test_all_three_hooks_are_called(self, tmp_path: Path) -> None:
        snap, _, cfg = self._make_snap(tmp_path)
        mock_grail = AsyncMock()
        mock_seasons = AsyncMock()
        mock_boss = AsyncMock()

        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap), \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", mock_grail), \
             patch("backend.services.seasons_service.check_season_milestones", mock_seasons), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", mock_boss):
            await _snapshot_source("pc", True)

        mock_grail.assert_awaited_once()
        mock_seasons.assert_awaited_once()
        mock_boss.assert_awaited_once()

    async def test_grail_failure_does_not_propagate(self, tmp_path: Path) -> None:
        snap, _, cfg = self._make_snap(tmp_path)
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap), \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", AsyncMock(side_effect=RuntimeError("grail boom"))), \
             patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", new_callable=AsyncMock):
            _, count = await _snapshot_source("pc", True)  # must not raise

        assert count == 2

    async def test_seasons_failure_does_not_propagate(self, tmp_path: Path) -> None:
        snap, _, cfg = self._make_snap(tmp_path)
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap), \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock), \
             patch("backend.services.seasons_service.check_season_milestones", AsyncMock(side_effect=RuntimeError("seasons boom"))), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", new_callable=AsyncMock):
            _, count = await _snapshot_source("pc", True)

        assert count == 2

    async def test_boss_summon_failure_does_not_propagate(self, tmp_path: Path) -> None:
        snap, _, cfg = self._make_snap(tmp_path)
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock, return_value=snap), \
             patch("backend.services.auto_sync.get_settings", return_value=cfg), \
             patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock), \
             patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock), \
             patch("backend.services.boss_summon_service.check_boss_summon_progress", AsyncMock(side_effect=RuntimeError("boss boom"))):
            _, count = await _snapshot_source("pc", True)

        assert count == 2


# ─── _auto_push_to_dest ───────────────────────────────────────────────────────

class TestAutoPushToDest:
    """_auto_push_to_dest pushes the latest vault snapshot to the correct dest."""

    async def test_pc_to_deck_pushes_to_deck(self) -> None:
        mock_push = AsyncMock(return_value=(0, 2))
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={"host": "deck"}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/deck/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine", mock_push):
            await _auto_push_to_dest("pc_to_deck")

        mock_push.assert_awaited_once()
        _s, machine, _conn, _dir, is_windows = mock_push.call_args[0]
        assert machine == "deck"
        assert is_windows is False

    async def test_deck_to_pc_pushes_to_pc(self) -> None:
        mock_push = AsyncMock(return_value=(0, 2))
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={"host": "pc"}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/pc/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine", mock_push):
            await _auto_push_to_dest("deck_to_pc")

        _s, machine, _conn, _dir, is_windows = mock_push.call_args[0]
        assert machine == "pc"
        assert is_windows is True

    async def test_conn_failure_does_not_propagate(self) -> None:
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", AsyncMock(side_effect=ValueError("no creds"))):
            await _auto_push_to_dest("pc_to_deck")  # must not raise

    async def test_push_failure_does_not_propagate(self) -> None:
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine", AsyncMock(side_effect=RuntimeError("SSH down"))):
            await _auto_push_to_dest("pc_to_deck")  # must not raise


# ─── _has_new_saves ───────────────────────────────────────────────────────────

class TestHasNewSaves:
    """_has_new_saves checks whether a machine has .d2s files newer than a threshold."""

    async def test_returns_true_when_mtime_exceeds_threshold(self) -> None:
        since = _dt(-300)  # 5 minutes ago
        # file modified 10 seconds AFTER the threshold window → should be "new"
        new_mtime = _ts(-(300 - CONFLICT_THRESHOLD_SECONDS - 10))

        with patch("backend.services.auto_sync._get_d2s_mtimes", AsyncMock(return_value=[new_mtime])):
            result = await _has_new_saves("deck", False, since)

        assert result is True

    async def test_returns_false_when_mtime_within_threshold(self) -> None:
        since = _dt(-300)
        # file modified only a few seconds after `since` — within threshold
        within_mtime = since.timestamp() + CONFLICT_THRESHOLD_SECONDS - 1

        with patch("backend.services.auto_sync._get_d2s_mtimes", AsyncMock(return_value=[within_mtime])):
            result = await _has_new_saves("deck", False, since)

        assert result is False

    async def test_returns_none_when_dest_unreachable(self) -> None:
        with patch("backend.services.auto_sync._get_d2s_mtimes", AsyncMock(return_value=None)):
            result = await _has_new_saves("deck", False, _dt())

        assert result is None


# ─── run_auto_sync_watcher helpers ────────────────────────────────────────────

def _make_setting_fn(enabled: bool = True, interval: int = 30):
    """Return an async side_effect for _get_autosync_setting."""
    async def _fn(key: str) -> str | None:
        if key == "autosync_enabled":
            return "true" if enabled else "false"
        if key == "autosync_poll_interval":
            return str(interval)
        return None
    return _fn


def _make_check_d2r(pc_returns: list, deck_returns: list):
    """Return an AsyncMock for _check_d2r that returns pc_returns / deck_returns per machine."""
    pc_iter = iter(pc_returns)
    deck_iter = iter(deck_returns)

    async def _fn(machine: str, is_windows: bool) -> bool | None:
        if machine == "pc":
            return next(pc_iter, None)
        return next(deck_iter, None)

    return AsyncMock(side_effect=_fn)


async def _run_watcher_n(n: int, **patches) -> None:
    """Run n iterations of run_auto_sync_watcher then raise CancelledError."""
    call_count = 0

    async def _sleep(_n: int) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= n:
            raise asyncio.CancelledError()

    with patch("backend.services.auto_sync.asyncio.sleep", side_effect=_sleep):
        ctx_mgr = patch("backend.services.auto_sync.asyncio.create_task", side_effect=lambda c: c.close() or MagicMock())
        with ctx_mgr:
            for key, val in patches.items():
                pass  # patches applied in caller via with-stack
            try:
                await run_auto_sync_watcher()
            except asyncio.CancelledError:
                pass


# ─── run_auto_sync_watcher — disabled ─────────────────────────────────────────

class TestWatcherDisabled:

    async def test_disabled_does_not_poll_d2r(self) -> None:
        """When auto-sync is disabled, D2R state must never be checked."""
        mock_check = AsyncMock()

        with patch("backend.services.auto_sync._get_autosync_setting",
                   AsyncMock(side_effect=_make_setting_fn(enabled=False))), \
             patch("backend.services.auto_sync._check_d2r", mock_check), \
             patch("backend.services.auto_sync.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError())):
            try:
                await run_auto_sync_watcher()
            except asyncio.CancelledError:
                pass

        mock_check.assert_not_called()


# ─── run_auto_sync_watcher — game-close scenarios ─────────────────────────────

class TestWatcherGameClose:
    """
    Tests for the True→False D2R transition.
    Requires 2 iterations: iter 1 sets prev=True, iter 2 detects the close.
    """

    def _common_patches(
        self,
        *,
        state=None,
        last_sync_time=None,
        has_new_saves=False,
        snapshot_result=(Path("/fake/snap"), 3),
        dest_mtimes: list | None = None,  # None=offline, list=online
    ):
        """Return a dict of patch targets → mocks for game-close tests."""
        set_state = AsyncMock()
        return {
            "_get_autosync_setting": AsyncMock(side_effect=_make_setting_fn()),
            "_get_state": AsyncMock(return_value=state or dict(_IDLE)),
            "_set_state": set_state,
            "_get_last_sync_time": AsyncMock(return_value=last_sync_time),
            "_has_new_saves": AsyncMock(return_value=has_new_saves),
            "_snapshot_source": AsyncMock(return_value=snapshot_result),
            "_get_d2s_mtimes": AsyncMock(return_value=dest_mtimes),
            "_auto_push_to_dest": AsyncMock(),
            "notify_conflict": AsyncMock(),
        }, set_state

    async def _run_two_iters(self, *, pc_d2r: list, deck_d2r: list, patches: dict) -> None:
        """Run the watcher for 2 iterations with the given mock patches."""
        sleep_count = 0

        async def _sleep(_n):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        check_d2r = _make_check_d2r(pc_d2r, deck_d2r)

        with patch("backend.services.auto_sync._get_autosync_setting", patches["_get_autosync_setting"]), \
             patch("backend.services.auto_sync._get_state", patches["_get_state"]), \
             patch("backend.services.auto_sync._set_state", patches["_set_state"]), \
             patch("backend.services.auto_sync._get_last_sync_time", patches["_get_last_sync_time"]), \
             patch("backend.services.auto_sync._has_new_saves", patches["_has_new_saves"]), \
             patch("backend.services.auto_sync._snapshot_source", patches["_snapshot_source"]), \
             patch("backend.services.auto_sync._get_d2s_mtimes", patches["_get_d2s_mtimes"]), \
             patch("backend.services.auto_sync._auto_push_to_dest", patches["_auto_push_to_dest"]), \
             patch("backend.services.auto_sync.notify_conflict", patches["notify_conflict"]), \
             patch("backend.services.auto_sync._check_d2r", check_d2r), \
             patch("backend.services.auto_sync.asyncio.sleep", side_effect=_sleep), \
             patch("backend.services.auto_sync.asyncio.create_task", side_effect=lambda c: c.close() or MagicMock()):
            try:
                await run_auto_sync_watcher()
            except asyncio.CancelledError:
                pass

    async def test_dest_online_push_fires_immediately(self) -> None:
        """Game closes on PC, Deck is reachable → snapshot + push task created."""
        patches, set_state = self._common_patches(
            last_sync_time=_dt(-3600),  # synced 1 hour ago
            has_new_saves=False,        # no conflict
            dest_mtimes=[1234.0],       # deck online
        )
        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_snapshot_source"].assert_awaited_once_with("pc", True)
        patches["_auto_push_to_dest"].assert_called_once_with("pc_to_deck")

    async def test_dest_offline_records_pending_state(self) -> None:
        """Game closes on PC, Deck offline → snapshot taken, state set to pending."""
        patches, set_state = self._common_patches(
            last_sync_time=_dt(-3600),
            has_new_saves=False,
            dest_mtimes=None,  # deck offline
        )
        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_snapshot_source"].assert_awaited_once_with("pc", True)
        patches["_auto_push_to_dest"].assert_not_called()

        # _set_state must have been called with status=pending
        set_state_calls = [c.args[0] for c in set_state.call_args_list]
        pending_calls = [s for s in set_state_calls if s.get("status") == "pending"]
        assert len(pending_calls) == 1
        assert pending_calls[0]["direction"] == "pc_to_deck"
        assert pending_calls[0]["expires_at"] is not None

    async def test_conflict_detected_sets_conflict_state_and_notifies(self) -> None:
        """Dest has new saves since last sync → conflict state + notify, no snapshot."""
        patches, set_state = self._common_patches(
            last_sync_time=_dt(-3600),
            has_new_saves=True,   # dest has new saves → conflict
        )
        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_snapshot_source"].assert_not_called()
        patches["_auto_push_to_dest"].assert_not_called()
        patches["notify_conflict"].assert_called_once()

        set_state_calls = [c.args[0] for c in set_state.call_args_list]
        conflict_calls = [s for s in set_state_calls if s.get("status") == "conflict"]
        assert len(conflict_calls) == 1

    async def test_existing_conflict_state_skips_trigger(self) -> None:
        """If there's already an unresolved conflict in state, game-close is ignored."""
        existing_conflict = {
            "status": "conflict", "direction": None,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None, "reason": "prior conflict",
        }
        patches, set_state = self._common_patches(state=existing_conflict)
        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_snapshot_source"].assert_not_called()
        patches["_auto_push_to_dest"].assert_not_called()
        patches["notify_conflict"].assert_not_called()

    async def test_snapshot_failure_skips_push_and_pending(self) -> None:
        """If _snapshot_source raises, no push fires and no pending state is written."""
        patches, set_state = self._common_patches(
            last_sync_time=_dt(-3600),
            has_new_saves=False,
        )
        patches["_snapshot_source"] = AsyncMock(side_effect=RuntimeError("SSH timeout"))

        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_auto_push_to_dest"].assert_not_called()
        set_state_calls = [c.args[0] for c in set_state.call_args_list]
        pending_calls = [s for s in set_state_calls if s.get("status") == "pending"]
        assert len(pending_calls) == 0

    async def test_no_prior_sync_skips_conflict_check_and_proceeds(self) -> None:
        """When last_sync_time is None, conflict check is skipped and snapshot is taken."""
        patches, _ = self._common_patches(
            last_sync_time=None,    # never synced before
            dest_mtimes=[1234.0],   # deck online
        )
        await self._run_two_iters(
            pc_d2r=[True, False],
            deck_d2r=[False, False],
            patches=patches,
        )

        patches["_has_new_saves"].assert_not_called()
        patches["_snapshot_source"].assert_awaited_once()
        patches["_auto_push_to_dest"].assert_called_once()


# ─── run_auto_sync_watcher — pending resolution ───────────────────────────────

class TestWatcherPending:
    """Tests for the pending-state resolution path (dest comes back online)."""

    async def _run_one_iter_pending(self, *, state: dict, dest_mtimes: list | None) -> AsyncMock:
        """Run one iteration with a pending state and return the _set_state mock."""
        set_state = AsyncMock()
        push = AsyncMock()
        sleep_fired = False

        async def _sleep(_n):
            nonlocal sleep_fired
            sleep_fired = True
            raise asyncio.CancelledError()

        with patch("backend.services.auto_sync._get_autosync_setting", AsyncMock(side_effect=_make_setting_fn())), \
             patch("backend.services.auto_sync._get_state", AsyncMock(return_value=state)), \
             patch("backend.services.auto_sync._set_state", set_state), \
             patch("backend.services.auto_sync._get_d2s_mtimes", AsyncMock(return_value=dest_mtimes)), \
             patch("backend.services.auto_sync._auto_push_to_dest", push), \
             patch("backend.services.auto_sync._check_d2r", AsyncMock(return_value=None)), \
             patch("backend.services.auto_sync.asyncio.sleep", side_effect=_sleep), \
             patch("backend.services.auto_sync.asyncio.create_task", side_effect=lambda c: c.close() or MagicMock()):
            try:
                await run_auto_sync_watcher()
            except asyncio.CancelledError:
                pass

        return set_state, push

    async def test_pending_dest_online_fires_push_and_clears_state(self) -> None:
        """When dest comes online while state=pending, push fires and state → idle."""
        state = {
            "status": "pending", "direction": "pc_to_deck",
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=PENDING_EXPIRY_DAYS)).isoformat(),
            "reason": "Waiting for deck to come online",
        }
        set_state, push = await self._run_one_iter_pending(
            state=state, dest_mtimes=[1234.0],  # deck now online
        )

        push.assert_called_once_with("pc_to_deck")
        set_state_calls = [c.args[0] for c in set_state.call_args_list]
        idle_calls = [s for s in set_state_calls if s.get("status") == "idle"]
        assert len(idle_calls) >= 1

    async def test_pending_dest_still_offline_does_not_push(self) -> None:
        """When dest is still offline, pending state is preserved and no push fires."""
        state = {
            "status": "pending", "direction": "pc_to_deck",
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=PENDING_EXPIRY_DAYS)).isoformat(),
            "reason": "Waiting for deck to come online",
        }
        set_state, push = await self._run_one_iter_pending(
            state=state, dest_mtimes=None,  # deck still offline
        )

        push.assert_not_called()

    async def test_pending_expired_clears_state_without_push(self) -> None:
        """Expired pending state is cleared to idle; no push is triggered."""
        expired_state = {
            "status": "pending", "direction": "pc_to_deck",
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),  # 1 day ago
            "reason": "Waiting for deck to come online",
        }
        set_state, push = await self._run_one_iter_pending(
            state=expired_state, dest_mtimes=None,
        )

        push.assert_not_called()
        set_state_calls = [c.args[0] for c in set_state.call_args_list]
        idle_calls = [s for s in set_state_calls if s.get("status") == "idle"]
        assert len(idle_calls) >= 1


# ─── _push_to_machine ─────────────────────────────────────────────────────────

class TestPushToMachine:
    """_push_to_machine is the best-effort per-machine push used by trigger_mothership_push."""

    async def test_pc_passes_is_windows_true(self) -> None:
        """Destination 'pc' must set is_windows=True when calling push_snapshot_to_machine."""
        mock_push = AsyncMock(return_value=(0, 2))
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={"host": "pc"}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/pc/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine", mock_push):
            await _push_to_machine("pc")

        mock_push.assert_awaited_once()
        _sess, machine, _conn, _dir, is_windows = mock_push.call_args[0]
        assert machine == "pc"
        assert is_windows is True

    async def test_deck_passes_is_windows_false(self) -> None:
        """Destination 'deck' must set is_windows=False when calling push_snapshot_to_machine."""
        mock_push = AsyncMock(return_value=(0, 2))
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={"host": "deck"}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/deck/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine", mock_push):
            await _push_to_machine("deck")

        mock_push.assert_awaited_once()
        _sess, machine, _conn, _dir, is_windows = mock_push.call_args[0]
        assert machine == "deck"
        assert is_windows is False

    async def test_conn_failure_does_not_raise(self) -> None:
        """SSH connection errors are caught and swallowed — endpoint must not fail."""
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs",
                   AsyncMock(side_effect=ValueError("no creds configured"))):
            await _push_to_machine("pc")  # must not raise

    async def test_push_failure_does_not_raise(self) -> None:
        """push_snapshot_to_machine errors (e.g. D2R running) are swallowed."""
        with patch("backend.services.auto_sync.AsyncSessionLocal", return_value=_ctx()), \
             patch("backend.services.auto_sync._get_conn_kwargs", new_callable=AsyncMock, return_value={}), \
             patch("backend.services.auto_sync._get_setting", new_callable=AsyncMock, return_value="/saves"), \
             patch("backend.services.backup_manager.push_snapshot_to_machine",
                   AsyncMock(side_effect=RuntimeError("D2R is currently running on PC"))):
            await _push_to_machine("pc")  # must not raise


# ─── trigger_mothership_push ──────────────────────────────────────────────────

def _setting_side_effect(**values):
    """AsyncMock side_effect for _get_setting(session, key) returning keyed values."""
    async def _fn(_session, key: str) -> str | None:
        return values.get(key)
    return AsyncMock(side_effect=_fn)


class TestTriggerMothershipPush:
    """trigger_mothership_push schedules background tasks based on auto-sync settings."""

    async def test_disabled_schedules_no_tasks(self) -> None:
        """Master switch off → add_task never called."""
        bg = MagicMock()
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(autosync_enabled="false")):
            await trigger_mothership_push(bg, session)
        bg.add_task.assert_not_called()

    async def test_both_enabled_schedules_two_tasks(self) -> None:
        """Both pc and deck enabled → two add_task calls, one per machine."""
        bg = MagicMock()
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="true",
                       autosync_deck_enabled="true",
                   )):
            await trigger_mothership_push(bg, session)

        assert bg.add_task.call_count == 2
        machines = {call.args[1] for call in bg.add_task.call_args_list}
        assert machines == {"pc", "deck"}

    async def test_only_pc_enabled_schedules_pc_task(self) -> None:
        """Only pc enabled → exactly one task for 'pc'."""
        bg = MagicMock()
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="true",
                       autosync_deck_enabled="false",
                   )):
            await trigger_mothership_push(bg, session)

        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[1] == "pc"

    async def test_only_deck_enabled_schedules_deck_task(self) -> None:
        """Only deck enabled → exactly one task for 'deck'."""
        bg = MagicMock()
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="false",
                       autosync_deck_enabled="true",
                   )):
            await trigger_mothership_push(bg, session)

        assert bg.add_task.call_count == 1
        assert bg.add_task.call_args.args[1] == "deck"

    async def test_neither_machine_enabled_schedules_no_tasks(self) -> None:
        """Master switch on but both per-machine toggles off → no tasks."""
        bg = MagicMock()
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="false",
                       autosync_deck_enabled="false",
                   )):
            await trigger_mothership_push(bg, session)
        bg.add_task.assert_not_called()


# ─── guard_mothership_write ───────────────────────────────────────────────────

class TestGuardMothershipWrite:
    """guard_mothership_write blocks writes when D2R is detected running on any enabled machine."""

    def _check_d2r_fn(self, **machine_states: bool | None):
        """Return an AsyncMock side_effect for _check_d2r(machine, is_windows)."""
        async def _fn(machine: str, _is_windows: bool) -> bool | None:
            return machine_states.get(machine)
        return AsyncMock(side_effect=_fn)

    async def test_disabled_does_not_raise(self) -> None:
        """Auto-sync disabled → guard is a no-op regardless of D2R state."""
        session = AsyncMock()
        mock_check = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(autosync_enabled="false")), \
             patch("backend.services.auto_sync._check_d2r", mock_check):
            await guard_mothership_write(session)  # must not raise
        mock_check.assert_not_called()

    async def test_d2r_running_on_pc_raises_409(self) -> None:
        """D2R confirmed running on PC → HTTPException with status 409."""
        from fastapi import HTTPException
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="true",
                       autosync_deck_enabled="false",
                   )), \
             patch("backend.services.auto_sync._check_d2r",
                   self._check_d2r_fn(pc=True)):
            with pytest.raises(HTTPException) as exc_info:
                await guard_mothership_write(session)
        assert exc_info.value.status_code == 409
        assert "PC" in exc_info.value.detail

    async def test_d2r_running_on_deck_raises_409(self) -> None:
        """D2R confirmed running on Deck → HTTPException with status 409."""
        from fastapi import HTTPException
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="false",
                       autosync_deck_enabled="true",
                   )), \
             patch("backend.services.auto_sync._check_d2r",
                   self._check_d2r_fn(deck=True)):
            with pytest.raises(HTTPException) as exc_info:
                await guard_mothership_write(session)
        assert exc_info.value.status_code == 409
        assert "DECK" in exc_info.value.detail

    async def test_d2r_not_running_does_not_raise(self) -> None:
        """Both machines reachable and not running → no exception."""
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="true",
                       autosync_deck_enabled="true",
                   )), \
             patch("backend.services.auto_sync._check_d2r",
                   self._check_d2r_fn(pc=False, deck=False)):
            await guard_mothership_write(session)  # must not raise

    async def test_unreachable_machines_do_not_raise(self) -> None:
        """None return (SSH timeout) is treated as 'not running' — don't block the user."""
        session = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="true",
                       autosync_deck_enabled="true",
                   )), \
             patch("backend.services.auto_sync._check_d2r",
                   self._check_d2r_fn(pc=None, deck=None)):
            await guard_mothership_write(session)  # must not raise

    async def test_unenabled_machine_not_checked(self) -> None:
        """A machine whose per-machine toggle is off is never SSH-checked, even if D2R
        would be running on it — it's not in scope for auto-sync."""
        session = AsyncMock()
        mock_check = self._check_d2r_fn(pc=True, deck=False)
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="false",   # PC not enrolled
                       autosync_deck_enabled="true",
                   )), \
             patch("backend.services.auto_sync._check_d2r", mock_check):
            await guard_mothership_write(session)  # must not raise (only deck checked)

        # _check_d2r should only have been called for "deck"
        checked = [call.args[0] for call in mock_check.call_args_list]
        assert "pc" not in checked
        assert "deck" in checked

    async def test_no_machines_enrolled_is_noop(self) -> None:
        """Master switch on but both per-machine toggles off → no D2R check, no exception."""
        session = AsyncMock()
        mock_check = AsyncMock()
        with patch("backend.services.auto_sync._get_setting",
                   _setting_side_effect(
                       autosync_enabled="true",
                       autosync_pc_enabled="false",
                       autosync_deck_enabled="false",
                   )), \
             patch("backend.services.auto_sync._check_d2r", mock_check):
            await guard_mothership_write(session)  # must not raise
        mock_check.assert_not_called()

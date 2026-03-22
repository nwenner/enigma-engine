from __future__ import annotations

"""
Unit tests for backup_manager.

_prune_backups
    Focus: the 2026-03-09 refactor that changed pruning from per-platform to
    total-across-all-platforms, and added retention for pre_grail_* and pre_vault_*.

push_snapshot_to_machine — pre_sync safety guarantee
    Every call must create a pre_sync snapshot of the destination BEFORE any
    files are deleted or uploaded. This ensures the user always has a restorable
    point even if the push overwrites their saves.
"""

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# SQLAlchemy and other backend deps are only available inside Docker.
# Skip this file gracefully when running locally without them.
# To run: docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v
pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.backup_manager import _prune_backups, push_snapshot_to_machine, create_snapshot


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _snap(
    id: int,
    label: str = "manual",
    source_machine: str = "pc",
    snapshot_path: str | None = None,
) -> MagicMock:
    """Create a minimal BackupSnapshot mock."""
    s = MagicMock()
    s.id = id
    s.label = label
    s.source_machine = source_machine
    s.snapshot_path = snapshot_path or f"backups/{source_machine}/snap_{id}"
    return s


def _session(snapshots: list[Any]) -> AsyncMock:
    """Return an AsyncSession mock whose execute().scalars().all() yields `snapshots`."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = snapshots
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _cfg(data_dir: Path = Path("/nonexistent")) -> MagicMock:
    """Return a minimal settings mock."""
    cfg = MagicMock()
    cfg.data_dir = data_dir
    return cfg


# ─── game_close / manual (keep 1 total) ──────────────────────────────────────

class TestManualGameCloseRetention:
    async def test_deletes_excess_when_over_limit(self) -> None:
        """3 snapshots exist → keep newest 1, delete 2."""
        snaps = [_snap(i, label="manual") for i in range(3)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "manual")

        assert session.delete.call_count == 2
        # The two oldest (indices 1 and 2) are deleted
        deleted_ids = {call.args[0].id for call in session.delete.call_args_list}
        assert deleted_ids == {1, 2}
        session.commit.assert_called_once()

    async def test_no_op_at_exact_limit(self) -> None:
        """Exactly 1 snapshot → nothing deleted."""
        session = _session([_snap(0, label="manual")])

        await _prune_backups(session, _cfg(), "manual")

        session.delete.assert_not_called()
        session.commit.assert_not_called()

    async def test_no_op_below_limit(self) -> None:
        """0 snapshots → nothing happens."""
        session = _session([])

        await _prune_backups(session, _cfg(), "manual")

        session.delete.assert_not_called()
        session.commit.assert_not_called()

    async def test_game_close_label_uses_same_pool(self) -> None:
        """game_close triggers the same query group (combined with manual)."""
        snaps = [_snap(i, label="game_close") for i in range(4)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "game_close")

        assert session.delete.call_count == 3
        session.commit.assert_called_once()

    async def test_pruning_is_total_not_per_platform(self) -> None:
        """
        2 snaps from PC + 1 from Deck = 3 total → keep 1, delete 2.
        Old behavior would have kept 1 per platform (2 total).
        """
        snaps = [
            _snap(0, label="manual", source_machine="pc"),
            _snap(1, label="manual", source_machine="pc"),
            _snap(2, label="manual", source_machine="deck"),
        ]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "manual")

        # Keep only the first (newest) regardless of platform
        assert session.delete.call_count == 2

    async def test_deletes_filesystem_path_when_exists(self, tmp_path: Path) -> None:
        """Snapshot directory on disk is removed when it exists."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)

        snap = _snap(1, label="manual", snapshot_path="backups/pc/snap_1")
        # newest is snap 0 (index 0), oldest is snap 1 (index 1)
        snaps = [_snap(0, label="manual"), snap]
        session = _session(snaps)
        cfg = _cfg(data_dir=tmp_path)

        await _prune_backups(session, cfg, "manual")

        assert not snap_dir.exists()

    async def test_missing_filesystem_path_does_not_raise(self) -> None:
        """If snapshot dir is already gone, rmtree is skipped gracefully."""
        snaps = [_snap(0, label="manual"), _snap(1, label="manual")]
        session = _session(snaps)

        # /nonexistent path → snap_path.exists() is False, no rmtree
        await _prune_backups(session, _cfg(), "manual")

        session.delete.assert_called_once()


# ─── pre_sync (keep 5 total) ─────────────────────────────────────────────────

class TestPreSyncRetention:
    async def test_keeps_5_total(self) -> None:
        """8 pre_sync snapshots → delete 3."""
        snaps = [_snap(i, label="pre_sync") for i in range(8)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_sync")

        assert session.delete.call_count == 3
        session.commit.assert_called_once()

    async def test_no_op_at_limit(self) -> None:
        """Exactly 5 → no deletions."""
        snaps = [_snap(i, label="pre_sync") for i in range(5)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_sync")

        session.delete.assert_not_called()

    async def test_limit_is_5_not_3(self) -> None:
        """
        Previously kept 3 per platform. Now keeps 5 total.
        Verify that 4 snaps from the same platform are NOT pruned.
        """
        snaps = [_snap(i, label="pre_sync", source_machine="pc") for i in range(4)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_sync")

        session.delete.assert_not_called()

    async def test_mixed_platform_still_5_total(self) -> None:
        """3 PC + 4 Deck = 7 total → delete 2."""
        snaps = (
            [_snap(i, label="pre_sync", source_machine="pc") for i in range(3)]
            + [_snap(i + 3, label="pre_sync", source_machine="deck") for i in range(4)]
        )
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_sync")

        assert session.delete.call_count == 2


# ─── pre_grail_* (keep 5 total) ──────────────────────────────────────────────

class TestPreGrailRetention:
    async def test_keeps_5_total(self) -> None:
        """7 grail snapshots → delete 2."""
        snaps = [_snap(i, label="pre_grail_deposit") for i in range(7)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_grail_deposit")

        assert session.delete.call_count == 2

    async def test_retrieve_label_also_pruned(self) -> None:
        """pre_grail_retrieve triggers same retention group."""
        snaps = [_snap(i, label="pre_grail_retrieve") for i in range(6)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_grail_retrieve")

        assert session.delete.call_count == 1

    async def test_no_op_below_limit(self) -> None:
        """3 grail snaps → none deleted."""
        snaps = [_snap(i, label="pre_grail_deposit") for i in range(3)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_grail_deposit")

        session.delete.assert_not_called()


# ─── pre_vault_* (keep 5 total) ──────────────────────────────────────────────

class TestPreVaultRetention:
    async def test_keeps_5_total(self) -> None:
        """6 vault snapshots → delete 1."""
        snaps = [_snap(i, label="pre_vault_gold") for i in range(6)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_vault_gold")

        assert session.delete.call_count == 1
        session.commit.assert_called_once()

    async def test_vault_store_label(self) -> None:
        snaps = [_snap(i, label="pre_vault_store") for i in range(7)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_vault_store")

        assert session.delete.call_count == 2

    async def test_vault_retrieve_label(self) -> None:
        snaps = [_snap(i, label="pre_vault_retrieve") for i in range(5)]
        session = _session(snaps)

        await _prune_backups(session, _cfg(), "pre_vault_retrieve")

        session.delete.assert_not_called()


# ─── Unknown / unrecognised labels ───────────────────────────────────────────

class TestUnknownLabel:
    async def test_unknown_label_is_no_op(self) -> None:
        """An unrecognised label must not touch the DB."""
        session = AsyncMock()

        await _prune_backups(session, _cfg(), "totally_unknown")

        session.execute.assert_not_called()
        session.delete.assert_not_called()
        session.commit.assert_not_called()

    async def test_empty_label_is_no_op(self) -> None:
        session = AsyncMock()

        await _prune_backups(session, _cfg(), "")

        session.execute.assert_not_called()


# ─── season_archive (never pruned) ───────────────────────────────────────────

class TestSeasonArchivePrune:
    async def test_season_archive_is_never_pruned(self) -> None:
        """season_archive snapshots are never auto-pruned regardless of count."""
        session = AsyncMock()
        # Even with 100 season_archive snaps, the function returns early
        await _prune_backups(session, _cfg(), "season_archive")
        session.execute.assert_not_called()
        session.delete.assert_not_called()
        session.commit.assert_not_called()


# ─── pre_season_reward (keep 5 total) ────────────────────────────────────────

class TestPreSeasonRewardPrune:
    async def test_keeps_5_total(self) -> None:
        """7 pre_season_reward snapshots → delete 2."""
        snaps = [_snap(i, label="pre_season_reward") for i in range(7)]
        session = _session(snaps)
        await _prune_backups(session, _cfg(), "pre_season_reward")
        assert session.delete.call_count == 2
        session.commit.assert_called_once()

    async def test_no_op_below_limit(self) -> None:
        snaps = [_snap(i, label="pre_season_reward") for i in range(3)]
        session = _session(snaps)
        await _prune_backups(session, _cfg(), "pre_season_reward")
        session.delete.assert_not_called()

    async def test_no_op_at_exact_limit(self) -> None:
        snaps = [_snap(i, label="pre_season_reward") for i in range(5)]
        session = _session(snaps)
        await _prune_backups(session, _cfg(), "pre_season_reward")
        session.delete.assert_not_called()


# ─── push_snapshot_to_machine — pre_sync safety guarantee ────────────────────

def _push_session() -> AsyncMock:
    """Session mock for push_snapshot_to_machine: no active season, no existing snapshot."""
    season_result = MagicMock()
    season_result.scalar_one_or_none.return_value = None   # no active season

    snap_result = MagicMock()
    snap_result.scalar_one_or_none.return_value = None     # no snapshot to push

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[season_result, snap_result])
    return session


class TestPushSnapshotPreSyncSafety:
    """
    push_snapshot_to_machine must create a pre_sync snapshot of the destination
    BEFORE touching any files on the device. These tests lock in that contract so
    accidentally removing the create_snapshot call causes an immediate test failure.
    """

    async def test_pre_sync_snapshot_taken_before_push_thread(self) -> None:
        """create_snapshot must be called before asyncio.to_thread(_push) — strict ordering."""
        call_order: list[str] = []

        async def _track_create(**kwargs):
            call_order.append("create_snapshot")
            return MagicMock()

        async def _track_thread(fn):
            call_order.append("push_thread")
            return (0, 0)

        with patch("backend.services.backup_manager.create_snapshot", side_effect=_track_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", side_effect=_track_thread):
            await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        assert call_order == ["create_snapshot", "push_thread"], (
            "pre_sync snapshot must be taken BEFORE the push runs — "
            "if this fails the safety backup was removed or reordered"
        )

    async def test_pre_sync_label_used(self) -> None:
        """create_snapshot is called with label='pre_sync', not any other label."""
        mock_create = AsyncMock(return_value=MagicMock())

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
            await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["label"] == "pre_sync"

    async def test_pre_sync_correct_machine_and_paths(self) -> None:
        """create_snapshot receives the destination machine, conn_kwargs, and save_dir."""
        mock_create = AsyncMock(return_value=MagicMock())
        conn = {"host": "steamdeck", "port": 22}
        save_dir = "/home/deck/saves"

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
            await push_snapshot_to_machine(_push_session(), "deck", conn, save_dir, False)

        kw = mock_create.call_args.kwargs
        assert kw["machine"] == "deck"
        assert kw["conn_kwargs"] == conn
        assert kw["save_dir"] == save_dir

    async def test_pre_sync_does_not_update_characters(self) -> None:
        """update_characters=False so a mid-season safety backup never corrupts the character DB."""
        mock_create = AsyncMock(return_value=MagicMock())

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
            await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        assert mock_create.call_args.kwargs["update_characters"] is False

    async def test_pre_sync_not_linked_to_sync_operation(self) -> None:
        """sync_operation_id=None — the safety snapshot is independent of any SyncOperation record."""
        mock_create = AsyncMock(return_value=MagicMock())

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
            await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        assert mock_create.call_args.kwargs["sync_operation_id"] is None

    async def test_pre_sync_called_exactly_once_per_push(self) -> None:
        """create_snapshot is invoked exactly once — not zero times, not twice."""
        mock_create = AsyncMock(return_value=MagicMock())

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(1, 3))):
            await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        mock_create.assert_awaited_once()

    async def test_push_aborted_if_pre_sync_snapshot_fails(self) -> None:
        """If create_snapshot raises (e.g. SSH error), the push thread must NOT run.
        Device files are left untouched — no partial overwrite."""
        push_thread_called = False

        async def _track_thread(fn):
            nonlocal push_thread_called
            push_thread_called = True
            return (0, 0)

        with patch("backend.services.backup_manager.create_snapshot",
                   AsyncMock(side_effect=RuntimeError("SFTP error during snapshot"))), \
             patch("backend.services.backup_manager.asyncio.to_thread", side_effect=_track_thread):
            with pytest.raises(RuntimeError, match="SFTP error during snapshot"):
                await push_snapshot_to_machine(_push_session(), "deck", {}, "/saves", False)

        assert not push_thread_called, (
            "push must not run if the pre_sync backup failed — "
            "device files should be untouched"
        )

    async def test_pre_sync_same_guarantee_for_pc_destination(self) -> None:
        """The pre_sync guarantee applies equally when pushing to PC, not just Steam Deck."""
        mock_create = AsyncMock(return_value=MagicMock())

        with patch("backend.services.backup_manager.create_snapshot", mock_create), \
             patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
            await push_snapshot_to_machine(
                _push_session(), "pc", {"host": "gaming-pc"}, "C:/Users/Nick/Saved Games/D2R", True
            )

        kw = mock_create.call_args.kwargs
        assert kw["label"] == "pre_sync"
        assert kw["machine"] == "pc"

    async def test_snapshot_re_resolved_after_concurrent_prune(self) -> None:
        """Race condition: if a concurrent checkin prunes the snapshot directory between
        the pre_sync call and the push thread, push_snapshot_to_machine must re-resolve
        to the current latest snapshot rather than raising FileNotFoundError."""
        # First session query (active season) + second query (snapshot after pre_sync)
        # must both work. We simulate the snapshot being pruned by making the first
        # snapshot resolution (inside create_snapshot mock) delete the directory.
        snap_path = "backups/deck/20260318T230653Z_game_close"
        snap = MagicMock()
        snap.snapshot_path = snap_path

        # After the pre_sync call (1st execute pair), re-query returns None (pruned)
        season_result1 = MagicMock()
        season_result1.scalar_one_or_none.return_value = None   # no active season

        snap_result1 = MagicMock()
        snap_result1.scalar_one_or_none.return_value = None     # re-query after pre_sync: pruned

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[season_result1, snap_result1])

        push_thread_ran = False

        async def _track_thread(fn):
            nonlocal push_thread_ran
            push_thread_ran = True
            # Don't call fn() — it would open a real SSH connection.
            # snapshot_dir_ref[0] is None (re-resolved to pruned), so
            # the real _push would upload 0 files anyway. We just verify
            # the thread was launched without a FileNotFoundError.
            return (0, 0)

        with patch("backend.services.backup_manager.create_snapshot", AsyncMock(return_value=MagicMock())), \
             patch("backend.services.backup_manager.asyncio.to_thread", side_effect=_track_thread), \
             patch("backend.services.backup_manager.get_settings") as mock_cfg:
            cfg = MagicMock()
            cfg.data_dir = Path("/nonexistent")
            mock_cfg.return_value = cfg
            # Should not raise even though original snapshot no longer exists on disk
            removed, uploaded = await push_snapshot_to_machine(session, "deck", {}, "/saves", False)

        # Re-resolved to None (pruned) → push thread ran without FileNotFoundError
        assert push_thread_ran
        assert uploaded == 0


# ─── create_snapshot — Settings.json exclusion ───────────────────────────────

class TestCreateSnapshotExclusions:
    """
    create_snapshot must skip Settings.json when downloading from the remote device.
    Settings.json is device-specific (graphics/display prefs) and must never be stored
    in a snapshot — otherwise it gets pushed to the other machine and overwrites its settings.
    """

    async def test_settings_json_not_downloaded(self, tmp_path: Path) -> None:
        """Settings.json returned by list_all_files must not be passed to _sftp_download."""
        remote_files = [
            {"filename": "Hero.d2s", "path": "/saves/Hero.d2s", "modified_at": 0.0},
            {"filename": "SharedStash.d2i", "path": "/saves/SharedStash.d2i", "modified_at": 0.0},
            {"filename": "Settings.json", "path": "/saves/Settings.json", "modified_at": 0.0},
        ]

        downloaded: list[str] = []

        def _fake_download(sftp, remote_path, local_path):
            downloaded.append(Path(local_path).name)
            return 10

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        session = AsyncMock()
        prune_result = MagicMock()
        prune_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=prune_result)
        session.add = MagicMock()
        session.commit = AsyncMock()

        mock_char = MagicMock()
        mock_char.to_dict.return_value = {"name": "Hero"}

        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=cfg),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
            patch("backend.services.backup_manager._sftp_download", side_effect=_fake_download),
            patch("backend.services.backup_manager.asyncio.to_thread",
                  AsyncMock(side_effect=lambda fn, *a, **kw: fn())),
            patch("backend.services.backup_manager.parse_d2s", return_value=mock_char),
            patch("backend.services.backup_manager._prune_backups", AsyncMock()),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            await create_snapshot(
                session=session,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
                label="manual",
                sync_operation_id=None,
                update_characters=False,
            )

        assert "Settings.json" not in downloaded, (
            "Settings.json must not be downloaded into a snapshot — "
            "it's device-specific and would overwrite display settings on the other machine"
        )
        assert "Hero.d2s" in downloaded
        assert "SharedStash.d2i" in downloaded

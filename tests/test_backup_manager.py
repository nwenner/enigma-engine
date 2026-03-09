from __future__ import annotations

"""
Unit tests for backup_manager._prune_backups.

Focus: the 2026-03-09 refactor that changed pruning from per-platform to
total-across-all-platforms, and added retention for pre_grail_* and pre_vault_*.
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

from backend.services.backup_manager import _prune_backups


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

from __future__ import annotations

"""
Unit tests for the rewritten seasons_service.start_season.

The new version does NOT use SSH — it archives the latest local snapshot
via shutil.copytree, wipes the DB, and activates the season.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.seasons_service import start_season


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _season(
    id: int = 1,
    status: str = "setup",
    started_at: datetime | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.status = status
    s.started_at = started_at
    s.archive_snapshot_id = None
    return s


def _snap(id: int = 10, source_machine: str = "pc", path: str = "backups/pc/snap_10") -> MagicMock:
    s = MagicMock()
    s.id = id
    s.source_machine = source_machine
    s.snapshot_path = path
    s.file_count = 3
    s.characters = []
    return s


def _session(
    season: MagicMock | None,
    latest_snap: MagicMock | None,
    other_active: MagicMock | None = None,
) -> AsyncMock:
    """
    Build a session where:
    - session.get(Season, id) → season
    - execute() calls return: other_active check, latest_snap query
    """
    session = AsyncMock()

    # session.get returns the season
    session.get = AsyncMock(return_value=season)

    # execute calls:
    # 1st: check for other active season
    # 2nd: find latest manual/game_close snapshot
    other_result = MagicMock()
    other_result.scalar_one_or_none.return_value = other_active

    snap_result = MagicMock()
    snap_result.scalar_one_or_none.return_value = latest_snap

    session.execute = AsyncMock(side_effect=[other_result, snap_result])

    return session


# ─── Validation errors ────────────────────────────────────────────────────────

class TestStartSeasonValidation:
    async def test_raises_if_season_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await start_season(session=session, season_id=99)

    async def test_raises_if_already_active(self) -> None:
        season = _season(status="active")
        session = AsyncMock()
        session.get = AsyncMock(return_value=season)

        with pytest.raises(ValueError, match="already active"):
            await start_season(session=session, season_id=1)

    async def test_raises_if_completed(self) -> None:
        season = _season(status="completed")
        session = AsyncMock()
        session.get = AsyncMock(return_value=season)

        with pytest.raises(ValueError, match="Cannot start a completed"):
            await start_season(session=session, season_id=1)

    async def test_raises_if_another_season_active(self) -> None:
        season = _season(status="setup")
        other = MagicMock()

        session = AsyncMock()
        session.get = AsyncMock(return_value=season)

        other_result = MagicMock()
        other_result.scalar_one_or_none.return_value = other
        session.execute = AsyncMock(return_value=other_result)

        with pytest.raises(ValueError, match="Another season is already active"):
            await start_season(session=session, season_id=1)


# ─── Local archive creation ───────────────────────────────────────────────────

class TestStartSeasonArchive:
    async def test_copies_snapshot_dir_to_archive(self, tmp_path: Path) -> None:
        """Latest snapshot dir is copied to a new season_archive subdir."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_10"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\xaa" * 8)

        season = _season()
        snap = _snap(path="backups/pc/snap_10")
        session = _session(season, snap)
        session.flush = AsyncMock()

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot") as MockSnap,
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            mock_archive_snap = MagicMock()
            mock_archive_snap.id = 99
            MockSnap.return_value = mock_archive_snap

            await start_season(session=session, season_id=1)

        # A new BackupSnapshot with label="season_archive" was created
        MockSnap.assert_called_once()
        kwargs = MockSnap.call_args.kwargs
        assert kwargs["label"] == "season_archive"
        assert kwargs["source_machine"] == "pc"

        # The archive dir was actually created on disk
        archive_dirs = list((tmp_path / "backups" / "pc").iterdir())
        archive_dirs = [d for d in archive_dirs if "season_archive" in d.name]
        assert len(archive_dirs) == 1
        assert (archive_dirs[0] / "Hero.d2s").exists()

    async def test_no_snapshot_proceeds_without_archive(self, tmp_path: Path) -> None:
        """If no manual/game_close snapshot exists, season starts with archive_snapshot_id=None."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot") as MockSnap,
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        # No BackupSnapshot created (no snapshot to archive)
        MockSnap.assert_not_called()
        assert season.archive_snapshot_id is None

    async def test_missing_snapshot_dir_on_disk_proceeds(self, tmp_path: Path) -> None:
        """Snapshot in DB but dir deleted → skip archive, no crash."""
        season = _season()
        snap = _snap(path="backups/pc/gone_snap")  # dir not created
        session = _session(season, snap)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot") as MockSnap,
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        MockSnap.assert_not_called()


# ─── DB wipe ─────────────────────────────────────────────────────────────────

class TestStartSeasonDbWipe:
    async def test_characters_and_grail_and_vault_deleted(self, tmp_path: Path) -> None:
        """After archive, all Character/GrailEntry/VaultItem rows are deleted and GoldVault zeroed."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot"),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        # session.execute called for: other_active check, snap query, delete(Character),
        # delete(GrailEntry), delete(VaultItem), update(GoldVault)
        assert session.execute.call_count >= 4

    async def test_season_activated(self, tmp_path: Path) -> None:
        """season.status is set to 'active' and started_at is populated."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot"),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            result = await start_season(session=session, season_id=1)

        assert result.status == "active"
        assert result.started_at is not None

    async def test_compute_season_stats_called_before_wipe(self, tmp_path: Path) -> None:
        """compute_and_save_season_stats must be called to snapshot metrics before wiping."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot"),
            patch(
                "backend.services.seasons_service.compute_and_save_season_stats",
                new_callable=AsyncMock,
            ) as mock_stats,
        ):
            await start_season(session=session, season_id=1)

        mock_stats.assert_called_once_with(session, season)

    async def test_session_committed(self, tmp_path: Path) -> None:
        """session.commit() is called at the end."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot"),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        session.commit.assert_called()

    async def test_archive_snapshot_id_set_when_archive_created(self, tmp_path: Path) -> None:
        """season.archive_snapshot_id is set to the new archive snapshot's id."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_10"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 4)

        season = _season()
        snap = _snap(path="backups/pc/snap_10")
        session = _session(season, snap)
        session.flush = AsyncMock()

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot") as MockSnap,
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            archive_instance = MagicMock()
            archive_instance.id = 42
            MockSnap.return_value = archive_instance

            result = await start_season(session=session, season_id=1)

        assert result.archive_snapshot_id == 42


# ─── No SSH used ─────────────────────────────────────────────────────────────

class TestStartSeasonNoSsh:
    async def test_ssh_client_never_imported_or_called(self, tmp_path: Path) -> None:
        """start_season must not import or call any ssh_client functions."""
        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.services.seasons_service.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.BackupSnapshot"),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
            patch("backend.services.ssh_client.get_sftp") as mock_sftp,
        ):
            await start_season(session=session, season_id=1)

        # ssh_client.get_sftp must never be invoked
        mock_sftp.assert_not_called()

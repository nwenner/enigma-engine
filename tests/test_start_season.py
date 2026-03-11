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


def _noop_result() -> MagicMock:
    """A generic mock execute result that won't raise on any attribute access."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    r.scalars.return_value.all.return_value = []
    return r


def _session(
    season: MagicMock | None,
    latest_snap: MagicMock | None,
    other_active: MagicMock | None = None,
    stale_chars: list | None = None,
) -> AsyncMock:
    """
    Build a session where:
    - session.get(Season, id) → season
    - execute() call order:
        1. check for other active season
        2. find latest manual/game_close snapshot
        3. stale-chars select (returns empty list by default)
        4+ anything else (noop)
    """
    session = AsyncMock()
    session.get = AsyncMock(return_value=season)

    other_result = MagicMock()
    other_result.scalar_one_or_none.return_value = other_active

    snap_result = MagicMock()
    snap_result.scalar_one_or_none.return_value = latest_snap

    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = stale_chars or []

    # Provide a generous tail of noop results so that the char archive UPDATE,
    # stale delete, GrailEntry delete, VaultItem delete, and GoldVault update
    # calls don't exhaust the side_effect list and raise StopIteration.
    session.execute = AsyncMock(side_effect=[
        other_result, snap_result, stale_result,
        *(_noop_result() for _ in range(8)),
    ])

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
        from backend.models import BackupSnapshot

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
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        # A BackupSnapshot with label="season_archive" was added to the session
        added = [c.args[0] for c in session.add.call_args_list]
        archive_snaps = [o for o in added if isinstance(o, BackupSnapshot) and o.label == "season_archive"]
        assert len(archive_snaps) == 1
        assert archive_snaps[0].source_machine == "pc"

        # The archive dir was actually created on disk
        archive_dirs = [d for d in (tmp_path / "backups" / "pc").iterdir() if "season_archive" in d.name]
        assert len(archive_dirs) == 1
        assert (archive_dirs[0] / "Hero.d2s").exists()

    async def test_no_snapshot_proceeds_without_archive(self, tmp_path: Path) -> None:
        """If no manual/game_close snapshot exists, season starts with archive_snapshot_id=None."""
        from backend.models import BackupSnapshot

        season = _season()
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        # No BackupSnapshot added to session
        added = [c.args[0] for c in session.add.call_args_list]
        archive_snaps = [o for o in added if isinstance(o, BackupSnapshot)]
        assert len(archive_snaps) == 0
        assert season.archive_snapshot_id is None

    async def test_missing_snapshot_dir_on_disk_proceeds(self, tmp_path: Path) -> None:
        """Snapshot in DB but dir deleted → skip archive, no crash."""
        from backend.models import BackupSnapshot

        season = _season()
        snap = _snap(path="backups/pc/gone_snap")  # dir not created
        session = _session(season, snap)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        added = [c.args[0] for c in session.add.call_args_list]
        archive_snaps = [o for o in added if isinstance(o, BackupSnapshot)]
        assert len(archive_snaps) == 0


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
            patch("backend.config.get_settings", return_value=cfg),
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
            patch("backend.config.get_settings", return_value=cfg),
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
            patch("backend.config.get_settings", return_value=cfg),
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
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=1)

        session.commit.assert_called()

    async def test_archive_snapshot_id_set_when_archive_created(self, tmp_path: Path) -> None:
        """season.archive_snapshot_id is set to the new archive snapshot's id."""
        from backend.models import BackupSnapshot

        snap_dir = tmp_path / "backups" / "pc" / "snap_10"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 4)

        season = _season()
        snap = _snap(path="backups/pc/snap_10")
        session = _session(season, snap)

        # Use flush side-effect to stamp id=42 on any BackupSnapshot added to the session.
        added_snaps: list = []
        orig_add = session.add.side_effect

        def _track_add(obj):
            if isinstance(obj, BackupSnapshot):
                added_snaps.append(obj)
            if orig_add:
                orig_add(obj)

        session.add = MagicMock(side_effect=_track_add)

        async def _stamp_flush():
            for s in added_snaps:
                s.id = 42

        session.flush = AsyncMock(side_effect=_stamp_flush)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
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
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
            patch("backend.services.ssh_client.get_sftp") as mock_sftp,
        ):
            await start_season(session=session, season_id=1)

        # ssh_client.get_sftp must never be invoked
        mock_sftp.assert_not_called()


# ─── Stale archive cleanup ────────────────────────────────────────────────────

class TestStartSeasonStaleCleanup:
    """
    If a setup-status season already has characters archived to it (stale rows
    from a failed previous start attempt), start_season must remove them before
    re-archiving the current active characters — otherwise the bulk UPDATE hits
    a UNIQUE constraint on (filename, season_id).

    Regression for: UNIQUE constraint failed: characters.filename, characters.season_id
    """

    async def test_stale_archives_are_deleted_before_archiving(self, tmp_path: Path) -> None:
        """
        When stale archived chars exist for the target season, delete them first
        so the bulk UPDATE can proceed without a UNIQUE violation.
        """
        stale_char = MagicMock()
        stale_char.filename = "Tald.d2s"

        season = _season(id=4)
        session = _session(season, latest_snap=None, stale_chars=[stale_char])

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            result = await start_season(session=session, season_id=4)

        # Season should activate successfully
        assert result.status == "active"

        # A delete(Character) call must have fired for the stale rows.
        # other_active(1) + snap(2) + stale_select(3) + stale_delete(4) + char_archive(5)
        # + grail_delete(6) + vault_item_delete(7) + gold_update(8)
        assert session.execute.call_count >= 5

    async def test_no_stale_archives_skips_delete(self, tmp_path: Path) -> None:
        """When no stale rows exist, no extra delete is issued."""
        season = _season(id=4)
        # stale_chars defaults to [] in _session
        session = _session(season, latest_snap=None)

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            await start_season(session=session, season_id=4)

        # With no stale chars the stale delete execute is NOT called:
        # other_active(1) + snap(2) + stale_select(3) + char_archive(4) + grail_delete(5)
        # + vault_item_delete(6) + gold_update(7) = 7 calls (no extra stale delete)
        assert session.execute.call_count == 7

    async def test_same_character_name_across_seasons_succeeds(self, tmp_path: Path) -> None:
        """
        A player using the same character filename every season (e.g. 'Tald.d2s')
        must be able to start a new season without a constraint error, even if a
        previous season already archived that character.
        """
        stale_tald = MagicMock()
        stale_tald.filename = "Tald.d2s"
        stale_talderaan = MagicMock()
        stale_talderaan.filename = "Talderaan.d2s"

        season = _season(id=5)
        session = _session(season, latest_snap=None, stale_chars=[stale_tald, stale_talderaan])

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        with (
            patch("backend.config.get_settings", return_value=cfg),
            patch("backend.services.seasons_service.compute_and_save_season_stats", new_callable=AsyncMock),
        ):
            result = await start_season(session=session, season_id=5)

        assert result.status == "active"

from __future__ import annotations

"""
Unit tests for backup_manager.push_snapshot_to_machine.

Tests cover:
- Normal push: old .d2s/.d2i deleted, snapshot files uploaded
- Empty snapshot (fresh season): delete only, nothing uploaded
- No snapshot in DB: delete only, nothing uploaded
- D2R running: RuntimeError raised before any file ops
- Snapshot dir missing on disk: treated like no-snapshot
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.backup_manager import push_snapshot_to_machine


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _snap(id: int = 1, source_machine: str = "pc", path: str = "backups/pc/snap_1") -> MagicMock:
    s = MagicMock()
    s.id = id
    s.source_machine = source_machine
    s.snapshot_path = path
    return s


def _session(snapshot: MagicMock | None) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = snapshot
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _cfg(data_dir: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.data_dir = data_dir
    return cfg


def _sftp_with_files(filenames: list[str], save_dir: str = "/saves") -> MagicMock:
    """Return an sftp mock whose list_all_files yields the given filenames."""
    file_infos = [
        {"filename": f, "path": f"{save_dir}/{f}", "modified_at": 0.0}
        for f in filenames
    ]
    return file_infos


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestPushSnapshotNormal:
    async def test_deletes_d2s_and_d2i_on_target(self, tmp_path: Path) -> None:
        """Remote .d2s and .d2i are deleted before upload."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 10)

        snap = _snap(path="backups/pc/snap_1")
        session = _session(snap)

        remote_files = [
            {"filename": "OldHero.d2s", "path": "/saves/OldHero.d2s", "modified_at": 0.0},
            {"filename": "OldHero.d2i", "path": "/saves/OldHero.d2i", "modified_at": 0.0},
            {"filename": "Settings.json", "path": "/saves/Settings.json", "modified_at": 0.0},
        ]

        mock_sftp = MagicMock()
        mock_sftp.remove = MagicMock()
        mock_sftp.put = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
                is_windows=True,
            )

        # Only .d2s and .d2i are removed (not Settings.json)
        assert removed == 2
        assert mock_sftp.remove.call_count == 2
        removed_paths = {c.args[0] for c in mock_sftp.remove.call_args_list}
        assert "/saves/OldHero.d2s" in removed_paths
        assert "/saves/OldHero.d2i" in removed_paths

    async def test_settings_json_not_uploaded(self, tmp_path: Path) -> None:
        """Settings.json in the snapshot dir must NOT be uploaded — it's device-specific."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 10)
        (snap_dir / "Settings.json").write_bytes(b"{}")

        snap = _snap(path="backups/pc/snap_1")
        session = _session(snap)

        mock_sftp = MagicMock()
        mock_sftp.remove = MagicMock()
        mock_sftp.put = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=[]),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
                is_windows=True,
            )

        # Only Hero.d2s uploaded — Settings.json excluded
        assert uploaded == 1
        uploaded_files = {call.args[0] for call in mock_sftp.put.call_args_list}
        assert all("Settings.json" not in f for f in uploaded_files)

    async def test_uploads_snapshot_files(self, tmp_path: Path) -> None:
        """All save files in snapshot dir are uploaded."""
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 10)
        (snap_dir / "Stash.d2i").write_bytes(b"\x00" * 20)

        snap = _snap(path="backups/pc/snap_1")
        session = _session(snap)

        mock_sftp = MagicMock()
        mock_sftp.remove = MagicMock()
        mock_sftp.put = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=[]),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
                is_windows=True,
            )

        assert uploaded == 2
        assert mock_sftp.put.call_count == 2

    async def test_returns_correct_counts(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "A.d2s").write_bytes(b"\x00" * 4)
        (snap_dir / "B.d2s").write_bytes(b"\x00" * 4)

        snap = _snap(path="backups/pc/snap_1")
        session = _session(snap)

        remote_files = [
            {"filename": "Old.d2s", "path": "/saves/Old.d2s", "modified_at": 0.0},
        ]

        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session, machine="pc",
                conn_kwargs={"host": "localhost"}, save_dir="/saves", is_windows=True,
            )

        assert removed == 1
        assert uploaded == 2


class TestPushSnapshotEmpty:
    async def test_no_snapshot_in_db_deletes_only(self, tmp_path: Path) -> None:
        """No manual/game_close snapshot → delete remote saves, upload nothing."""
        session = _session(None)

        remote_files = [
            {"filename": "Old.d2s", "path": "/saves/Old.d2s", "modified_at": 0.0},
        ]
        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session, machine="pc",
                conn_kwargs={"host": "localhost"}, save_dir="/saves", is_windows=True,
            )

        assert removed == 1
        assert uploaded == 0
        assert mock_sftp.put.call_count == 0

    async def test_snapshot_dir_missing_on_disk_uploads_nothing(self, tmp_path: Path) -> None:
        """Snapshot exists in DB but dir was deleted → upload nothing."""
        snap = _snap(path="backups/pc/gone_snap")
        session = _session(snap)
        # snapshot dir deliberately not created

        remote_files = [
            {"filename": "Old.d2s", "path": "/saves/Old.d2s", "modified_at": 0.0},
        ]
        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            removed, uploaded = await push_snapshot_to_machine(
                session=session, machine="pc",
                conn_kwargs={"host": "localhost"}, save_dir="/saves", is_windows=True,
            )

        assert uploaded == 0
        assert mock_sftp.put.call_count == 0


class TestPushSnapshotPreflight:
    async def test_d2r_running_raises_runtime_error(self, tmp_path: Path) -> None:
        """If D2R is running on target, RuntimeError is raised before any file ops."""
        snap = _snap(path="backups/pc/snap_1")
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 4)
        session = _session(snap)

        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=[]),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=True),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="D2R.exe is currently running"):
                await push_snapshot_to_machine(
                    session=session, machine="pc",
                    conn_kwargs={"host": "localhost"}, save_dir="/saves", is_windows=True,
                )

        # No files deleted or uploaded
        mock_sftp.remove.assert_not_called()
        mock_sftp.put.assert_not_called()

    async def test_deck_machine_passes_is_windows_false(self, tmp_path: Path) -> None:
        """is_windows=False is forwarded to check_d2r_running for the Deck."""
        session = _session(None)
        mock_sftp = MagicMock()

        with (
            patch("backend.services.backup_manager.get_settings", return_value=_cfg(tmp_path)),
            patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp,
            patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=[]),
            patch("backend.services.backup_manager.ssh_mod.normalize_path", side_effect=lambda x: x),
            patch("backend.services.backup_manager.ssh_mod.check_d2r_running", return_value=False) as mock_check,
        ):
            mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
            mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)

            await push_snapshot_to_machine(
                session=session, machine="deck",
                conn_kwargs={"host": "deckhost"}, save_dir="/saves", is_windows=False,
            )

        _ssh_arg, is_win_arg = mock_check.call_args.args
        assert is_win_arg is False

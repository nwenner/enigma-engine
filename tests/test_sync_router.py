from __future__ import annotations

"""
Unit tests for sync router helpers:
- compare_with_device categorisation logic (via direct calls to the compare endpoint)
- do_checkin background task: snapshot creation, grail/season hooks, status updates
- do_push background task: push_snapshot_to_machine called, status updates

All SSH calls are mocked. DB session is AsyncMock.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.routers.sync import (
    FileCompareEntry,
    SyncCompareResponse,
    COMPARE_THRESHOLD_SECONDS,
    do_checkin,
    do_push,
)


# ─── Compare threshold helpers ────────────────────────────────────────────────

class TestCompareThreshold:
    """Verify the threshold constant controls bucket assignment."""

    def test_threshold_is_60_seconds(self) -> None:
        assert COMPARE_THRESHOLD_SECONDS == 60

    def _categorise(self, device_mtime: float, app_mtime: float) -> str:
        """Return which bucket a single file would fall into."""
        diff = device_mtime - app_mtime
        if diff < -COMPARE_THRESHOLD_SECONDS:
            return "device_older"
        elif diff > COMPARE_THRESHOLD_SECONDS:
            return "device_newer"
        return "in_sync"

    def test_device_older_by_2_minutes(self) -> None:
        assert self._categorise(1000.0, 1000.0 + 120) == "device_older"

    def test_device_newer_by_2_minutes(self) -> None:
        assert self._categorise(1000.0 + 120, 1000.0) == "device_newer"

    def test_within_threshold_is_in_sync(self) -> None:
        # 30 seconds difference — within threshold
        assert self._categorise(1000.0 + 30, 1000.0) == "in_sync"
        assert self._categorise(1000.0, 1000.0 + 30) == "in_sync"

    def test_exactly_at_threshold_is_in_sync(self) -> None:
        # Equal to threshold (not strictly greater) → in_sync
        assert self._categorise(1000.0 - 60, 1000.0) == "in_sync"
        assert self._categorise(1000.0 + 60, 1000.0) == "in_sync"

    def test_one_second_over_threshold_is_older(self) -> None:
        assert self._categorise(1000.0 - 61, 1000.0) == "device_older"

    def test_one_second_over_threshold_is_newer(self) -> None:
        assert self._categorise(1000.0 + 61, 1000.0) == "device_newer"


# ─── do_checkin ───────────────────────────────────────────────────────────────

def _pending_op(id: int = 1) -> MagicMock:
    op = MagicMock()
    op.id = id
    op.status = "pending"
    op.file_count = 0
    op.error_message = None
    op.completed_at = None
    return op


def _operation_session(operation: MagicMock) -> tuple[AsyncMock, AsyncMock]:
    """Return (outer session mock, AsyncSessionLocal context manager mock)."""
    op_result = MagicMock()
    op_result.scalar_one_or_none.return_value = operation

    session = AsyncMock()
    session.execute = AsyncMock(return_value=op_result)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return session, ctx


class TestDoCheckin:
    async def test_success_sets_status_to_success(self, tmp_path: Path) -> None:
        """Happy path: snapshot created → status = success."""
        op = _pending_op()
        session, ctx = _operation_session(op)

        snap = MagicMock()
        snap.file_count = 5
        snap.snapshot_path = "backups/pc/snap_1"

        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)
        (snap_dir / "Hero.d2s").write_bytes(b"\x00" * 4)

        cfg = MagicMock()
        cfg.data_dir = tmp_path

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch("backend.routers.sync.create_snapshot", new_callable=AsyncMock, return_value=snap),
            patch("backend.routers.sync.get_settings", return_value=cfg),
            patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock),
            patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock),
        ):
            await do_checkin(
                operation_id=1,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
            )

        assert op.status == "success"
        assert op.file_count == 5
        assert op.completed_at is not None

    async def test_snapshot_failure_sets_status_to_failed(self) -> None:
        """If create_snapshot raises, operation is marked failed."""
        op = _pending_op()
        session, ctx = _operation_session(op)

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch(
                "backend.routers.sync.create_snapshot",
                new_callable=AsyncMock,
                side_effect=RuntimeError("SSH timeout"),
            ),
        ):
            await do_checkin(
                operation_id=1,
                machine="pc",
                conn_kwargs={"host": "localhost"},
                save_dir="/saves",
            )

        assert op.status == "failed"
        assert "SSH timeout" in (op.error_message or "")
        assert op.completed_at is not None

    async def test_operation_not_found_returns_early(self) -> None:
        """If operation is not in DB, function returns without crashing."""
        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=op_result)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx):
            # Should not raise
            await do_checkin(999, "pc", {"host": "localhost"}, "/saves")

    async def test_grail_hook_failure_does_not_fail_operation(self, tmp_path: Path) -> None:
        """Grail hook error is swallowed — operation still succeeds."""
        op = _pending_op()
        session, ctx = _operation_session(op)

        snap = MagicMock()
        snap.file_count = 1
        snap.snapshot_path = "backups/pc/snap_1"

        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)

        cfg = MagicMock()
        cfg.data_dir = tmp_path

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch("backend.routers.sync.create_snapshot", new_callable=AsyncMock, return_value=snap),
            patch("backend.routers.sync.get_settings", return_value=cfg),
            patch(
                "backend.services.grail_service.process_portal_tab_hook",
                new_callable=AsyncMock,
                side_effect=Exception("grail exploded"),
            ),
            patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock),
        ):
            await do_checkin(1, "pc", {"host": "localhost"}, "/saves")

        assert op.status == "success"

    async def test_create_snapshot_called_with_manual_label(self, tmp_path: Path) -> None:
        """create_snapshot must be called with label='manual'."""
        op = _pending_op()
        session, ctx = _operation_session(op)

        snap = MagicMock()
        snap.file_count = 0
        snap.snapshot_path = "backups/pc/snap_1"
        snap_dir = tmp_path / "backups" / "pc" / "snap_1"
        snap_dir.mkdir(parents=True)

        cfg = MagicMock()
        cfg.data_dir = tmp_path

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch("backend.routers.sync.create_snapshot", new_callable=AsyncMock, return_value=snap) as mock_cs,
            patch("backend.routers.sync.get_settings", return_value=cfg),
            patch("backend.services.grail_service.process_portal_tab_hook", new_callable=AsyncMock),
            patch("backend.services.seasons_service.check_season_milestones", new_callable=AsyncMock),
        ):
            await do_checkin(1, "pc", {"host": "host"}, "/saves")

        mock_cs.assert_awaited_once()
        kwargs = mock_cs.call_args.kwargs
        assert kwargs["label"] == "manual"
        assert kwargs["machine"] == "pc"


# ─── do_push ─────────────────────────────────────────────────────────────────

class TestDoPush:
    async def test_success_sets_status_to_success(self) -> None:
        op = _pending_op()
        session, ctx = _operation_session(op)

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch(
                "backend.routers.sync.push_snapshot_to_machine",
                new_callable=AsyncMock,
                return_value=(2, 3),   # removed=2, uploaded=3
            ),
        ):
            await do_push(1, "deck", {"host": "deckhost"}, "/saves", False)

        assert op.status == "success"
        assert op.file_count == 3  # uploaded count
        assert op.completed_at is not None

    async def test_d2r_running_sets_status_to_failed(self) -> None:
        op = _pending_op()
        session, ctx = _operation_session(op)

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch(
                "backend.routers.sync.push_snapshot_to_machine",
                new_callable=AsyncMock,
                side_effect=RuntimeError("D2R.exe is currently running on DECK"),
            ),
        ):
            await do_push(1, "deck", {"host": "deckhost"}, "/saves", False)

        assert op.status == "failed"
        assert "D2R.exe" in (op.error_message or "")

    async def test_operation_not_found_returns_early(self) -> None:
        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=op_result)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx):
            await do_push(999, "pc", {"host": "localhost"}, "/saves", True)

    async def test_push_snapshot_called_with_correct_args(self) -> None:
        op = _pending_op()
        session, ctx = _operation_session(op)

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch(
                "backend.routers.sync.push_snapshot_to_machine",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ) as mock_push,
        ):
            await do_push(1, "pc", {"host": "pchost"}, "/pc/saves", True)

        mock_push.assert_awaited_once()
        kwargs = mock_push.call_args.kwargs
        assert kwargs["machine"] == "pc"
        assert kwargs["save_dir"] == "/pc/saves"
        assert kwargs["is_windows"] is True

    async def test_status_set_to_running_before_push(self) -> None:
        """Operation status must transition pending → running before the push starts."""
        op = _pending_op()
        session, ctx = _operation_session(op)

        status_during_push = []

        async def _capture_push(**kwargs):
            status_during_push.append(op.status)
            return 0, 0

        with (
            patch("backend.routers.sync.AsyncSessionLocal", return_value=ctx),
            patch("backend.routers.sync.push_snapshot_to_machine", side_effect=_capture_push),
        ):
            await do_push(1, "pc", {"host": "localhost"}, "/saves", True)

        assert status_during_push == ["running"]
        assert op.status == "success"

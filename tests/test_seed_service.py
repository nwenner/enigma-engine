from __future__ import annotations

"""
Unit tests for seed service (backend/services/seed_service.py).

Strategy
--------
- write_map_seed round-trip: pure Python, no mocking needed.
- apply_seed_to_snapshot: mocked session + tmp_path filesystem so no Docker needed.

Coverage
--------
- write_map_seed()            → round-trip read back correct seed, size unchanged
- apply_seed_to_snapshot()    → 404 when no snapshot; 404 when char missing; success path
"""

import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run inside Docker")

from fastapi import HTTPException, BackgroundTasks

from backend.services.d2s_parser import MAGIC, read_map_seed, write_map_seed
from backend.services.seed_service import apply_seed_to_snapshot


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_v100_d2s(seed: int = 0x01C73932) -> bytes:
    """Minimal v105 .d2s with the given seed at offset 0x9B. Checksum is zeroed (fine for test)."""
    size = 0x9B + 20
    buf = bytearray(size)
    struct.pack_into("<I", buf, 0, MAGIC)
    struct.pack_into("<I", buf, 4, 105)
    struct.pack_into("<I", buf, 0x9B, seed)
    return bytes(buf)


def _make_v99_d2s(seed: int = 0xDEADBEEF) -> bytes:
    """Minimal v99 .d2s with the given seed at offset 0xAB."""
    size = 0xAB + 20
    buf = bytearray(size)
    struct.pack_into("<I", buf, 0, MAGIC)
    struct.pack_into("<I", buf, 4, 99)
    struct.pack_into("<I", buf, 0xAB, seed)
    return bytes(buf)


def _make_saved_seed(seed_value: int = 0xDEADBEEF, name: str = "Test Seed") -> MagicMock:
    s = MagicMock()
    s.id = 1
    s.seed_value = seed_value
    s.name = name
    s.notes = None
    s.source_character = "Tald"
    s.source_class = "Warlock"
    s.source_version = 105
    return s


def _mock_session_with_snap(snap) -> AsyncMock:
    """Return an AsyncSession mock whose execute returns the given snapshot."""
    session = AsyncMock()
    # First execute() returns active season query (None), second returns snapshot query
    season_result = MagicMock()
    season_result.scalar_one_or_none.return_value = None
    snap_result = MagicMock()
    snap_result.scalar_one_or_none.return_value = snap
    session.execute = AsyncMock(side_effect=[season_result, snap_result])
    return session


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestWriteMapSeedRoundTrip:
    def test_v100_seed_round_trip(self) -> None:
        """write_map_seed then read_map_seed returns the written seed for v100+."""
        original = _make_v100_d2s(0x01C73932)
        patched = write_map_seed(original, 0xDEADBEEF)
        assert read_map_seed(patched) == 0xDEADBEEF

    def test_v99_seed_round_trip(self) -> None:
        """write_map_seed then read_map_seed returns the written seed for v99."""
        original = _make_v99_d2s(0x01C73932)
        patched = write_map_seed(original, 0xCAFEBABE)
        assert read_map_seed(patched) == 0xCAFEBABE

    def test_file_size_unchanged(self) -> None:
        """File size must not change after write_map_seed."""
        original = _make_v100_d2s()
        patched = write_map_seed(original, 0x12345678)
        assert len(patched) == len(original)


class TestApplySeedToSnapshot:
    @pytest.mark.asyncio
    async def test_returns_404_when_no_snapshot(self) -> None:
        """apply_seed_to_snapshot raises HTTPException(404) when no snapshot exists."""
        session = AsyncMock()
        # Both season and snapshot queries return None
        null_result = MagicMock()
        null_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=null_result)

        saved_seed = _make_saved_seed()
        background_tasks = BackgroundTasks()

        with pytest.raises(HTTPException) as exc_info:
            await apply_seed_to_snapshot(session, saved_seed, "Tald", background_tasks)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_character_missing(self, tmp_path: Path) -> None:
        """apply_seed_to_snapshot raises HTTPException(404) when .d2s not in snapshot."""
        snap = MagicMock()
        snap.snapshot_path = "backups/pc/20260101T000000Z_manual"
        snap.created_at = datetime.now(timezone.utc)

        snap_dir = tmp_path / "backups" / "pc" / "20260101T000000Z_manual"
        snap_dir.mkdir(parents=True)
        # Do NOT create a .d2s file — character missing

        session = _mock_session_with_snap(snap)
        saved_seed = _make_saved_seed()
        background_tasks = BackgroundTasks()

        with (
            patch("backend.services.seed_service.get_settings") as mock_settings,
            patch("backend.services.auto_sync.guard_mothership_write", new_callable=AsyncMock),
        ):
            mock_settings.return_value.data_dir = tmp_path
            with pytest.raises(HTTPException) as exc_info:
                await apply_seed_to_snapshot(session, saved_seed, "Tald", background_tasks)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_path_returns_correct_dict(self, tmp_path: Path) -> None:
        """apply_seed_to_snapshot returns success dict with correct keys on happy path."""
        snap = MagicMock()
        snap.snapshot_path = "backups/pc/20260101T000000Z_manual"
        snap.created_at = datetime.now(timezone.utc)

        snap_dir = tmp_path / "backups" / "pc" / "20260101T000000Z_manual"
        snap_dir.mkdir(parents=True)
        d2s_file = snap_dir / "Tald.d2s"
        d2s_file.write_bytes(_make_v100_d2s(0x01C73932))

        session = _mock_session_with_snap(snap)
        saved_seed = _make_saved_seed(seed_value=0xDEADBEEF, name="Act1 Dec")
        background_tasks = BackgroundTasks()

        with (
            patch("backend.services.seed_service.get_settings") as mock_settings,
            patch("backend.services.auto_sync.guard_mothership_write", new_callable=AsyncMock),
            patch("backend.services.seed_service._create_local_backup_snapshot", new_callable=AsyncMock),
            patch("backend.services.auto_sync.trigger_mothership_push", new_callable=AsyncMock),
        ):
            mock_settings.return_value.data_dir = tmp_path
            result = await apply_seed_to_snapshot(session, saved_seed, "Tald", background_tasks)

        assert result["success"] is True
        assert result["seed_name"] == "Act1 Dec"
        assert result["character"] == "Tald"
        assert result["seed_hex"] == "0xDEADBEEF"

    @pytest.mark.asyncio
    async def test_success_path_patches_file_on_disk(self, tmp_path: Path) -> None:
        """After apply, reading the seed back from the patched file returns the new seed."""
        snap = MagicMock()
        snap.snapshot_path = "backups/pc/20260101T000000Z_manual"
        snap.created_at = datetime.now(timezone.utc)

        snap_dir = tmp_path / "backups" / "pc" / "20260101T000000Z_manual"
        snap_dir.mkdir(parents=True)
        d2s_file = snap_dir / "Tald.d2s"
        d2s_file.write_bytes(_make_v100_d2s(0x01C73932))

        session = _mock_session_with_snap(snap)
        saved_seed = _make_saved_seed(seed_value=0xCAFEBABE)
        background_tasks = BackgroundTasks()

        with (
            patch("backend.services.seed_service.get_settings") as mock_settings,
            patch("backend.services.auto_sync.guard_mothership_write", new_callable=AsyncMock),
            patch("backend.services.seed_service._create_local_backup_snapshot", new_callable=AsyncMock),
            patch("backend.services.auto_sync.trigger_mothership_push", new_callable=AsyncMock),
        ):
            mock_settings.return_value.data_dir = tmp_path
            await apply_seed_to_snapshot(session, saved_seed, "Tald", background_tasks)

        # Read the patched file back and verify the seed changed
        patched_data = d2s_file.read_bytes()
        assert read_map_seed(patched_data) == 0xCAFEBABE

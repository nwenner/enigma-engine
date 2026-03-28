from __future__ import annotations

"""
Map Seeds router.

Endpoints:
  GET  /api/seeds/current             - All characters with their map seeds from latest snapshot
  GET  /api/seeds/debug/{character}    - Raw byte windows at both candidate offsets for verification
"""
import logging
import struct
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_session
from backend.models import BackupSnapshot, Season
from backend.services.d2s_parser import CLASS_NAMES, D2SParseError, MAGIC, parse_d2s, read_map_seed

log = logging.getLogger(__name__)
router = APIRouter(tags=["seeds"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _latest_snapshot(session: AsyncSession) -> BackupSnapshot | None:
    active_result = await session.execute(select(Season).where(Season.status == "active"))
    active_season = active_result.scalar_one_or_none()

    q = (
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    if active_season and active_season.started_at:
        q = q.where(BackupSnapshot.created_at >= active_season.started_at)

    result = await session.execute(q)
    return result.scalar_one_or_none()


def _snapshot_dir(snap: BackupSnapshot) -> Path:
    return get_settings().data_dir / snap.snapshot_path


def _hex_window(data: bytes, offset: int, pre: int = 4, post: int = 8) -> str:
    """Return a hex string showing bytes around the given offset."""
    start = max(0, offset - pre)
    end = min(len(data), offset + post)
    return " ".join(f"{b:02X}" for b in data[start:end])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SeedEntry(BaseModel):
    character: str
    name: str
    class_name: str
    seed_decimal: int
    seed_hex: str


class SeedsCurrentResponse(BaseModel):
    seeds: list[SeedEntry]
    parse_errors: list[str]
    snapshot_at: Optional[str] = None


class SeedDebugResponse(BaseModel):
    character: str
    version: int
    offset_v100: int
    seed_at_v100: int
    hex_window_v100: str
    offset_v99: int
    seed_at_v99: int
    hex_window_v99: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/seeds/current", response_model=SeedsCurrentResponse)
async def seeds_current(session: AsyncSession = Depends(get_session)):
    """Return all characters with their map seeds from the latest vault snapshot."""
    snap = await _latest_snapshot(session)
    if snap is None:
        return SeedsCurrentResponse(seeds=[], parse_errors=[], snapshot_at=None)

    snap_dir = _snapshot_dir(snap)
    entries: list[SeedEntry] = []
    errors: list[str] = []

    for path in sorted(snap_dir.glob("*.d2s")):
        try:
            data = path.read_bytes()
            char = parse_d2s(path)
            seed = read_map_seed(data)
            entries.append(SeedEntry(
                character=path.stem,
                name=char.name,
                class_name=char.class_name,
                seed_decimal=seed,
                seed_hex=f"0x{seed:08X}",
            ))
        except (D2SParseError, OSError, struct.error) as e:
            errors.append(f"{path.name}: {e}")

    snapshot_at = snap.created_at.isoformat() if snap.created_at else None
    return SeedsCurrentResponse(seeds=entries, parse_errors=errors, snapshot_at=snapshot_at)


@router.get("/seeds/debug/{character}", response_model=SeedDebugResponse)
async def seeds_debug(character: str, session: AsyncSession = Depends(get_session)):
    """Return raw byte windows at both candidate seed offsets for empirical verification."""
    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    d2s_path = snap_dir / f"{character}.d2s"
    if not d2s_path.exists():
        raise HTTPException(404, f"{character}.d2s not found in snapshot")

    data = d2s_path.read_bytes()

    if len(data) < 8:
        raise HTTPException(400, f"{character}.d2s is too small to read version")

    _, version = struct.unpack_from("<II", data, 0)

    offset_v100 = 0x9B
    offset_v99 = 0xAB

    seed_at_v100 = (
        struct.unpack_from("<I", data, offset_v100)[0]
        if len(data) >= offset_v100 + 4
        else 0
    )
    seed_at_v99 = (
        struct.unpack_from("<I", data, offset_v99)[0]
        if len(data) >= offset_v99 + 4
        else 0
    )

    return SeedDebugResponse(
        character=character,
        version=version,
        offset_v100=offset_v100,
        seed_at_v100=seed_at_v100,
        hex_window_v100=_hex_window(data, offset_v100),
        offset_v99=offset_v99,
        seed_at_v99=seed_at_v99,
        hex_window_v99=_hex_window(data, offset_v99),
    )

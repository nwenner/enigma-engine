from __future__ import annotations

"""
Map Seeds router.

Endpoints:
  GET  /api/seeds/current             - All characters with their map seeds from latest snapshot
  GET  /api/seeds/debug/{character}    - Raw byte windows at both candidate offsets for verification
  POST /api/seeds/library             - Save a character's current map seed to the library
  GET  /api/seeds/library             - List all saved seeds, newest first
  PATCH /api/seeds/library/{id}       - Update name and notes of a saved seed
  DELETE /api/seeds/library/{id}      - Delete a saved seed (returns 204)
"""
import logging
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_session
from backend.models import BackupSnapshot, SavedSeed, Season
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


class SaveSeedRequest(BaseModel):
    character: str       # filename without .d2s, e.g. "Tald"
    name: str            # user label, e.g. "Act1 Dec"
    notes: Optional[str] = None


class UpdateSeedRequest(BaseModel):
    name: str
    notes: Optional[str] = None


class SavedSeedRecord(BaseModel):
    id: int
    seed_value: int
    seed_hex: str
    name: str
    notes: Optional[str]
    source_character: str
    source_class: str
    source_version: int
    saved_at: str


# ─── Helper ───────────────────────────────────────────────────────────────────

def _seed_record(s: SavedSeed) -> SavedSeedRecord:
    return SavedSeedRecord(
        id=s.id,
        seed_value=s.seed_value,
        seed_hex=f"0x{s.seed_value:08X}",
        name=s.name,
        notes=s.notes,
        source_character=s.source_character,
        source_class=s.source_class,
        source_version=s.source_version,
        saved_at=s.saved_at.isoformat(),
    )


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


@router.post("/seeds/library", response_model=SavedSeedRecord, status_code=201)
async def save_seed_to_library(
    body: SaveSeedRequest,
    session: AsyncSession = Depends(get_session),
):
    """Save the current map seed of a character to the named library."""
    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    d2s_path = snap_dir / f"{body.character}.d2s"
    if not d2s_path.exists():
        raise HTTPException(404, f"{body.character}.d2s not found in latest snapshot.")

    try:
        data = d2s_path.read_bytes()
        seed = read_map_seed(data)
        char = parse_d2s(d2s_path)
        _, version = struct.unpack_from("<II", data, 0)
    except (D2SParseError, OSError, struct.error) as e:
        raise HTTPException(400, f"Cannot read seed from {body.character}.d2s: {e}") from e

    entry = SavedSeed(
        seed_value=seed,
        name=body.name,
        notes=body.notes,
        source_character=body.character,
        source_class=char.class_name,
        source_version=version,
        saved_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    log.info("Saved seed 0x%08X ('%s') from %s", seed, body.name, body.character)
    return _seed_record(entry)


@router.get("/seeds/library", response_model=list[SavedSeedRecord])
async def list_seeds(session: AsyncSession = Depends(get_session)):
    """List all saved seeds, newest first."""
    result = await session.execute(
        select(SavedSeed).order_by(SavedSeed.saved_at.desc())
    )
    return [_seed_record(s) for s in result.scalars().all()]


@router.patch("/seeds/library/{seed_id}", response_model=SavedSeedRecord)
async def update_seed(
    seed_id: int,
    body: UpdateSeedRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update the name and notes of a saved seed."""
    result = await session.execute(select(SavedSeed).where(SavedSeed.id == seed_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Seed not found.")
    entry.name = body.name
    entry.notes = body.notes
    await session.commit()
    await session.refresh(entry)
    return _seed_record(entry)


@router.delete("/seeds/library/{seed_id}", status_code=204)
async def delete_seed(
    seed_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a saved seed from the library."""
    result = await session.execute(select(SavedSeed).where(SavedSeed.id == seed_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Seed not found.")
    await session.delete(entry)
    await session.commit()

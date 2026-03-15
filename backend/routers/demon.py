from __future__ import annotations

"""
Demon Vault router.

Endpoints:
  GET  /api/demon/status                   - Check if current snapshot has a bound demon
  POST /api/demon/save                     - Save bound demon from latest snapshot to vault
  GET  /api/demon/list                     - List all saved demons
  DELETE /api/demon/{id}                   - Delete a saved demon
  POST /api/demon/{id}/restore             - Restore saved demon to a machine's .d2s file
"""
import logging
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_session
from backend.models import BoundDemon, BackupSnapshot, Season
from backend.services.demon_service import (
    has_bound_demon,
    extract_demon_bytes,
    restore_demon_to_d2s,
)
from backend.services.d2s_parser import CLASS_NAMES, MAGIC

WARLOCK_CLASS_ID = 7

log = logging.getLogger(__name__)
router = APIRouter(tags=["demon"])


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


def _parse_class(d2s_data: bytes) -> tuple[int, str]:
    """Return (class_id, class_name) from raw .d2s bytes without writing to disk."""
    if len(d2s_data) < 8:
        return -1, "Unknown"
    magic, version = struct.unpack_from("<II", d2s_data, 0)
    if magic != MAGIC:
        return -1, "Unknown"
    if version >= 100:
        class_id = d2s_data[0x18] if len(d2s_data) > 0x18 else -1
    else:
        class_id = d2s_data[40] if len(d2s_data) > 40 else -1
    return class_id, CLASS_NAMES.get(class_id, f"Unknown(class {class_id})")


def _require_warlock(d2s_data: bytes, character: str) -> None:
    """Raise HTTP 400 if the character is not a Warlock."""
    class_id, class_name = _parse_class(d2s_data)
    if class_id != WARLOCK_CLASS_ID:
        raise HTTPException(
            400,
            f"{character} is a {class_name}, not a Warlock. "
            "Only Warlocks can use the Demon Vault.",
        )


async def _get_conn_and_dir(session: AsyncSession, machine: str):
    from backend.routers.settings import _get_conn_kwargs, _get_setting
    conn = await _get_conn_kwargs(session, machine)
    save_dir = await _get_setting(session, f"{machine}_save_path") or ""
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {machine}")
    return conn, save_dir


# ─── Schemas ──────────────────────────────────────────────────────────────────

class DemonStatusResponse(BaseModel):
    has_demon: bool
    character: str
    is_warlock: bool
    class_name: str
    snapshot_at: Optional[str] = None


class SaveDemonRequest(BaseModel):
    character: str       # filename without .d2s, e.g. "Tald"
    label: str
    notes: Optional[str] = None


class RestoreDemonRequest(BaseModel):
    character: str       # filename without .d2s


class DemonRecord(BaseModel):
    id: int
    label: str
    character_filename: str
    notes: Optional[str]
    saved_at: str
    demon_size: int


# ─── Routes ───────────────────────────────────────────────────────────────────

class WarlockInfo(BaseModel):
    filename: str     # "Tald.d2s"
    name: str         # "Tald"
    has_demon: bool
    snapshot_at: str


@router.get("/demon/warlocks", response_model=list[WarlockInfo])
async def list_warlocks(session: AsyncSession = Depends(get_session)):
    """
    Return all Warlock characters found in the latest snapshot with their demon status.
    Used to populate dropdowns on the Demon Registry page.
    """
    snap = await _latest_snapshot(session)
    if snap is None:
        return []
    snap_dir = _snapshot_dir(snap)
    if not snap_dir.exists():
        return []
    result = []
    for d2s_path in sorted(snap_dir.glob("*.d2s")):
        try:
            data = d2s_path.read_bytes()
        except OSError:
            continue
        class_id, _ = _parse_class(data)
        if class_id == WARLOCK_CLASS_ID:
            result.append(WarlockInfo(
                filename=d2s_path.name,
                name=d2s_path.stem,
                has_demon=has_bound_demon(data),
                snapshot_at=snap.created_at.isoformat(),
            ))
    return result


@router.get("/demon/tags", response_model=list[str])
async def list_tags(session: AsyncSession = Depends(get_session)):
    """Return all unique tags used across registered demon labels (comma-delimited)."""
    result = await session.execute(select(BoundDemon.label))
    tags: set[str] = set()
    for label in result.scalars().all():
        for tag in label.split(","):
            tag = tag.strip()
            if tag:
                tags.add(tag)
    return sorted(tags)


@router.get("/demon/status", response_model=DemonStatusResponse)
async def demon_status(
    character: str = Query(..., description="Character filename without .d2s (e.g. 'Tald')"),
    session: AsyncSession = Depends(get_session),
):
    """Check whether the latest snapshot .d2s has a bound demon."""
    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    d2s_path = snap_dir / f"{character}.d2s"
    if not d2s_path.exists():
        raise HTTPException(404, f"{character}.d2s not found in latest snapshot.")

    d2s_data = d2s_path.read_bytes()
    class_id, class_name = _parse_class(d2s_data)
    return DemonStatusResponse(
        has_demon=has_bound_demon(d2s_data),
        character=character,
        is_warlock=class_id == WARLOCK_CLASS_ID,
        class_name=class_name,
        snapshot_at=snap.created_at.isoformat(),
    )


@router.post("/demon/save", response_model=DemonRecord)
async def save_demon(
    body: SaveDemonRequest,
    session: AsyncSession = Depends(get_session),
):
    """Extract the bound demon from the latest snapshot and save it to the vault."""
    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    d2s_path = snap_dir / f"{body.character}.d2s"
    if not d2s_path.exists():
        raise HTTPException(404, f"{body.character}.d2s not found in latest snapshot.")

    d2s_data = d2s_path.read_bytes()
    _require_warlock(d2s_data, body.character)
    demon_bytes = extract_demon_bytes(d2s_data)
    if demon_bytes is None:
        raise HTTPException(400, f"{body.character} does not have a bound demon in the latest snapshot.")

    demon = BoundDemon(
        label=body.label,
        character_filename=f"{body.character}.d2s",
        demon_bytes=demon_bytes,
        notes=body.notes,
        saved_at=datetime.now(timezone.utc),
    )
    session.add(demon)
    await session.commit()
    await session.refresh(demon)

    log.info("Saved demon '%s' for %s (%d bytes)", body.label, body.character, len(demon_bytes))
    return DemonRecord(
        id=demon.id,
        label=demon.label,
        character_filename=demon.character_filename,
        notes=demon.notes,
        saved_at=demon.saved_at.isoformat(),
        demon_size=len(demon_bytes),
    )


@router.get("/demon/list", response_model=list[DemonRecord])
async def list_demons(
    character: Optional[str] = Query(None, description="Filter by character (without .d2s)"),
    session: AsyncSession = Depends(get_session),
):
    """List all demons saved in the vault."""
    q = select(BoundDemon).order_by(BoundDemon.saved_at.desc())
    if character:
        q = q.where(BoundDemon.character_filename == f"{character}.d2s")

    result = await session.execute(q)
    demons = result.scalars().all()
    return [
        DemonRecord(
            id=d.id,
            label=d.label,
            character_filename=d.character_filename,
            notes=d.notes,
            saved_at=d.saved_at.isoformat(),
            demon_size=len(d.demon_bytes),
        )
        for d in demons
    ]


@router.delete("/demon/{demon_id}")
async def delete_demon(
    demon_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a saved demon from the vault."""
    result = await session.execute(select(BoundDemon).where(BoundDemon.id == demon_id))
    demon = result.scalar_one_or_none()
    if demon is None:
        raise HTTPException(404, "Demon not found.")
    await session.delete(demon)
    await session.commit()
    return {"success": True}


@router.post("/demon/{demon_id}/restore")
async def restore_demon(
    demon_id: int,
    body: RestoreDemonRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Inject a registered demon into the character's .d2s in the local snapshot
    (the mothership). Use Sync to Device afterward to push the change out.
    """
    result = await session.execute(select(BoundDemon).where(BoundDemon.id == demon_id))
    demon = result.scalar_one_or_none()
    if demon is None:
        raise HTTPException(404, "Demon not found.")

    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    character_file = f"{body.character}.d2s"
    d2s_path = snap_dir / character_file

    if not d2s_path.exists():
        raise HTTPException(404, f"{character_file} not found in latest snapshot.")

    d2s_data = d2s_path.read_bytes()
    _require_warlock(d2s_data, body.character)

    from backend.services.auto_sync import guard_mothership_write
    await guard_mothership_write(session)

    try:
        new_d2s = restore_demon_to_d2s(d2s_data, demon.demon_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    d2s_path.write_bytes(new_d2s)

    log.info("Injected demon '%s' into snapshot/%s", demon.label, character_file)

    from backend.services.auto_sync import trigger_mothership_push
    await trigger_mothership_push(background_tasks, session)

    return {"success": True, "label": demon.label, "character": character_file}

"""
Characters router.

Endpoints:
  GET  /api/characters                    — instant DB read, sorted by modified_at desc
  POST /api/characters/refresh            — SFTP scan of both machines, upserts DB
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Character, SyncFileRecord
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.d2s_parser import D2SParseError, parse_d2s
from backend.services.ssh_client import (
    SSHConnectionError,
    get_sftp,
    list_d2s_files,
    normalize_path,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["characters"])


# ─── Pydantic schema ──────────────────────────────────────────────────────────

class CharacterInfo(BaseModel):
    filename: str
    name: str
    class_id: int
    class_name: str
    level: int
    hardcore: bool
    ever_died: bool
    expansion: bool
    modified_at: float
    last_updated_at: datetime


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _char_to_info(char: Character) -> CharacterInfo:
    return CharacterInfo(
        filename=char.filename,
        name=char.name,
        class_id=char.class_id,
        class_name=char.class_name,
        level=char.level,
        hardcore=char.hardcore,
        ever_died=char.ever_died,
        expansion=char.expansion,
        modified_at=char.modified_at,
        last_updated_at=char.last_updated_at,
    )


async def _backfill_from_sync_records(session: AsyncSession) -> None:
    """
    Seed the Character table from existing SyncFileRecord.char_snapshot data.
    Called once automatically when the table is empty (e.g. after upgrading).
    Uses synced_at as a proxy for modified_at — good enough for initial display.
    """
    result = await session.execute(
        select(SyncFileRecord)
        .where(SyncFileRecord.char_snapshot.isnot(None))
        .order_by(SyncFileRecord.synced_at.desc())
    )
    records = result.scalars().all()

    seen: set[str] = set()
    chars: list[dict] = []
    for rec in records:
        if not rec.char_snapshot:
            continue
        fname = rec.filename
        if fname and fname not in seen:
            seen.add(fname)
            d = dict(rec.char_snapshot)
            d["filename"] = fname  # override any corrupted filename stored in char_snapshot
            d["modified_at"] = rec.synced_at.timestamp()
            chars.append(d)

    if chars:
        await upsert_characters(session, chars)


async def upsert_characters(session: AsyncSession, chars: list[dict]) -> None:
    """
    Insert or update Character rows from a list of dicts.
    Each dict must have the fields from D2SCharacter.to_dict() plus 'modified_at'.
    Updates the row when incoming modified_at >= existing modified_at.
    """
    for char_dict in chars:
        filename = char_dict.get("filename")
        if not filename:
            continue

        result = await session.execute(
            select(Character).where(Character.filename == filename)
        )
        existing = result.scalar_one_or_none()
        incoming_mtime = float(char_dict.get("modified_at", 0.0))
        now = datetime.utcnow()

        difficulty_active = int(char_dict.get("difficulty_active", 0))

        if existing is None:
            session.add(
                Character(
                    filename=filename,
                    name=char_dict["name"],
                    class_id=char_dict["class_id"],
                    class_name=char_dict["class_name"],
                    level=char_dict["level"],
                    hardcore=bool(char_dict.get("hardcore", False)),
                    ever_died=bool(char_dict.get("ever_died", False)),
                    expansion=bool(char_dict.get("expansion", True)),
                    difficulty_active=difficulty_active,
                    modified_at=incoming_mtime,
                    last_updated_at=now,
                )
            )
        elif incoming_mtime >= existing.modified_at:
            existing.name = char_dict["name"]
            existing.class_id = char_dict["class_id"]
            existing.class_name = char_dict["class_name"]
            existing.level = char_dict["level"]
            existing.hardcore = bool(char_dict.get("hardcore", False))
            existing.ever_died = bool(char_dict.get("ever_died", False))
            existing.expansion = bool(char_dict.get("expansion", True))
            existing.difficulty_active = difficulty_active
            existing.modified_at = incoming_mtime
            existing.last_updated_at = now
        else:
            existing.last_updated_at = now

    await session.commit()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/characters", response_model=list[CharacterInfo])
async def get_characters(session: AsyncSession = Depends(get_session)):
    count = (await session.execute(select(func.count()).select_from(Character))).scalar_one()
    if count == 0:
        await _backfill_from_sync_records(session)

    result = await session.execute(
        select(Character).order_by(Character.modified_at.desc())
    )
    return [_char_to_info(c) for c in result.scalars().all()]


@router.post("/characters/refresh", response_model=list[CharacterInfo])
async def refresh_characters(session: AsyncSession = Depends(get_session)):
    """SFTP scan both machines, upsert DB, return full character list."""
    all_chars: list[dict] = []

    for machine in ("pc", "deck"):
        try:
            conn_kwargs = await _get_conn_kwargs(session, machine)
            save_path = await _get_setting(session, f"{machine}_save_path") or ""
        except Exception as e:
            log.warning("Config error for %s during refresh: %s", machine, e)
            continue

        if not conn_kwargs.get("host") or not save_path:
            continue

        def _fetch(conn_kwargs=conn_kwargs, save_path=save_path, machine=machine):
            results = []
            with get_sftp(**conn_kwargs) as (_ssh, sftp):
                files = list_d2s_files(sftp, save_path)
                for f in files:
                    if not f["filename"].endswith(".d2s"):
                        continue
                    with tempfile.NamedTemporaryFile(suffix=".d2s", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    try:
                        sftp.get(normalize_path(f["path"]), str(tmp_path))
                        char = parse_d2s(tmp_path)
                        d = char.to_dict()
                        d["filename"] = f["filename"]
                        d["modified_at"] = f["modified_at"]
                        results.append(d)
                    except D2SParseError as e:
                        log.warning(
                            "Could not parse %s on %s: %s", f["filename"], machine, e
                        )
                    finally:
                        tmp_path.unlink(missing_ok=True)
            return results

        try:
            machine_chars = await asyncio.to_thread(_fetch)
            all_chars.extend(machine_chars)
        except Exception as e:
            log.warning("Could not refresh characters from %s: %s", machine, e)

    await upsert_characters(session, all_chars)

    result = await session.execute(
        select(Character).order_by(Character.modified_at.desc())
    )
    return [_char_to_info(c) for c in result.scalars().all()]



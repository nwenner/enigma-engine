from __future__ import annotations

"""
Holy Grail router.

Endpoints:
  GET  /api/grail/{mode}                    - Full catalog + found status
  GET  /api/grail/{mode}/progress           - Summary stats
  POST /api/grail/catalog/seed              - Upload JSON to seed/replace catalog
  POST /api/grail/{mode}/{catalog_id}/retrieve - Write item to tab 5 on target machine
  DELETE /api/grail/{mode}/{catalog_id}     - Admin escape hatch to unmark an entry
"""
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.database import get_session
from backend.models import GrailCatalog, GrailEntry

log = logging.getLogger(__name__)
router = APIRouter(tags=["grail"])

Mode = Literal["sc", "hc"]


def _mode_to_hardcore(mode: Mode) -> bool:
    return mode == "hc"


# ─── Response schemas ─────────────────────────────────────────────────────────

class GrailItemResponse(BaseModel):
    catalog_id: int
    item_code: str
    name: str
    base_item: str
    quality: str
    set_name: Optional[str]
    sort_order: int
    found: bool
    find_count: int
    found_at: Optional[str]
    last_found_at: Optional[str]
    is_deposited: bool


class GrailProgressResponse(BaseModel):
    hardcore: bool
    unique_total: int
    unique_found: int
    set_total: int
    set_found: int
    items: list[GrailItemResponse]


class RetrieveRequest(BaseModel):
    machine: Literal["pc", "deck"]


class DepositRequest(BaseModel):
    machine: Literal["pc", "deck"]


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/grail/{mode}", response_model=GrailProgressResponse)
async def get_grail(mode: Mode, session: AsyncSession = Depends(get_session)):
    hardcore = _mode_to_hardcore(mode)

    catalog_result = await session.execute(
        select(GrailCatalog).order_by(GrailCatalog.sort_order, GrailCatalog.name)
    )
    catalog = catalog_result.scalars().all()

    entries_result = await session.execute(
        select(GrailEntry).where(GrailEntry.hardcore == hardcore)
    )
    entries_by_catalog: dict[int, GrailEntry] = {
        e.catalog_id: e for e in entries_result.scalars().all()
    }

    items: list[GrailItemResponse] = []
    unique_total = unique_found = set_total = set_found = 0

    for cat in catalog:
        entry = entries_by_catalog.get(cat.id)
        found = entry is not None
        is_unique = cat.quality == "unique"

        if is_unique:
            unique_total += 1
            if found:
                unique_found += 1
        else:
            set_total += 1
            if found:
                set_found += 1

        items.append(GrailItemResponse(
            catalog_id=cat.id,
            item_code=cat.item_code,
            name=cat.name,
            base_item=cat.base_item,
            quality=cat.quality,
            set_name=cat.set_name,
            sort_order=cat.sort_order,
            found=found,
            find_count=entry.find_count if entry else 0,
            found_at=entry.found_at.isoformat() if entry else None,
            last_found_at=entry.last_found_at.isoformat() if entry else None,
            is_deposited=entry.is_deposited if entry else False,
        ))

    return GrailProgressResponse(
        hardcore=hardcore,
        unique_total=unique_total,
        unique_found=unique_found,
        set_total=set_total,
        set_found=set_found,
        items=items,
    )


@router.get("/grail/{mode}/progress")
async def get_grail_progress(mode: Mode, session: AsyncSession = Depends(get_session)):
    hardcore = _mode_to_hardcore(mode)

    catalog_result = await session.execute(select(GrailCatalog))
    catalog = catalog_result.scalars().all()
    total = len(catalog)

    entries_result = await session.execute(
        select(GrailEntry).where(GrailEntry.hardcore == hardcore)
    )
    found = len(entries_result.scalars().all())

    pct = round(found / total * 100, 1) if total else 0.0
    return {"total": total, "found": found, "pct": pct}


@router.post("/grail/catalog/seed")
async def seed_catalog(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        items = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    if not isinstance(items, list):
        raise HTTPException(400, "Expected a JSON array")

    required = {"item_code", "name", "base_item", "quality"}
    for i, item in enumerate(items):
        missing = required - set(item.keys())
        if missing:
            raise HTTPException(400, f"Item {i} missing fields: {missing}")
        if item["quality"] not in ("unique", "set"):
            raise HTTPException(400, f"Item {i} quality must be 'unique' or 'set'")

    # Truncate existing catalog + entries
    await session.execute(delete(GrailEntry))
    await session.execute(delete(GrailCatalog))

    for item in items:
        session.add(GrailCatalog(
            item_code=item["item_code"],
            name=item["name"],
            base_item=item["base_item"],
            quality=item["quality"],
            set_name=item.get("set_name"),
            unique_id=item.get("unique_id"),
            set_id=item.get("set_id"),
            sort_order=item.get("sort_order", 0),
        ))

    await session.commit()
    return {"success": True, "count": len(items)}


@router.post("/grail/deposit")
async def deposit_tab5(
    body: DepositRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Download stash files from the machine, register tab 5 unique/set items in the grail,
    clear tab 5, and upload the modified stash back. Explicit user action only.

    SAFETY: Creates full backup before ANY modification. D2R must not be running.
    """
    from backend.services.grail_service import deposit_tab5 as _deposit
    from backend.routers.settings import _get_conn_kwargs, _get_setting
    from backend.services.ssh_client import check_d2r_running, get_sftp

    conn = await _get_conn_kwargs(session, body.machine)
    save_dir = await _get_setting(session, f"{body.machine}_save_path") or ""
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {body.machine}")

    # CRITICAL: Check D2R is not running
    def _check_running():
        with get_sftp(**conn) as (_ssh, _sftp):
            is_windows = body.machine == "pc"
            return check_d2r_running(_ssh, is_windows)

    import asyncio
    try:
        is_running = await asyncio.to_thread(_check_running)
        if is_running:
            raise HTTPException(
                409,
                f"D2R is currently running on {body.machine.upper()}. Close the game before depositing items."
            )
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Could not check if D2R is running: %s", e)

    try:
        result = await _deposit(
            session=session,
            machine=body.machine,
            conn=conn,
            save_dir=save_dir,
        )
    except Exception as e:
        log.error("Deposit failed: %s", e)
        raise HTTPException(500, str(e))

    return {
        "success": True,
        "registered": result["registered"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }


@router.post("/grail/{mode}/{catalog_id}/retrieve")
async def retrieve_grail_item(
    mode: Mode,
    catalog_id: int,
    body: RetrieveRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Retrieve a found grail item and write it to stash tab 5.

    SAFETY: Creates full backup before ANY modification. D2R must not be running.
    Modern stash format only (ModernSharedStashSoftCoreV2.d2i).
    """
    hardcore = _mode_to_hardcore(mode)

    # Load catalog entry
    cat_result = await session.execute(
        select(GrailCatalog).where(GrailCatalog.id == catalog_id)
    )
    cat = cat_result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Catalog item not found")

    # Load grail entry
    entry_result = await session.execute(
        select(GrailEntry).where(
            GrailEntry.catalog_id == catalog_id,
            GrailEntry.hardcore == hardcore,
        )
    )
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Item not yet found in grail")
    if entry.raw_item_bytes is None:
        raise HTTPException(409, "No raw item bytes stored — item was found before retrieval support was added")
    if not entry.is_deposited:
        raise HTTPException(409, "Item is not currently in the grail vault — deposit it first")

    # Modern stash format only
    stash_filename = "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"

    from backend.services.grail_service import retrieve_item_to_tab5
    from backend.routers.settings import _get_conn_kwargs, _get_setting
    from backend.services.ssh_client import check_d2r_running, get_sftp

    conn = await _get_conn_kwargs(session, body.machine)
    save_dir = await _get_setting(session, f"{body.machine}_save_path") or ""
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {body.machine}")

    # CRITICAL: Check D2R is not running
    def _check_running():
        with get_sftp(**conn) as (_ssh, _sftp):
            is_windows = body.machine == "pc"
            return check_d2r_running(_ssh, is_windows)

    import asyncio
    try:
        is_running = await asyncio.to_thread(_check_running)
        if is_running:
            raise HTTPException(
                409,
                f"D2R is currently running on {body.machine.upper()}. Close the game before retrieving items."
            )
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Could not check if D2R is running: %s", e)

    try:
        await retrieve_item_to_tab5(
            session=session,
            catalog_id=catalog_id,
            hardcore=hardcore,
            target_machine=body.machine,
            conn=conn,
            save_dir=save_dir,
            stash_filename=stash_filename,
        )
    except Exception as e:
        log.error("Retrieve failed: %s", e)
        raise HTTPException(500, str(e))

    return {"success": True, "message": f"{cat.name} written to stash tab 5 on {body.machine.upper()}"}


@router.delete("/grail/{mode}/{catalog_id}")
async def unmark_grail_entry(
    mode: Mode,
    catalog_id: int,
    session: AsyncSession = Depends(get_session),
):
    hardcore = _mode_to_hardcore(mode)

    result = await session.execute(
        select(GrailEntry).where(
            GrailEntry.catalog_id == catalog_id,
            GrailEntry.hardcore == hardcore,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found")

    await session.delete(entry)
    await session.commit()
    return {"success": True}


@router.post("/grail/reset")
async def reset_all_grail_entries(session: AsyncSession = Depends(get_session)):
    """Delete all grail entries (both SC and HC). Catalog remains intact."""
    result = await session.execute(delete(GrailEntry))
    count = result.rowcount
    await session.commit()
    log.info("Reset grail: deleted %d entries", count)
    return {"success": True, "deleted": count}

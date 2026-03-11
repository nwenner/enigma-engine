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


class DepositPreviewItem(BaseModel):
    stash_filename: str
    item_index: int
    catalog_id: Optional[int]
    item_name: Optional[str]
    base_item: Optional[str]
    quality_name: Optional[str]
    item_code: Optional[str]
    is_ethereal: bool
    in_catalog: bool
    already_deposited: bool
    hardcore: bool


class DepositRequest(BaseModel):
    catalog_ids: Optional[list[int]] = None




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


@router.get("/grail/deposit/preview", response_model=list[DepositPreviewItem])
async def preview_deposit(session: AsyncSession = Depends(get_session)):
    """
    Read-only scan of stash tab 5 in the latest snapshot.
    Returns item metadata with catalog match status — no writes.
    """
    from backend.services.grail_service import preview_tab5
    return await preview_tab5(session)


@router.post("/grail/deposit")
async def deposit_tab5(
    body: DepositRequest = DepositRequest(),
    session: AsyncSession = Depends(get_session),
):
    """
    Register unique/set items from tab 5 of the latest snapshot stash, then clear that tab.
    If catalog_ids is provided, only deposit those items. Otherwise deposit all recognized items.
    Writes to the local snapshot (mothership). Sync to device afterward.

    SAFETY: Creates full local backup before ANY modification.
    """
    from backend.services.grail_service import deposit_tab5 as _deposit

    try:
        result = await _deposit(session=session, catalog_ids=body.catalog_ids)
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
    session: AsyncSession = Depends(get_session),
):
    """
    Retrieve a found grail item and write it to stash tab 5 of the latest snapshot.
    Writes to the local snapshot (mothership). Sync to device afterward.

    SAFETY: Creates full local backup before ANY modification.
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

    stash_filename = "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"

    from backend.services.grail_service import retrieve_item_to_tab5

    try:
        await retrieve_item_to_tab5(
            session=session,
            catalog_id=catalog_id,
            hardcore=hardcore,
            stash_filename=stash_filename,
        )
    except Exception as e:
        log.error("Retrieve failed: %s", e)
        raise HTTPException(500, str(e))

    return {"success": True, "message": f"{cat.name} written to stash tab 5. Sync to device when ready."}


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

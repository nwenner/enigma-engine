from __future__ import annotations

"""
store router — Rune Store endpoints.

Endpoints:
  GET    /api/store/catalog               get_catalog
  POST   /api/store/seed                  seed_library       [multipart: file, hardcore]
  GET    /api/store/tab5-runes            get_tab5_runes     [query: mode]
  POST   /api/store/buy                   buy_rune
  POST   /api/store/trade                 trade_rune
  DELETE /api/store/library/{item_code}   delete_library_entry
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.services import store_service

log = logging.getLogger(__name__)
router = APIRouter(tags=["store"])


# ─── Request / Response schemas ───────────────────────────────────────────────

class CatalogEntry(BaseModel):
    item_code: str
    rune_name: str
    tier: str
    gold_cost: int
    seeded: bool


class CatalogResponse(BaseModel):
    low: list[CatalogEntry]
    mid: list[CatalogEntry]
    high: list[CatalogEntry]


class Tab5RuneResponse(BaseModel):
    item_index: int
    item_code: str
    rune_name: str
    tier: str


class BuyRuneRequest(BaseModel):
    item_code: str
    mode: str = "sc"


class BuyRuneResponse(BaseModel):
    vault_gold: int
    rune_name: str


class TradeRuneRequest(BaseModel):
    tab5_item_index: int
    target_code: str
    mode: str = "sc"


class TradeRuneResponse(BaseModel):
    source_rune: str
    target_rune: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/store/catalog", response_model=CatalogResponse)
async def get_catalog(session: AsyncSession = Depends(get_session)):
    """Return the full rune catalog grouped by tier, indicating which are seeded."""
    data = await store_service.get_catalog(session)
    return CatalogResponse(
        low=[CatalogEntry(**e) for e in data["low"]],
        mid=[CatalogEntry(**e) for e in data["mid"]],
        high=[CatalogEntry(**e) for e in data["high"]],
    )


@router.post("/store/seed")
async def seed_library(
    file: UploadFile,
    hardcore: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    """Upload a .d2i stash file to seed rune entries into the store library."""
    from backend.services.auto_sync import guard_mothership_write
    await guard_mothership_write(session)

    content = await file.read()
    try:
        count = await store_service.seed_rune_library(session, content, hardcore)
    except Exception as e:
        log.error("Store seed failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"seeded": count}


@router.get("/store/tab5-runes", response_model=list[Tab5RuneResponse])
async def get_tab5_runes(
    mode: str = Query("sc"),
    session: AsyncSession = Depends(get_session),
):
    """Return rune items currently on stash tab 5 of the latest local snapshot."""
    runes = await store_service.get_tab5_runes(session, mode)
    return [Tab5RuneResponse(**r) for r in runes]


@router.post("/store/buy", response_model=BuyRuneResponse)
async def buy_rune(
    body: BuyRuneRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Purchase a rune with vault gold. Rune is placed on stash tab 5."""
    from backend.services.auto_sync import guard_mothership_write, trigger_mothership_push
    await guard_mothership_write(session)

    try:
        result = await store_service.buy_rune(session, body.item_code, body.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        log.error("Store buy safety failure: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log.error("Store buy failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    await trigger_mothership_push(background_tasks, session)

    return BuyRuneResponse(vault_gold=result["vault_gold"], rune_name=result["rune_name"])


@router.post("/store/trade", response_model=TradeRuneResponse)
async def trade_rune(
    body: TradeRuneRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Trade a rune on stash tab 5 for another rune of the same tier."""
    from backend.services.auto_sync import guard_mothership_write, trigger_mothership_push
    await guard_mothership_write(session)

    try:
        result = await store_service.trade_rune(
            session, body.tab5_item_index, body.target_code, body.mode
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        log.error("Store trade safety failure: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log.error("Store trade failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    await trigger_mothership_push(background_tasks, session)

    return TradeRuneResponse(source_rune=result["source_rune"], target_rune=result["target_rune"])


@router.delete("/store/library/{item_code}")
async def delete_library_entry(
    item_code: str,
    session: AsyncSession = Depends(get_session),
):
    """Remove a rune from the store library."""
    deleted = await store_service.delete_library_entry(session, item_code)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rune '{item_code}' not found in library")
    return {"deleted": item_code}

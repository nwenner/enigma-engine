from __future__ import annotations

"""
Rewards router — a curated library of items to use as season milestone rewards.

Endpoints:
  POST /api/rewards/validate        — parse hex bytes → item preview (no save)
  GET  /api/rewards                 — list all saved rewards
  POST /api/rewards                 — create a reward (hex + label + notes)
  PATCH /api/rewards/{id}           — update name / notes / category
  DELETE /api/rewards/{id}          — delete a reward
"""
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import SeasonReward

log = logging.getLogger(__name__)
router = APIRouter(tags=["rewards"])

QUALITY_NAMES: dict[int, str] = {
    1: "inferior", 2: "normal", 3: "superior", 4: "magic",
    5: "set", 6: "rare", 7: "unique", 8: "crafted", 9: "tempered",
}


class RewardCategory(str, Enum):
    """Extensible category enum for reward library items.
    Add new values here to extend without schema changes (stored as TEXT)."""
    RUNE               = "Rune"
    RUNEWORD           = "Runeword"
    MATERIAL           = "Material"
    UNIQUE             = "Unique"
    SET_ITEM           = "Set Item"
    KEY                = "Key"
    CHARM              = "Charm"
    WORLDSTONE_SHARD   = "Worldstone Shard"
    UBER_ANCIENT_SUMMON = "Uber Ancient Summon"


def _auto_category(quality: Optional[int]) -> Optional[str]:
    """Infer category from item quality when possible."""
    if quality == 7:
        return RewardCategory.UNIQUE
    if quality == 5:
        return RewardCategory.SET_ITEM
    return None


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    hex: str  # space-separated or continuous hex bytes


class ValidateResponse(BaseModel):
    item_name: Optional[str]
    item_code: Optional[str]
    quality: Optional[int]
    quality_name: Optional[str]
    item_level: Optional[int]
    is_ethereal: Optional[bool]
    byte_len: int
    valid: bool
    error: Optional[str]


class RewardCreate(BaseModel):
    name: str
    hex: str
    notes: Optional[str] = None
    category: Optional[str] = None  # RewardCategory value; None → auto-detect from quality


class RewardUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    category: Optional[str] = None  # Pass empty string "" to clear category


class RewardOut(BaseModel):
    id: int
    name: str
    item_code: Optional[str]
    item_name: Optional[str]
    quality: Optional[int]
    quality_name: Optional[str]
    item_level: Optional[int]
    is_ethereal: bool
    notes: Optional[str]
    category: Optional[str]
    byte_len: int
    created_at: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_bytes(hex_str: str) -> bytes:
    cleaned = hex_str.replace(" ", "").replace("\n", "").replace("\t", "")
    return bytes.fromhex(cleaned)


def _parse_item_bytes(raw: bytes) -> dict:
    """Delegate to the FastAPI-free service module."""
    from backend.services.item_export import parse_item_bytes
    return parse_item_bytes(raw)


async def _resolve_catalog_name(
    session: AsyncSession,
    parsed: dict,
) -> str | None:
    """
    For unique (quality=7) and set (quality=5) items, look up the proper name
    from GrailCatalog.  Falls back to the parser's display_name if no entry exists.
    """
    from backend.models import GrailCatalog
    quality = parsed.get("quality")
    if quality == 7 and parsed.get("unique_id") is not None:
        result = await session.execute(
            select(GrailCatalog).where(GrailCatalog.unique_id == parsed["unique_id"])
        )
        catalog = result.scalar_one_or_none()
        if catalog and catalog.name:
            return catalog.name
    elif quality == 5 and parsed.get("set_id") is not None:
        result = await session.execute(
            select(GrailCatalog).where(GrailCatalog.set_id == parsed["set_id"])
        )
        catalog = result.scalar_one_or_none()
        if catalog and catalog.name:
            return catalog.name
    return parsed.get("item_name")


def _reward_out(r: SeasonReward) -> RewardOut:
    return RewardOut(
        id=r.id,
        name=r.name,
        item_code=r.item_code,
        item_name=r.item_name,
        quality=r.quality,
        quality_name=r.quality_name,
        item_level=r.item_level,
        is_ethereal=r.is_ethereal,
        notes=r.notes,
        category=r.category,
        byte_len=len(r.raw_item_bytes) if r.raw_item_bytes else 0,
        created_at=r.created_at.isoformat(),
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/rewards/categories")
async def list_categories():
    """Return the ordered list of valid reward categories."""
    return {"categories": [c.value for c in RewardCategory]}


@router.post("/rewards/extract-from-stash")
async def extract_from_stash_file(file: UploadFile = File(...)):
    """
    Upload a shared stash .d2i file (from Hero Editor or the game).
    Returns one entry per non-empty tab with item info and raw page bytes.
    The raw bytes are in the exact format D2R expects — safe for reward insertion.
    """
    from backend.services.item_parsing.stash_format import parse_stash

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        stash = parse_stash(data, hardcore=False)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse stash file: {e}")

    tabs = []
    for i, page in enumerate(stash.pages):
        if not page.raw_bytes or page.jm_item_count == 0:
            continue
        raw_bytes = bytes(page.raw_bytes)
        parsed = _parse_item_bytes(raw_bytes)
        tabs.append({
            "tab_index": i,
            "jm_item_count": page.jm_item_count,
            "byte_len": len(raw_bytes),
            "hex": " ".join(f"{b:02x}" for b in raw_bytes),
            **parsed,
        })

    if not tabs:
        raise HTTPException(400, "No items found in this stash file")

    return {"filename": file.filename, "tabs": tabs}


@router.post("/rewards/validate", response_model=ValidateResponse)
async def validate_reward(body: ValidateRequest):
    """Parse hex bytes and return item info. Does not save anything."""
    try:
        raw = _hex_to_bytes(body.hex)
    except ValueError as e:
        raise HTTPException(400, f"Invalid hex: {e}")

    parsed = _parse_item_bytes(raw)
    return ValidateResponse(byte_len=len(raw), **parsed)


@router.get("/rewards", response_model=list[RewardOut])
async def list_rewards(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SeasonReward).order_by(SeasonReward.created_at.desc())
    )
    return [_reward_out(r) for r in result.scalars().all()]


@router.post("/rewards", response_model=RewardOut)
async def create_reward(body: RewardCreate, session: AsyncSession = Depends(get_session)):
    if not body.name.strip():
        raise HTTPException(400, "Name is required")

    try:
        raw = _hex_to_bytes(body.hex)
    except ValueError as e:
        raise HTTPException(400, f"Invalid hex: {e}")

    if not raw:
        raise HTTPException(400, "Hex bytes cannot be empty")

    parsed = _parse_item_bytes(raw)
    item_name = await _resolve_catalog_name(session, parsed)

    # Use explicit category if provided, otherwise auto-detect from quality
    category = body.category or _auto_category(parsed.get("quality"))

    reward = SeasonReward(
        name=body.name.strip(),
        item_code=parsed["item_code"],
        item_name=item_name,
        quality=parsed["quality"],
        quality_name=parsed["quality_name"],
        item_level=parsed["item_level"],
        is_ethereal=parsed["is_ethereal"] or False,
        raw_item_bytes=raw,
        notes=body.notes,
        category=category,
        created_at=datetime.now(timezone.utc),
    )
    session.add(reward)
    await session.commit()
    return _reward_out(reward)


class RegisterFromSnapshotRequest(BaseModel):
    mode: str  # "sc" | "hc"
    item_index: int
    name: str
    category: Optional[str] = None
    notes: Optional[str] = None


@router.post("/rewards/register-from-snapshot", response_model=RewardOut)
async def register_reward_from_snapshot(
    body: RegisterFromSnapshotRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Register an item from stash tab 5 of the latest local snapshot as a season reward.
    Non-destructive — item stays in the stash. Only the bytes are copied.
    """
    from backend.services.grail_service import _latest_snapshot, _snapshot_dir
    from backend.services.item_parsing import parse_stash
    from backend.services.item_parsing.stash_format import validate_page_items

    if not body.name.strip():
        raise HTTPException(400, "Name is required")

    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    hardcore = body.mode == "hc"
    stash_filename = "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"
    stash_path = snap_dir / stash_filename

    if not stash_path.exists():
        raise HTTPException(404, f"{stash_filename} not found in latest snapshot")

    try:
        stash = parse_stash(stash_path, hardcore=hardcore)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse stash: {e}")

    PORTAL_TAB_INDEX = 4
    if len(stash.pages) <= PORTAL_TAB_INDEX:
        raise HTTPException(400, "Stash has fewer than 5 tabs")

    portal_page = stash.pages[PORTAL_TAB_INDEX]
    if not validate_page_items(portal_page):
        raise HTTPException(400, "Tab 5 failed validation")

    if body.item_index < 0 or body.item_index >= len(portal_page.items):
        raise HTTPException(400, f"Item index {body.item_index} out of range (tab 5 has {len(portal_page.items)} items)")

    item = portal_page.items[body.item_index]
    raw = bytes(portal_page.raw_bytes[item.byte_start : item.byte_end])

    parsed = _parse_item_bytes(raw)
    item_name = await _resolve_catalog_name(session, parsed)
    category = body.category or _auto_category(parsed.get("quality"))

    reward = SeasonReward(
        name=body.name.strip(),
        item_code=parsed["item_code"],
        item_name=item_name,
        quality=parsed["quality"],
        quality_name=parsed["quality_name"],
        item_level=parsed["item_level"],
        is_ethereal=parsed["is_ethereal"] or False,
        raw_item_bytes=raw,
        notes=body.notes or None,
        category=category,
        created_at=datetime.now(timezone.utc),
    )
    session.add(reward)
    await session.commit()
    log.info("Registered reward '%s' from snapshot tab 5 (%d bytes)", body.name, len(raw))
    return _reward_out(reward)


@router.patch("/rewards/{reward_id}", response_model=RewardOut)
async def update_reward(
    reward_id: int,
    body: RewardUpdate,
    session: AsyncSession = Depends(get_session),
):
    reward = await session.get(SeasonReward, reward_id)
    if reward is None:
        raise HTTPException(404, "Reward not found")

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "Name cannot be empty")
        reward.name = body.name.strip()
    if body.notes is not None:
        reward.notes = body.notes or None
    if body.category is not None:
        reward.category = body.category.strip() or None  # empty string clears it

    await session.commit()
    return _reward_out(reward)


@router.delete("/rewards/{reward_id}")
async def delete_reward(reward_id: int, session: AsyncSession = Depends(get_session)):
    reward = await session.get(SeasonReward, reward_id)
    if reward is None:
        raise HTTPException(404, "Reward not found")
    await session.delete(reward)
    await session.commit()
    return {"success": True}


@router.get("/rewards/{reward_id}/bytes")
async def get_reward_bytes(reward_id: int, session: AsyncSession = Depends(get_session)):
    """Return the raw hex bytes for a reward (for copying into milestone fields)."""
    reward = await session.get(SeasonReward, reward_id)
    if reward is None:
        raise HTTPException(404, "Reward not found")
    raw = bytes(reward.raw_item_bytes)
    return {
        "hex": " ".join(f"{b:02x}" for b in raw),
        "byte_len": len(raw),
        "name": reward.name,
    }

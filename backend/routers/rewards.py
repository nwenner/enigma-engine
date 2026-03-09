from __future__ import annotations

"""
Rewards router — a curated library of items to use as season milestone rewards.

Endpoints:
  POST /api/rewards/validate        — parse hex bytes → item preview (no save)
  GET  /api/rewards                 — list all saved rewards
  POST /api/rewards                 — create a reward (hex + label + notes)
  PATCH /api/rewards/{id}           — update name / notes
  DELETE /api/rewards/{id}          — delete a reward
"""
import logging
from datetime import datetime, timezone
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


class RewardUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None


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
        byte_len=len(r.raw_item_bytes) if r.raw_item_bytes else 0,
        created_at=r.created_at.isoformat(),
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/rewards/extract-from-item")
async def extract_from_item_file(file: UploadFile = File(...)):
    """
    Upload a single-item .d2i file exported by Hero Editor.
    The file contains raw item bytes starting at offset 0 — no header, no JM wrapper.
    Returns parsed item info + hex bytes ready to save to the rewards library.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")

    parsed = _parse_item_bytes(data)
    return {
        "filename": file.filename,
        "hex": " ".join(f"{b:02x}" for b in data),
        "byte_len": len(data),
        **parsed,
    }


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

    reward = SeasonReward(
        name=body.name.strip(),
        item_code=parsed["item_code"],
        item_name=parsed["item_name"],
        quality=parsed["quality"],
        quality_name=parsed["quality_name"],
        item_level=parsed["item_level"],
        is_ethereal=parsed["is_ethereal"] or False,
        raw_item_bytes=raw,
        notes=body.notes,
        created_at=datetime.now(timezone.utc),
    )
    session.add(reward)
    await session.commit()
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

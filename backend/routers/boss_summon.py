from __future__ import annotations

"""
Boss Summon Portals router.

GET  /api/boss-summon                      → list all 4 sets + season progress
POST /api/boss-summon/{set_id}/summon      → insert items into portal tab 5
POST /api/boss-summon/{set_id}/earn        → manually mark a code as earned
DELETE /api/boss-summon/{set_id}/reset     → reset progress for a set
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.services.boss_summon_service import (
    list_summon_status,
    summon_boss_set,
    earn_code_manually,
    reset_summon_progress,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/boss-summon", tags=["boss-summon"])


class EarnCodeRequest(BaseModel):
    code: str


@router.get("")
async def get_boss_portals(session: AsyncSession = Depends(get_session)):
    """List all boss summon sets with current season progress."""
    return await list_summon_status(session)


@router.post("/{set_id}/summon")
async def summon(
    set_id: str,
    hardcore: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
):
    """Insert the required summon items into portal tab 5 of the latest snapshot."""
    try:
        return await summon_boss_set(session, set_id, hardcore=hardcore)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/{set_id}/earn")
async def earn_code(
    set_id: str,
    body: EarnCodeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Manually mark a specific item code as earned (fallback if auto-detect misses)."""
    try:
        return await earn_code_manually(session, set_id, body.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.delete("/{set_id}/reset")
async def reset_progress(
    set_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Reset progress for a set in the active season."""
    try:
        return await reset_summon_progress(session, set_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))

from __future__ import annotations

"""
Auto-sync router.

Endpoints:
  GET  /api/autosync/status  - Current auto-sync state + config
  PUT  /api/autosync/config  - Enable/disable and set poll interval
  POST /api/autosync/dismiss - Clear pending/conflict state
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session
from backend.models import Settings
from backend.routers.settings import _get_setting, _set_setting

log = logging.getLogger(__name__)
router = APIRouter(tags=["autosync"])

IDLE_STATE = {
    "status": "idle",
    "direction": None,
    "detected_at": None,
    "expires_at": None,
    "reason": None,
}


# ─── Schema ───────────────────────────────────────────────────────────────────


class AutoSyncStatusResponse(BaseModel):
    enabled: bool
    poll_interval: int
    state: Optional[dict] = None


class AutoSyncConfigRequest(BaseModel):
    enabled: bool
    poll_interval_seconds: int


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.get("/autosync/status", response_model=AutoSyncStatusResponse)
async def get_autosync_status(session: AsyncSession = Depends(get_session)):
    enabled_raw = await _get_setting(session, "autosync_enabled")
    enabled = (enabled_raw or "false").lower() == "true"

    interval_raw = await _get_setting(session, "autosync_poll_interval")
    try:
        interval = int(interval_raw or "30")
    except ValueError:
        interval = 30

    state_raw = await _get_setting(session, "autosync_state")
    state: Optional[dict] = None
    if state_raw:
        try:
            parsed = json.loads(state_raw)
            if parsed.get("status", "idle") != "idle":
                state = parsed
        except Exception:
            pass

    return AutoSyncStatusResponse(enabled=enabled, poll_interval=interval, state=state)


@router.put("/autosync/config", response_model=AutoSyncStatusResponse)
async def update_autosync_config(
    body: AutoSyncConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    await _set_setting(session, "autosync_enabled", "true" if body.enabled else "false")
    await _set_setting(session, "autosync_poll_interval", str(body.poll_interval_seconds))
    await session.commit()

    return AutoSyncStatusResponse(
        enabled=body.enabled,
        poll_interval=body.poll_interval_seconds,
        state=None,
    )


@router.post("/autosync/dismiss")
async def dismiss_autosync(session: AsyncSession = Depends(get_session)):
    await _set_setting(session, "autosync_state", json.dumps(IDLE_STATE))
    await session.commit()
    return {"success": True}

from __future__ import annotations

"""
Auto-sync router.

Endpoints:
  GET  /api/autosync/status  - Current auto-sync state + config
  PUT  /api/autosync/config  - Enable/disable and set poll interval
  POST /api/autosync/dismiss - Clear pending/conflict state
  POST /api/autosync/trigger - Manually dispatch a pending sync now
"""

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session
from backend.models import Settings, SyncOperation
from backend.routers.settings import _get_conn_kwargs, _get_setting, _set_setting

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
    pc_enabled: bool
    deck_enabled: bool
    state: Optional[dict] = None


class AutoSyncConfigRequest(BaseModel):
    enabled: bool
    poll_interval_seconds: int
    pc_enabled: bool
    deck_enabled: bool


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

    pc_enabled_raw = await _get_setting(session, "autosync_pc_enabled")
    pc_enabled = (pc_enabled_raw or "true").lower() == "true"

    deck_enabled_raw = await _get_setting(session, "autosync_deck_enabled")
    deck_enabled = (deck_enabled_raw or "true").lower() == "true"

    state_raw = await _get_setting(session, "autosync_state")
    state: Optional[dict] = None
    if state_raw:
        try:
            parsed = json.loads(state_raw)
            if parsed.get("status", "idle") != "idle":
                state = parsed
        except Exception:
            pass

    return AutoSyncStatusResponse(
        enabled=enabled,
        poll_interval=interval,
        pc_enabled=pc_enabled,
        deck_enabled=deck_enabled,
        state=state,
    )


@router.put("/autosync/config", response_model=AutoSyncStatusResponse)
async def update_autosync_config(
    body: AutoSyncConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    await _set_setting(session, "autosync_enabled", "true" if body.enabled else "false")
    await _set_setting(session, "autosync_poll_interval", str(body.poll_interval_seconds))
    await _set_setting(session, "autosync_pc_enabled", "true" if body.pc_enabled else "false")
    await _set_setting(session, "autosync_deck_enabled", "true" if body.deck_enabled else "false")
    await session.commit()

    return AutoSyncStatusResponse(
        enabled=body.enabled,
        poll_interval=body.poll_interval_seconds,
        pc_enabled=body.pc_enabled,
        deck_enabled=body.deck_enabled,
        state=None,
    )


@router.post("/autosync/trigger")
async def trigger_autosync(session: AsyncSession = Depends(get_session)):
    """Manually dispatch the pending sync right now (uses staged files if available)."""
    from backend.routers.sync import do_sync, sync_lock, _build_sync_kwargs

    state_raw = await _get_setting(session, "autosync_state")
    if not state_raw:
        raise HTTPException(400, "No pending auto-sync state")
    try:
        state = json.loads(state_raw)
    except Exception:
        raise HTTPException(400, "Invalid auto-sync state")

    if state.get("status") != "pending" or not state.get("direction"):
        raise HTTPException(400, "No pending auto-sync to trigger")

    if sync_lock.locked():
        raise HTTPException(409, "A sync operation is already in progress")

    direction = state["direction"]
    staged_path = state.get("staged_path")

    sync_kwargs = await _build_sync_kwargs(session, direction)
    if staged_path:
        sync_kwargs["staged_path"] = staged_path

    # Clear state before dispatching so watcher doesn't re-trigger
    await _set_setting(session, "autosync_state", json.dumps(IDLE_STATE))

    op = SyncOperation(direction=direction, status="pending")
    session.add(op)
    await session.commit()
    await session.refresh(op)

    asyncio.create_task(do_sync(op.id, sync_kwargs))
    return {"success": True, "operation_id": op.id}


@router.post("/autosync/dismiss")
async def dismiss_autosync(session: AsyncSession = Depends(get_session)):
    await _set_setting(session, "autosync_state", json.dumps(IDLE_STATE))
    await session.commit()
    return {"success": True}


class ResolveConflictRequest(BaseModel):
    keep_machine: Literal["pc", "deck"]


@router.post("/autosync/resolve")
async def resolve_conflict(
    body: ResolveConflictRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Resolve a conflict by picking which machine's saves to keep.
    Clears conflict state and triggers a check-in from the winning machine."""
    from backend.routers.sync import do_checkin

    # Clear conflict state
    await _set_setting(session, "autosync_state", json.dumps(IDLE_STATE))

    machine = body.keep_machine
    try:
        conn_kwargs = await _get_conn_kwargs(session, machine)
        save_dir = await _get_setting(session, f"{machine}_save_path") or ""
    except Exception as exc:
        await session.commit()
        raise HTTPException(400, f"Could not get connection settings for {machine}: {exc}")

    op = SyncOperation(direction=f"checkin_{machine}", status="pending")
    session.add(op)
    await session.commit()
    await session.refresh(op)

    background_tasks.add_task(do_checkin, op.id, machine, conn_kwargs, save_dir)
    return {"op_id": op.id, "machine": machine}

from __future__ import annotations

"""
Sync router.

A module-level asyncio.Lock prevents concurrent sync operations.

Endpoints:
  POST /api/sync                  - Start a new sync operation
  GET  /api/sync/last             - Return last successful sync operation
  GET  /api/sync/{id}/status      - Poll status of a sync operation
  GET  /api/sync/preflight        - Check if D2R is running on either machine
"""
import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session, AsyncSessionLocal
from backend.models import SyncOperation
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.backup_manager import run_sync
from backend.services.ssh_client import get_sftp, check_d2r_running, SSHConnectionError

log = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])

sync_lock = asyncio.Lock()


class SyncRequest(BaseModel):
    direction: Literal["pc_to_deck", "deck_to_pc"]


class SyncStatusResponse(BaseModel):
    id: int
    direction: str
    status: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    file_count: int


class PreflightResponse(BaseModel):
    pc_running: Optional[bool] = None   # None = could not check
    deck_running: Optional[bool] = None
    pc_error: Optional[str] = None
    deck_error: Optional[str] = None
    safe_to_sync: bool = False


async def _build_sync_kwargs(session: AsyncSession, direction: str) -> dict:
    if direction == "pc_to_deck":
        source, dest = "pc", "deck"
    else:
        source, dest = "deck", "pc"

    source_conn = await _get_conn_kwargs(session, source)
    dest_conn = await _get_conn_kwargs(session, dest)
    source_dir = await _get_setting(session, f"{source}_save_path") or ""
    dest_dir = await _get_setting(session, f"{dest}_save_path") or ""

    return dict(
        source_machine=source,
        dest_machine=dest,
        source_conn=source_conn,
        dest_conn=dest_conn,
        source_dir=source_dir,
        dest_dir=dest_dir,
        source_is_windows=(source == "pc"),
        dest_is_windows=(dest == "pc"),
    )


async def do_sync(operation_id: int, sync_kwargs: dict) -> None:
    """Background task: acquire lock then run sync with its own DB session."""
    from backend.config import get_settings
    staged_path_str = sync_kwargs.get("staged_path")
    if staged_path_str:
        sync_kwargs = {**sync_kwargs, "staged_path": Path(staged_path_str)}

    async with sync_lock:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SyncOperation).where(SyncOperation.id == operation_id)
            )
            operation = result.scalar_one_or_none()
            if not operation:
                log.error("Sync operation %d not found", operation_id)
                return

            try:
                await run_sync(session=session, operation=operation, **sync_kwargs)
            except Exception:
                pass  # Status already set to failed in run_sync
            finally:
                # Only clean up if staged_path is inside staging_dir (legacy staging).
                # Snapshot dirs (under backups_dir) are managed by the prune system.
                if staged_path_str:
                    staged = Path(staged_path_str)
                    cfg = get_settings()
                    if staged.is_relative_to(cfg.staging_dir):
                        shutil.rmtree(staged, ignore_errors=True)


@router.get("/sync/last", response_model=Optional[SyncStatusResponse])
async def get_last_sync(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SyncOperation)
        .where(SyncOperation.status == "success")
        .order_by(SyncOperation.completed_at.desc())
        .limit(1)
    )
    op = result.scalar_one_or_none()
    if not op:
        return None
    return SyncStatusResponse(
        id=op.id,
        direction=op.direction,
        status=op.status,
        error_message=op.error_message,
        started_at=op.started_at,
        completed_at=op.completed_at,
        file_count=op.file_count,
    )


@router.post("/sync", response_model=SyncStatusResponse, status_code=202)
async def start_sync(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    if sync_lock.locked():
        raise HTTPException(409, "A sync operation is already in progress")

    sync_kwargs = await _build_sync_kwargs(session, body.direction)

    operation = SyncOperation(direction=body.direction, status="pending")
    session.add(operation)
    await session.commit()
    await session.refresh(operation)

    background_tasks.add_task(do_sync, operation.id, sync_kwargs)

    return SyncStatusResponse(
        id=operation.id,
        direction=operation.direction,
        status=operation.status,
        error_message=operation.error_message,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
        file_count=operation.file_count,
    )


@router.get("/sync/preflight", response_model=PreflightResponse)
async def preflight_check(session: AsyncSession = Depends(get_session)):
    import asyncio

    async def _check(machine: str, is_windows: bool):
        try:
            kwargs = await _get_conn_kwargs(session, machine)
            def _do():
                with get_sftp(**kwargs) as (ssh, _sftp):
                    return check_d2r_running(ssh, is_windows)
            return await asyncio.to_thread(_do), None
        except SSHConnectionError as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

    pc_running, pc_err = await _check("pc", True)
    deck_running, deck_err = await _check("deck", False)

    safe = (pc_running is False) and (deck_running is False)

    return PreflightResponse(
        pc_running=pc_running,
        deck_running=deck_running,
        pc_error=pc_err,
        deck_error=deck_err,
        safe_to_sync=safe,
    )


@router.get("/sync/{sync_id}/status", response_model=SyncStatusResponse)
async def get_sync_status(sync_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SyncOperation).where(SyncOperation.id == sync_id)
    )
    operation = result.scalar_one_or_none()
    if not operation:
        raise HTTPException(404, f"Sync operation {sync_id} not found")

    return SyncStatusResponse(
        id=operation.id,
        direction=operation.direction,
        status=operation.status,
        error_message=operation.error_message,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
        file_count=operation.file_count,
    )

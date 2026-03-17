from __future__ import annotations

"""
Sync router.

A module-level asyncio.Lock prevents concurrent sync operations.

Endpoints:
  POST /api/sync                  - Start a legacy sync operation (kept for history compat)
  GET  /api/sync/last             - Return last successful sync operation
  GET  /api/sync/{id}/status      - Poll status of a sync operation
  GET  /api/sync/preflight        - Check if D2R is running on either machine
  POST /api/checkin               - Check In from a device (pull saves → app snapshot)
  POST /api/sync/push             - Push latest snapshot to a device
  GET  /api/sync/compare          - Compare device file mtimes vs app's known state
"""
import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session, AsyncSessionLocal
from backend.models import SyncOperation, Character, Season, BackupSnapshot
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.backup_manager import run_sync, create_snapshot, push_snapshot_to_machine
from backend.services.ssh_client import get_sftp, check_d2r_running, SSHConnectionError, list_all_files, CONNECT_TIMEOUT

log = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])

sync_lock = asyncio.Lock()


class SyncRequest(BaseModel):
    direction: Literal["pc_to_deck", "deck_to_pc"]


class CheckInRequest(BaseModel):
    machine: Literal["pc", "deck"]


class PushRequest(BaseModel):
    machine: Literal["pc", "deck"]


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


class FileCompareEntry(BaseModel):
    filename: str
    device_mtime: Optional[float]
    app_mtime: Optional[float]


class SyncCompareResponse(BaseModel):
    device_older: list[FileCompareEntry]   # device mtime older than app's known mtime
    device_newer: list[FileCompareEntry]   # device mtime newer than app's known mtime
    device_only: list[FileCompareEntry]    # on device, not in app DB
    app_only: list[FileCompareEntry]       # in app DB, not on device
    has_app_data: bool                     # False = no characters in DB (skip guards)
    pushed_since_season_start: bool        # False = no push to this machine since season started


class MachineSyncSummary(BaseModel):
    last_checkin_at: Optional[datetime]
    last_push_at: Optional[datetime]


class VaultSummary(BaseModel):
    snapshot_at: Optional[datetime]
    source_machine: Optional[str]
    file_count: int


class SyncSummaryResponse(BaseModel):
    vault: VaultSummary
    pc: MachineSyncSummary
    deck: MachineSyncSummary


COMPARE_THRESHOLD_SECONDS = 60


def _build_sync_status(op: SyncOperation) -> SyncStatusResponse:
    return SyncStatusResponse(
        id=op.id,
        direction=op.direction,
        status=op.status,
        error_message=op.error_message,
        started_at=op.started_at,
        completed_at=op.completed_at,
        file_count=op.file_count,
    )


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
                if staged_path_str:
                    staged = Path(staged_path_str)
                    cfg = get_settings()
                    if staged.is_relative_to(cfg.staging_dir):
                        shutil.rmtree(staged, ignore_errors=True)


async def do_checkin(operation_id: int, machine: str, conn_kwargs: dict, save_dir: str) -> None:
    """Background task: download saves from device → snapshot → grail/season hooks."""
    async with sync_lock:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SyncOperation).where(SyncOperation.id == operation_id)
            )
            operation = result.scalar_one_or_none()
            if not operation:
                log.error("CheckIn operation %d not found", operation_id)
                return

            try:
                operation.status = "running"
                await session.commit()

                snapshot = await create_snapshot(
                    session=session,
                    machine=machine,
                    conn_kwargs=conn_kwargs,
                    save_dir=save_dir,
                    label="manual",
                    sync_operation_id=operation_id,
                )

                from backend.config import get_settings
                cfg = get_settings()
                snapshot_dir = cfg.data_dir / snapshot.snapshot_path
                downloaded = [
                    {"filename": f.name, "local_part": f}
                    for f in snapshot_dir.iterdir()
                    if f.is_file()
                ]

                try:
                    from backend.services.grail_service import process_portal_tab_hook
                    await process_portal_tab_hook(session=session, downloaded=downloaded)
                except Exception as e:
                    log.warning("CheckIn: grail hook failed (unaffected): %s", e)

                try:
                    from backend.services.seasons_service import check_season_milestones
                    await check_season_milestones(session=session, downloaded=downloaded)
                except Exception as e:
                    log.warning("CheckIn: seasons hook failed (unaffected): %s", e)

                try:
                    from backend.services.boss_summon_service import check_boss_summon_progress
                    await check_boss_summon_progress(session=session, snapshot_dir=snapshot_dir)
                except Exception as e:
                    log.warning("CheckIn: boss summon progress hook failed (unaffected): %s", e)

                operation.status = "success"
                operation.file_count = snapshot.file_count
                operation.completed_at = datetime.now(timezone.utc)
                await session.commit()

            except Exception as e:
                log.error("CheckIn operation %d failed: %s", operation_id, e)
                operation.status = "failed"
                operation.error_message = str(e)
                operation.completed_at = datetime.now(timezone.utc)
                await session.commit()


async def do_push(operation_id: int, machine: str, conn_kwargs: dict, save_dir: str, is_windows: bool) -> None:
    """Background task: push latest snapshot to device."""
    async with sync_lock:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SyncOperation).where(SyncOperation.id == operation_id)
            )
            operation = result.scalar_one_or_none()
            if not operation:
                log.error("Push operation %d not found", operation_id)
                return

            try:
                operation.status = "running"
                await session.commit()

                removed, uploaded = await push_snapshot_to_machine(
                    session=session,
                    machine=machine,
                    conn_kwargs=conn_kwargs,
                    save_dir=save_dir,
                    is_windows=is_windows,
                )

                operation.status = "success"
                operation.file_count = uploaded
                operation.completed_at = datetime.now(timezone.utc)
                await session.commit()

            except Exception as e:
                log.error("Push operation %d failed: %s", operation_id, e)
                operation.status = "failed"
                operation.error_message = str(e)
                operation.completed_at = datetime.now(timezone.utc)
                await session.commit()


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
    return _build_sync_status(op)


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

    return _build_sync_status(operation)


@router.post("/checkin", response_model=SyncStatusResponse, status_code=202)
async def checkin(
    body: CheckInRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Pull saves from a device into the app (creates a manual snapshot)."""
    if sync_lock.locked():
        raise HTTPException(409, "A sync operation is already in progress")

    try:
        conn_kwargs = await _get_conn_kwargs(session, body.machine)
        save_dir = await _get_setting(session, f"{body.machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(400, f"Config error: {e}")

    if not conn_kwargs.get("host"):
        raise HTTPException(400, f"{body.machine.upper()} is not configured")
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {body.machine.upper()}")

    direction = f"checkin_{body.machine}"
    operation = SyncOperation(direction=direction, status="pending")
    session.add(operation)
    await session.commit()
    await session.refresh(operation)

    is_windows = body.machine == "pc"
    background_tasks.add_task(do_checkin, operation.id, body.machine, conn_kwargs, save_dir)

    return _build_sync_status(operation)


@router.post("/sync/push", response_model=SyncStatusResponse, status_code=202)
async def push_to_device(
    body: PushRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Push the latest app snapshot to a device (full mirror)."""
    if sync_lock.locked():
        raise HTTPException(409, "A sync operation is already in progress")

    try:
        conn_kwargs = await _get_conn_kwargs(session, body.machine)
        save_dir = await _get_setting(session, f"{body.machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(400, f"Config error: {e}")

    if not conn_kwargs.get("host"):
        raise HTTPException(400, f"{body.machine.upper()} is not configured")
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {body.machine.upper()}")

    direction = f"app_to_{body.machine}"
    operation = SyncOperation(direction=direction, status="pending")
    session.add(operation)
    await session.commit()
    await session.refresh(operation)

    is_windows = body.machine == "pc"
    background_tasks.add_task(do_push, operation.id, body.machine, conn_kwargs, save_dir, is_windows)

    return _build_sync_status(operation)


@router.get("/sync/summary", response_model=SyncSummaryResponse)
async def get_sync_summary(session: AsyncSession = Depends(get_session)):
    """Return per-machine last check-in / last push timestamps plus vault snapshot info."""
    snap_result = await session.execute(
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    snap = snap_result.scalar_one_or_none()

    async def _last(*directions: str) -> Optional[datetime]:
        r = await session.execute(
            select(SyncOperation.completed_at)
            .where(SyncOperation.direction.in_(directions), SyncOperation.status == "success")
            .order_by(SyncOperation.completed_at.desc())
            .limit(1)
        )
        return r.scalar_one_or_none()

    pc_checkin = await _last("checkin_pc")
    pc_push = await _last("app_to_pc", "deck_to_pc")
    deck_checkin = await _last("checkin_deck")
    deck_push = await _last("app_to_deck", "pc_to_deck")

    return SyncSummaryResponse(
        vault=VaultSummary(
            snapshot_at=snap.created_at if snap else None,
            source_machine=snap.source_machine if snap else None,
            file_count=snap.file_count if snap else 0,
        ),
        pc=MachineSyncSummary(last_checkin_at=pc_checkin, last_push_at=pc_push),
        deck=MachineSyncSummary(last_checkin_at=deck_checkin, last_push_at=deck_push),
    )


@router.get("/sync/compare", response_model=SyncCompareResponse)
async def compare_with_device(
    machine: Literal["pc", "deck"] = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Compare .d2s file mtimes on the device against Character.modified_at in the DB.
    Used as a pre-flight guard before Check In or Sync to Device.
    """
    try:
        conn_kwargs = await _get_conn_kwargs(session, machine)
        save_dir = await _get_setting(session, f"{machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(400, f"Config error: {e}")

    if not conn_kwargs.get("host"):
        raise HTTPException(400, f"{machine.upper()} is not configured")

    # Get app's known state
    chars_result = await session.execute(select(Character).where(Character.season_id == None))
    app_chars: dict[str, float] = {
        c.filename: c.modified_at
        for c in chars_result.scalars().all()
        if c.filename
    }
    has_app_data = len(app_chars) > 0

    # Check if this machine has been pushed to since the active season started
    active_season_result = await session.execute(
        select(Season).where(Season.status == "active")
    )
    active_season = active_season_result.scalar_one_or_none()

    if active_season and active_season.started_at:
        push_result = await session.execute(
            select(SyncOperation).where(
                SyncOperation.direction == f"app_to_{machine}",
                SyncOperation.status == "success",
                SyncOperation.completed_at >= active_season.started_at,
            ).limit(1)
        )
        pushed_since_season_start = push_result.scalar_one_or_none() is not None
    else:
        pushed_since_season_start = True  # No active season → no guard needed

    # Get device state
    try:
        def _list_device() -> list[dict]:
            with get_sftp(**conn_kwargs) as (_ssh, sftp):
                return list_all_files(sftp, save_dir)

        device_files_raw = await asyncio.to_thread(_list_device)
    except Exception as e:
        raise HTTPException(502, f"Cannot reach {machine.upper()}: {e}")

    device_d2s: dict[str, float] = {
        f["filename"]: f["modified_at"]
        for f in device_files_raw
        if f["filename"].endswith(".d2s")
    }

    device_older: list[FileCompareEntry] = []
    device_newer: list[FileCompareEntry] = []
    device_only: list[FileCompareEntry] = []
    app_only: list[FileCompareEntry] = []

    all_filenames = set(device_d2s) | set(app_chars)
    for fname in sorted(all_filenames):
        dmtime = device_d2s.get(fname)
        amtime = app_chars.get(fname)

        if dmtime is not None and amtime is not None:
            diff = dmtime - amtime
            if diff < -COMPARE_THRESHOLD_SECONDS:
                device_older.append(FileCompareEntry(filename=fname, device_mtime=dmtime, app_mtime=amtime))
            elif diff > COMPARE_THRESHOLD_SECONDS:
                device_newer.append(FileCompareEntry(filename=fname, device_mtime=dmtime, app_mtime=amtime))
        elif dmtime is not None and amtime is None:
            device_only.append(FileCompareEntry(filename=fname, device_mtime=dmtime, app_mtime=None))
        elif amtime is not None and dmtime is None:
            app_only.append(FileCompareEntry(filename=fname, device_mtime=None, app_mtime=amtime))

    return SyncCompareResponse(
        device_older=device_older,
        device_newer=device_newer,
        device_only=device_only,
        app_only=app_only,
        has_app_data=has_app_data,
        pushed_since_season_start=pushed_since_season_start,
    )


PREFLIGHT_TIMEOUT = CONNECT_TIMEOUT  # same timeout as watcher — deck SSH can be slow

@router.get("/sync/preflight", response_model=PreflightResponse)
async def preflight_check(session: AsyncSession = Depends(get_session)):
    # Fetch connection kwargs sequentially — session cannot be used concurrently
    try:
        pc_kwargs = await _get_conn_kwargs(session, "pc")
    except Exception as e:
        pc_kwargs = None

    try:
        deck_kwargs = await _get_conn_kwargs(session, "deck")
    except Exception as e:
        deck_kwargs = None

    async def _check(kwargs: dict | None, is_windows: bool):
        if kwargs is None:
            return None, "No connection configured"
        try:
            def _do():
                with get_sftp(**kwargs, connect_timeout=PREFLIGHT_TIMEOUT) as (ssh, _sftp):
                    return check_d2r_running(ssh, is_windows)
            return await asyncio.to_thread(_do), None
        except SSHConnectionError as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

    (pc_running, pc_err), (deck_running, deck_err) = await asyncio.gather(
        _check(pc_kwargs, True),
        _check(deck_kwargs, False),
    )

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

    return _build_sync_status(operation)

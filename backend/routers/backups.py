from __future__ import annotations

"""
Backups router.

Endpoints:
  GET    /api/backups                  - List all backup snapshots
  DELETE /api/backups/{id}             - Delete a backup snapshot
  POST   /api/backups/{id}/restore     - Restore a snapshot to its machine
  POST   /api/backups/snapshot         - Create a manual snapshot for a machine
"""
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.config import get_settings
from backend.database import get_session, AsyncSessionLocal
from backend.models import BackupSnapshot
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.ssh_client import get_sftp, normalize_path, SSHConnectionError

log = logging.getLogger(__name__)
router = APIRouter(tags=["backups"])


class SnapshotResponse(BaseModel):
    id: int
    source_machine: str
    snapshot_path: str
    file_count: int
    characters: Optional[list] = None
    created_at: str
    sync_operation_id: Optional[int] = None
    label: str = "pre_sync"


@router.get("/backups", response_model=list[SnapshotResponse])
async def list_backups(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(BackupSnapshot).order_by(BackupSnapshot.created_at.desc())
    )
    snapshots = result.scalars().all()
    return [
        SnapshotResponse(
            id=s.id,
            source_machine=s.source_machine,
            snapshot_path=s.snapshot_path,
            file_count=s.file_count,
            characters=s.characters,
            created_at=s.created_at.isoformat(),
            sync_operation_id=s.sync_operation_id,
            label=s.label or "pre_sync",
        )
        for s in snapshots
    ]


@router.delete("/backups/{backup_id}", status_code=204)
async def delete_backup(backup_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(BackupSnapshot).where(BackupSnapshot.id == backup_id)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(404, f"Backup {backup_id} not found")

    cfg = get_settings()
    snap_path = cfg.data_dir / snap.snapshot_path
    if snap_path.exists():
        shutil.rmtree(snap_path, ignore_errors=True)

    await session.delete(snap)
    await session.commit()


class RestoreResponse(BaseModel):
    success: bool
    message: str
    files_restored: int


@router.post("/backups/{backup_id}/restore", response_model=RestoreResponse)
async def restore_backup(backup_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(BackupSnapshot).where(BackupSnapshot.id == backup_id)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(404, f"Backup {backup_id} not found")

    cfg = get_settings()
    snap_path = cfg.data_dir / snap.snapshot_path
    if not snap_path.exists():
        raise HTTPException(404, f"Backup files not found on disk at {snap.snapshot_path}")

    machine = snap.source_machine  # restore back to the machine it was backed up from
    try:
        conn_kwargs = await _get_conn_kwargs(session, machine)
        save_path = await _get_setting(session, f"{machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(502, f"Config error: {e}")

    if not save_path:
        raise HTTPException(422, f"{machine.upper()} save path not configured")

    def _restore():
        files_restored = 0
        with get_sftp(**conn_kwargs) as (_ssh, sftp):
            for local_file in snap_path.iterdir():
                if local_file.is_file():
                    remote = normalize_path(f"{save_path}/{local_file.name}")
                    sftp.put(str(local_file), remote)
                    files_restored += 1
        return files_restored

    try:
        count = await asyncio.to_thread(_restore)
        return RestoreResponse(
            success=True,
            message=f"Restored {count} files to {machine.upper()}",
            files_restored=count,
        )
    except SSHConnectionError as e:
        raise HTTPException(502, f"SSH error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Restore failed: {e}")


class SnapshotRequest(BaseModel):
    machine: Literal["pc", "deck"]


@router.post("/backups/snapshot", response_model=SnapshotResponse, status_code=201)
async def create_manual_snapshot(
    body: SnapshotRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create an on-demand (manual) snapshot of the specified machine's save directory."""
    from backend.services.backup_manager import create_snapshot

    machine = body.machine
    try:
        conn_kwargs = await _get_conn_kwargs(session, machine)
        save_dir = await _get_setting(session, f"{machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(502, f"Config error: {e}")

    if not save_dir:
        raise HTTPException(422, f"{machine.upper()} save path not configured")

    try:
        snapshot = await create_snapshot(
            session=session,
            machine=machine,
            conn_kwargs=conn_kwargs,
            save_dir=save_dir,
            label="manual",
        )
    except SSHConnectionError as e:
        raise HTTPException(502, f"SSH error: {e}")
    except Exception as e:
        raise HTTPException(500, f"Snapshot failed: {e}")

    return SnapshotResponse(
        id=snapshot.id,
        source_machine=snapshot.source_machine,
        snapshot_path=snapshot.snapshot_path,
        file_count=snapshot.file_count,
        characters=snapshot.characters,
        created_at=snapshot.created_at.isoformat(),
        sync_operation_id=snapshot.sync_operation_id,
        label=snapshot.label,
    )

from __future__ import annotations

"""
History router.

Endpoints:
  GET /api/history?page=1&page_size=20  - Paginated audit log of sync operations
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database import get_session
from backend.models import SyncOperation, SyncFileRecord

router = APIRouter(tags=["history"])


class FileRecordResponse(BaseModel):
    id: int
    filename: str
    source_machine: str
    dest_machine: str
    bytes_transferred: int
    success: bool
    error_message: Optional[str]
    char_snapshot: Optional[dict]
    synced_at: datetime


class SyncOperationResponse(BaseModel):
    id: int
    direction: str
    status: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    file_count: int
    files: list[FileRecordResponse]


class HistoryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SyncOperationResponse]


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    # Total count
    count_result = await session.execute(select(func.count()).select_from(SyncOperation))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    ops_result = await session.execute(
        select(SyncOperation)
        .order_by(SyncOperation.started_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    operations = ops_result.scalars().all()

    items = []
    for op in operations:
        files_result = await session.execute(
            select(SyncFileRecord)
            .where(SyncFileRecord.sync_operation_id == op.id)
            .order_by(SyncFileRecord.synced_at)
        )
        files = files_result.scalars().all()

        items.append(
            SyncOperationResponse(
                id=op.id,
                direction=op.direction,
                status=op.status,
                error_message=op.error_message,
                started_at=op.started_at,
                completed_at=op.completed_at,
                file_count=op.file_count,
                files=[
                    FileRecordResponse(
                        id=f.id,
                        filename=f.filename,
                        source_machine=f.source_machine,
                        dest_machine=f.dest_machine,
                        bytes_transferred=f.bytes_transferred or 0,
                        success=f.success,
                        error_message=f.error_message,
                        char_snapshot=f.char_snapshot,
                        synced_at=f.synced_at,
                    )
                    for f in files
                ],
            )
        )

    return HistoryResponse(total=total, page=page, page_size=page_size, items=items)

from __future__ import annotations

"""
Notifications router.

Stores notification config in the DB KV store and exposes endpoints
for getting, updating, and testing notification settings.

Endpoints:
  GET  /api/notifications/config  - Return current notification config
  PUT  /api/notifications/config  - Update notification config
  POST /api/notifications/test    - Send a test notification
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.routers.settings import _get_setting, _set_setting
from backend.services.notify import notify_conflict

log = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])


# ─── Schema ───────────────────────────────────────────────────────────────────

class NotificationConfig(BaseModel):
    # Profile name from ~/.aws/credentials — not a secret, stored plaintext
    type: Literal["none", "ses"] = "none"
    aws_profile: str = ""
    aws_region: str = "us-east-1"
    ses_from: str = ""
    ses_to: str = ""


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _load_config(session: AsyncSession) -> NotificationConfig:
    return NotificationConfig(
        type=await _get_setting(session, "notification_type") or "none",  # type: ignore[arg-type]
        aws_profile=await _get_setting(session, "notification_aws_profile") or "",
        aws_region=await _get_setting(session, "notification_aws_region") or "us-east-1",
        ses_from=await _get_setting(session, "notification_ses_from") or "",
        ses_to=await _get_setting(session, "notification_ses_to") or "",
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/notifications/config", response_model=NotificationConfig)
async def get_notification_config(session: AsyncSession = Depends(get_session)):
    return await _load_config(session)


@router.put("/notifications/config", response_model=NotificationConfig)
async def update_notification_config(
    body: NotificationConfig,
    session: AsyncSession = Depends(get_session),
):
    await _set_setting(session, "notification_type", body.type)
    await _set_setting(session, "notification_aws_profile", body.aws_profile)
    await _set_setting(session, "notification_aws_region", body.aws_region)
    await _set_setting(session, "notification_ses_from", body.ses_from)
    await _set_setting(session, "notification_ses_to", body.ses_to)
    await session.commit()
    return await _load_config(session)


class TestNotificationResponse(BaseModel):
    success: bool
    message: str


@router.post("/notifications/test", response_model=TestNotificationResponse)
async def test_notification(session: AsyncSession = Depends(get_session)):
    config = await _load_config(session)
    if config.type == "none":
        return TestNotificationResponse(
            success=False, message="No notification type configured"
        )
    try:
        await notify_conflict(test=True)
        return TestNotificationResponse(
            success=True, message=f"Test email sent to {config.ses_to}"
        )
    except Exception as exc:
        return TestNotificationResponse(success=False, message=str(exc))

from __future__ import annotations

"""
Notification service.

Reads config from the DB at call time and dispatches notifications.
Currently supports Amazon SES. Additional providers can be added by
forking and extending `notify_conflict`.

The send functions are synchronous (blocking) and must be called via
asyncio.to_thread. The public entry point `notify_conflict` is async
and handles that itself.
"""

import asyncio
import logging

import boto3

from backend.database import AsyncSessionLocal
from backend.routers.settings import _get_setting

log = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

async def _get_config() -> dict:
    """Read notification config from the DB KV store."""
    async with AsyncSessionLocal() as session:
        return {
            "type": await _get_setting(session, "notification_type") or "none",
            "aws_profile": await _get_setting(session, "notification_aws_profile") or "",
            "aws_region": await _get_setting(session, "notification_aws_region") or "us-east-1",
            "ses_from": await _get_setting(session, "notification_ses_from") or "",
            "ses_to": await _get_setting(session, "notification_ses_to") or "",
        }


# ─── Providers ────────────────────────────────────────────────────────────────

def _send_ses_email(config: dict, subject: str, body: str) -> None:
    """Send an email via AWS SES. Blocking — call via asyncio.to_thread. Raises on failure."""
    if not config["ses_from"] or not config["ses_to"]:
        raise ValueError("SES_FROM and SES_TO must both be set")

    session = boto3.Session(
        profile_name=config["aws_profile"] or None,
        region_name=config["aws_region"],
    )
    client = session.client("ses")
    client.send_email(
        Source=config["ses_from"],
        Destination={"ToAddresses": [config["ses_to"]]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
    log.info("notify: email sent via SES to %s", config["ses_to"])


# ─── Public entry point ────────────────────────────────────────────────────────

async def notify_conflict(test: bool = False) -> None:
    """
    Read notification config from DB and send a conflict (or test) notification.

    Pass test=True to send a test message — the exception is re-raised so the
    caller can surface the error to the UI. In normal conflict detection the
    exception is swallowed so a broken notification never crashes the watcher.
    """
    config = await _get_config()

    if config["type"] == "none":
        log.debug("notify: type=none, skipping")
        return

    if test:
        subject = "Enigma Engine: Test Notification"
        body = (
            "This is a test notification from Enigma Engine.\n\n"
            "Your notification settings are working correctly."
        )
    else:
        subject = "Enigma Engine: Auto-Sync Conflict Detected"
        body = (
            "A save file conflict has been detected.\n\n"
            "Both your PC and Steam Deck have new saves since the last sync. "
            "Open the Enigma Engine dashboard to choose which direction to sync.\n\n"
            "http://enigma-engine.local:8080"
        )

    try:
        if config["type"] == "ses":
            await asyncio.to_thread(_send_ses_email, config, subject, body)
    except Exception as exc:
        log.warning("notify: send failed: %s", exc)
        if test:
            raise

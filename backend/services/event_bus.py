"""Lightweight in-process event bus for SSE push notifications.

Events are broadcast to all connected SSE subscribers.  Fire-and-forget:
if a subscriber's queue is full, the event is silently dropped for that client.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

_subscribers: list[asyncio.Queue[dict]] = []


def emit(event_type: str, **data: Any) -> None:
    """Broadcast an event to all connected SSE clients."""
    payload: dict = {"type": event_type, **data}
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # slow client — skip this event


def subscribe() -> asyncio.Queue[dict]:
    """Register a new SSE subscriber and return its queue."""
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=20)
    _subscribers.append(q)
    log.debug("event_bus: subscriber added (%d total)", len(_subscribers))
    return q


def unsubscribe(q: asyncio.Queue[dict]) -> None:
    """Remove a subscriber queue (called when SSE connection closes)."""
    try:
        _subscribers.remove(q)
        log.debug("event_bus: subscriber removed (%d total)", len(_subscribers))
    except ValueError:
        pass

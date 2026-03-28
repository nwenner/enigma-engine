"""SSE endpoint — real-time push events to the frontend."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)
router = APIRouter()

_KEEPALIVE_INTERVAL = 25.0  # seconds between keepalive comments


@router.get("/events/stream")
async def event_stream():
    """
    Server-Sent Events stream.  The browser connects once and receives push
    notifications whenever syncs complete, conflicts arise, etc.

    Keepalive comments are sent every 25 s to prevent proxies from closing
    idle connections.  The client should reconnect automatically on error.
    """
    from backend.services.event_bus import subscribe, unsubscribe

    q = subscribe()

    async def generator():
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

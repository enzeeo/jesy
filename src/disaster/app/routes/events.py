"""/events SSE stream — frontend subscribes here for live updates."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from disaster.app.deps import AppState

router = APIRouter(tags=["events"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.get("/events")
async def events_stream(request: Request) -> EventSourceResponse:
    state = _state(request)

    async def generator():
        # First event tells the client what sequence to expect (resume hint).
        yield {"event": "ready", "data": json.dumps({"subscriber_count": state.events.subscriber_count + 1})}
        async for event in state.events.subscribe():
            if await request.is_disconnected():
                break
            yield {
                "event": event.get("type", "message"),
                "data": json.dumps(event.get("data", {})),
                "id": str(event.get("sequence_id", "")),
            }

    return EventSourceResponse(generator())

"""GET /snowflake/tile/<name> — return tile data (real or in-memory fallback)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from disaster.snowflake.live_ops import latest_ops_cards
from disaster.snowflake.tiles import TILE_QUERIES, run_tile

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/snowflake", tags=["snowflake"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.get("/tile/{tile_name}")
async def get_tile(tile_name: str, request: Request) -> dict[str, Any]:
    if tile_name not in TILE_QUERIES:
        raise HTTPException(status_code=404, detail="unknown tile")
    state = _state(request)
    runner = getattr(state, "_sf_query_runner", None)
    incidents = await state.incidents.list()
    return await run_tile(tile_name, runner=runner, fallback_incidents=incidents)


@router.get("/tiles")
async def list_tiles() -> dict[str, list[str]]:
    return {"tiles": list(TILE_QUERIES.keys())}


@router.get("/ops")
async def get_ops(request: Request) -> dict[str, Any]:
    state = _state(request)
    runner = getattr(state, "_sf_query_runner", None)
    incidents = await state.incidents.list()
    responders = await state.responders.list()
    return await latest_ops_cards(
        runner=runner,
        fallback_incidents=incidents,
        fallback_responders=responders,
    )

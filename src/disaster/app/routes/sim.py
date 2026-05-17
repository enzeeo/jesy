"""
POST /sim/start  — kick off DisasterSimulator
POST /sim/stop   — cancel
GET  /sim/status — running, counts
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from disaster.road_access import demo_road_access_with_simulated_blocks
from disaster.routing.weighted import summarize_road_access
from disaster.simulator import DisasterSimulator
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sim", tags=["sim"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


def _get_or_create_sim(state) -> DisasterSimulator:
    sim = getattr(state, "_sim", None)
    if sim is None:
        async def on_incident(incident, external_id):
            # Triage in-process (no LLM, simulated incidents are pre-classified
            # but still get the scorer applied for consistency).
            try:
                triage = score(incident, current_time=datetime.now(UTC))
                scored = incident.with_triage(triage)
            except Exception:  # noqa: BLE001
                scored = incident
            persisted = await state.incidents.insert(scored, external_id=external_id)
            if state.snowflake is not None:
                state.snowflake.write("incidents", persisted.model_dump(mode="json"))
            await state.events.publish({
                "type": "incident_created",
                "data": persisted.model_dump(mode="json"),
                "sequence_id": state.events.next_sequence_id(),
            })
        sim = DisasterSimulator(on_incident=on_incident)
        state._sim = sim
    return sim


class StartPayload(BaseModel):
    count: int = Field(default=200, ge=1, le=2000)
    run_id: str = Field(default="texas-gulf-flood", min_length=1, max_length=64)
    seed: int = 42
    demo_window_s: float = Field(default=60.0, gt=0.0)
    road_block_updates: int = Field(default=4, ge=0, le=20)


@router.post("/start")
async def start_sim(payload: StartPayload, request: Request) -> dict[str, Any]:
    state = _state(request)
    sim = _get_or_create_sim(state)
    if sim.running:
        return {"status": "already_running", **sim.snapshot()}
    await _cancel_road_block_updates(state)
    road_access = await state.road_access.set(demo_road_access_with_simulated_blocks(0))
    await _publish_road_access_updated(state, road_access)
    await sim.start(
        count=payload.count,
        run_id=payload.run_id,
        seed=payload.seed,
        demo_window_s=payload.demo_window_s,
    )
    await state.events.publish({
        "type": "sim_started",
        "data": {"run_id": payload.run_id, "count": payload.count, "window_s": payload.demo_window_s},
        "sequence_id": state.events.next_sequence_id(),
    })
    _start_road_block_updates(
        state,
        update_count=payload.road_block_updates,
        demo_window_s=payload.demo_window_s,
    )
    return {"status": "started", **sim.snapshot()}


@router.post("/stop")
async def stop_sim(request: Request) -> dict[str, Any]:
    state = _state(request)
    sim = _get_or_create_sim(state)
    await sim.stop()
    await _cancel_road_block_updates(state)
    return {"status": "stopped", **sim.snapshot()}


@router.get("/status")
async def sim_status(request: Request) -> dict[str, Any]:
    state = _state(request)
    sim = _get_or_create_sim(state)
    return sim.snapshot()


async def _publish_road_access_updated(state: AppState, road_access: dict[str, Any]) -> None:
    await state.events.publish({
        "type": "road_access_updated",
        "data": summarize_road_access(road_access),
        "sequence_id": state.events.next_sequence_id(),
    })


def _start_road_block_updates(
    state: AppState,
    *,
    update_count: int,
    demo_window_s: float,
) -> None:
    if update_count <= 0:
        return
    interval_s = max(0.05, demo_window_s / (update_count + 1))
    state._road_block_task = asyncio.create_task(
        _run_road_block_updates(state, update_count=update_count, interval_s=interval_s),
        name="road-block-sim",
    )


async def _run_road_block_updates(
    state: AppState,
    *,
    update_count: int,
    interval_s: float,
) -> None:
    for block_count in range(1, update_count + 1):
        await asyncio.sleep(interval_s)
        road_access = await state.road_access.set(demo_road_access_with_simulated_blocks(block_count))
        await _publish_road_access_updated(state, road_access)


async def _cancel_road_block_updates(state: AppState) -> None:
    task = getattr(state, "_road_block_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    state._road_block_task = None

"""
POST /sim/start  — kick off DisasterSimulator
POST /sim/stop   — cancel
GET  /sim/status — running, counts
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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
    run_id: str = Field(default="hilo-1960", min_length=1, max_length=64)
    seed: int = 42
    demo_window_s: float = Field(default=60.0, gt=0.0)


@router.post("/start")
async def start_sim(payload: StartPayload, request: Request) -> dict[str, Any]:
    state = _state(request)
    if state.active_sim_run_id is not None and state.active_sim_run_id != payload.run_id:
        raise HTTPException(
            status_code=409,
            detail=f"another sim run is active: {state.active_sim_run_id}",
        )
    sim = _get_or_create_sim(state)
    if sim.running:
        return {"status": "already_running", **sim.snapshot()}
    await sim.start(
        count=payload.count,
        run_id=payload.run_id,
        seed=payload.seed,
        demo_window_s=payload.demo_window_s,
    )
    # Make this the active run so /incidents, /intake/voice, /demo/trigger-call
    # all stamp incident.sim_run_id with it. The AAR scopes by this id.
    state.active_sim_run_id = payload.run_id
    await state.events.publish({
        "type": "sim_started",
        "data": {"run_id": payload.run_id, "count": payload.count, "window_s": payload.demo_window_s},
        "sequence_id": state.events.next_sequence_id(),
    })
    return {"status": "started", **sim.snapshot()}


@router.post("/stop")
async def stop_sim(request: Request) -> dict[str, Any]:
    state = _state(request)
    sim = _get_or_create_sim(state)
    await sim.stop()
    state.active_sim_run_id = None
    return {"status": "stopped", **sim.snapshot()}


@router.get("/status")
async def sim_status(request: Request) -> dict[str, Any]:
    state = _state(request)
    sim = _get_or_create_sim(state)
    return sim.snapshot()

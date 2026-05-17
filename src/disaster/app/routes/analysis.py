"""
GET /api/analysis/{sim_run_id} — full AAR JSON
GET /api/analysis/{sim_run_id}/narrative — LLM-generated narrative + lessons (separate endpoint
   so the main payload doesn't block on the OpenAI call)
GET /api/analysis/runs — list discoverable sim_run_ids (most recent first)
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from disaster.analysis.aar import AARNotFound, get_or_compute_aar
from disaster.analysis.models import AARResponse, NarrativeResponse
from disaster.analysis.narrative import generate_narrative

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.get("/runs")
async def list_runs(request: Request) -> dict[str, list[dict]]:
    """
    Enumerate distinct sim_run_ids known to the system, most recent first. The
    AAR page links here so the user can pick which run to inspect.
    """
    state = _state(request)
    incidents = await state.incidents.list()
    # Preserve insertion order of first-seen incident per sim_run_id
    runs: OrderedDict[str, dict] = OrderedDict()
    for inc in sorted(incidents, key=lambda i: i.timestamp):
        if inc.sim_run_id is None:
            continue
        entry = runs.setdefault(inc.sim_run_id, {
            "sim_run_id": inc.sim_run_id,
            "started_at": inc.timestamp.isoformat(),
            "ended_at": inc.timestamp.isoformat(),
            "incident_count": 0,
            "is_active": inc.sim_run_id == state.active_sim_run_id,
        })
        entry["incident_count"] += 1
        entry["ended_at"] = inc.timestamp.isoformat()
    # Most recent first
    return {"runs": sorted(runs.values(), key=lambda r: r["ended_at"], reverse=True)}


@router.get("/{sim_run_id}", response_model=AARResponse)
async def get_aar(sim_run_id: str, request: Request) -> AARResponse:
    state = _state(request)
    try:
        return await get_or_compute_aar(sim_run_id, state)
    except AARNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{sim_run_id}/narrative", response_model=NarrativeResponse)
async def get_narrative(sim_run_id: str, request: Request) -> NarrativeResponse:
    """
    Async LLM call. 3s timeout — falls back to static prose if OpenAI is slow
    or unavailable. Always returns 200; check `source` to see if it's real.
    """
    state = _state(request)
    try:
        aar = await get_or_compute_aar(sim_run_id, state)
    except AARNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if aar.is_live:
        # Don't waste an LLM call narrating an in-progress run.
        return NarrativeResponse(
            narrative="Run in progress. Narrative will be available once the run completes.",
            lessons=[],
            source="fallback",
        )
    return await generate_narrative(aar, state.llm_client)

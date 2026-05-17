"""POST /routing/optimize — given current state, computes responder assignment."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

from disaster.models import IncidentStatus
from disaster.routing import optimize

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/optimize")
async def optimize_routes(request: Request, prefer_vrp: bool = False) -> dict[str, Any]:
    """
    Recompute dispatch. Defaults to greedy (demo path); pass ?prefer_vrp=true
    to try OR-Tools first.

    Side effect: writes one responder_dispatches row per RouteLeg so the
    post-disaster AAR has a real baseline for its counterfactual A/B.
    """
    state = _state(request)
    incidents = [
        i for i in await state.incidents.list()
        if i.status in {IncidentStatus.NEW, IncidentStatus.DISPATCHED}
    ]
    responders = await state.responders.list()
    assignment = optimize(incidents, responders, prefer_vrp=prefer_vrp)

    # Persist the dispatch decisions so the AAR can read "what actually happened"
    # rather than re-deriving via replay. sim_run_id scopes the AAR per-run.
    dispatched_at = datetime.now(UTC).isoformat()
    if state.snowflake is not None:
        for responder_id, legs in assignment.routes.items():
            for leg in legs:
                state.snowflake.write("responder_dispatches", {
                    "responder_id": str(responder_id),
                    "incident_id": str(leg.incident_id),
                    "dispatched_at": dispatched_at,
                    "distance_km": leg.distance_km,
                    "eta_seconds": leg.eta_seconds,
                    "solver": assignment.solver,
                    "sim_run_id": state.active_sim_run_id,
                })

    payload = {
        "solver": assignment.solver,
        "elapsed_ms": assignment.elapsed_ms,
        "unassigned": [str(uid) for uid in assignment.unassigned],
        "routes": {
            str(rid): [
                {
                    "incident_id": str(leg.incident_id),
                    "from_location": leg.from_location.model_dump(),
                    "to_location": leg.to_location.model_dump(),
                    "distance_km": leg.distance_km,
                    "eta_seconds": leg.eta_seconds,
                }
                for leg in legs
            ]
            for rid, legs in assignment.routes.items()
        },
    }

    await state.events.publish({
        "type": "route_recomputed",
        "data": {
            "solver": assignment.solver,
            "responder_count": len(assignment.routes),
            "assigned_count": sum(len(legs) for legs in assignment.routes.values()),
            "unassigned_count": len(assignment.unassigned),
        },
        "sequence_id": state.events.next_sequence_id(),
    })
    return payload

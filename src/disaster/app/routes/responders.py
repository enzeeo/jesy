"""Responder tracking endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from disaster.models import IncidentStatus, Location, ResponderStatus
from disaster.movement import record_responder_location, serialize_active_dispatch

if TYPE_CHECKING:
    from disaster.app.deps import AppState

router = APIRouter(prefix="/responders", tags=["responders"])


class ResponderLocationPing(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float = Field(ge=0.0, le=5000.0)
    timestamp: datetime
    speed_mps: float | None = Field(default=None, ge=0.0)
    heading: float | None = Field(default=None, ge=0.0, le=360.0)


class CompleteAssignmentRequest(BaseModel):
    completed_by: str = Field(min_length=1, max_length=120)


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.get("/assignments")
async def list_responder_assignments(request: Request) -> list[dict[str, Any]]:
    """Return all active human-started dispatches for frontend hydration."""

    state = _state(request)
    assignments: list[dict[str, Any]] = []
    for dispatch in await state.active_dispatches.list():
        assignment = await serialize_active_dispatch(state, dispatch)
        if assignment is not None:
            assignments.append(assignment)
    return assignments


@router.post("/{responder_id}/location")
async def update_responder_location(
    responder_id: UUID,
    ping: ResponderLocationPing,
    request: Request,
) -> dict[str, Any]:
    """Accept phone-like responder location pings and detect caller arrival."""

    state = _state(request)
    responder = await state.responders.get(responder_id)
    if responder is None:
        raise HTTPException(status_code=404, detail=f"responder {responder_id} not found")

    location = Location(lat=ping.lat, lng=ping.lng, description="phone ping")
    return await record_responder_location(
        state,
        responder_id=responder_id,
        location=location,
        timestamp=ping.timestamp,
        "accuracy_m": ping.accuracy_m,
        speed_mps=ping.speed_mps,
        heading=ping.heading,
    )


@router.post("/{responder_id}/assignment/complete")
async def complete_responder_assignment(
    responder_id: UUID,
    payload: CompleteAssignmentRequest,
    request: Request,
) -> dict[str, Any]:
    """Mark an on-scene responder's active assignment complete and release the unit."""

    state = _state(request)
    responder = await state.responders.get(responder_id)
    if responder is None:
        raise HTTPException(status_code=404, detail=f"responder {responder_id} not found")

    active_dispatch = await state.active_dispatches.get_for_responder(responder_id)
    if active_dispatch is None:
        raise HTTPException(status_code=404, detail="active assignment not found")

    incident = await state.incidents.get(active_dispatch.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {active_dispatch.incident_id} not found")

    completed_dispatch = await state.active_dispatches.complete_for_responder(responder_id)
    if completed_dispatch is None:
        raise HTTPException(status_code=404, detail="active assignment not found")
    movement = getattr(state, "dispatch_movement", None)
    if movement is not None:
        await movement.cancel(responder_id)

    released_responder = await state.responders.set_status(
        responder_id,
        ResponderStatus.IDLE,
        assigned_incident_id=None,
    )
    resolved_incident = await state.incidents.update(
        incident.model_copy(update={"status": IncidentStatus.RESOLVED})
    )
    event_data = {
        "assignment_id": completed_dispatch.dispatch_id,
        "route_id": completed_dispatch.route_id,
        "leg_id": completed_dispatch.leg_id,
        "responder_id": str(completed_dispatch.responder_id),
        "incident_id": str(completed_dispatch.incident_id),
        "status": released_responder.status.value,
        "completed_by": payload.completed_by,
        "responder": released_responder.model_dump(mode="json"),
        "incident": resolved_incident.model_dump(mode="json"),
    }
    await state.events.publish({
        "type": "dispatch_completed",
        "data": event_data,
        "sequence_id": state.events.next_sequence_id(),
    })
    return event_data


@router.get("/{responder_id}/assignment")
async def get_responder_assignment(
    responder_id: UUID,
    request: Request,
) -> dict[str, Any] | None:
    """Return the active human-started dispatch for a responder, if any."""

    state = _state(request)
    responder = await state.responders.get(responder_id)
    if responder is None:
        raise HTTPException(status_code=404, detail=f"responder {responder_id} not found")

    active_dispatch = await state.active_dispatches.get_for_responder(responder_id)
    if active_dispatch is None:
        return None

    incident = await state.incidents.get(active_dispatch.incident_id)
    return {
        "assignment_id": active_dispatch.dispatch_id,
        "route_id": active_dispatch.route_id,
        "leg_id": active_dispatch.leg_id,
        "responder_id": str(active_dispatch.responder_id),
        "incident_id": str(active_dispatch.incident_id),
        "status": responder.status.value,
        "eta_seconds": active_dispatch.leg.get("eta_seconds"),
        "distance_km": active_dispatch.leg.get("distance_km"),
        "route_leg": active_dispatch.leg,
        "leg": active_dispatch.leg,
        "incident": incident.model_dump(mode="json") if incident is not None else None,
    }

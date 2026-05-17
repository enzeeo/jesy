"""Responder tracking endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from disaster.models import IncidentStatus, Location, ResponderStatus
from disaster.routing.greedy import _haversine_km

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


def _state(req: Request) -> AppState:
    return req.app.state.disaster


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
    updated_responder = responder.model_copy(update={"location": location})
    await state.responders.upsert(updated_responder)

    await state.events.publish({
        "type": "responder_location_updated",
        "data": {
            "responder_id": str(responder_id),
            "responder": updated_responder.model_dump(mode="json"),
            "callsign": updated_responder.callsign,
            "status": updated_responder.status.value,
            "location": location.model_dump(),
            "accuracy_m": ping.accuracy_m,
            "timestamp": ping.timestamp.isoformat(),
            "speed_mps": ping.speed_mps,
            "heading": ping.heading,
        },
        "sequence_id": state.events.next_sequence_id(),
    })

    incident_id = updated_responder.assigned_incident_id
    if incident_id is None:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": None,
        }

    incident = await state.incidents.get(incident_id)
    if incident is None:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": str(incident_id),
            "warning": "assigned incident not found",
        }

    distance_m = _haversine_km(
        (location.lat, location.lng),
        (incident.location.lat, incident.location.lng),
    ) * 1000.0
    detection = state.responder_tracking.record_ping(
        responder_id=responder_id,
        incident_id=incident.id,
        timestamp=ping.timestamp,
        distance_m=distance_m,
    )

    if not detection.arrival_detected:
        return {
            "responder_id": str(responder_id),
            "arrival_detected": False,
            "incident_id": str(incident.id),
            "distance_m": detection.distance_m,
        }

    on_scene_responder = updated_responder.model_copy(update={"status": ResponderStatus.ON_SCENE})
    await state.responders.upsert(on_scene_responder)
    on_scene_incident = incident.model_copy(update={"status": IncidentStatus.ON_SCENE})
    await state.incidents.update(on_scene_incident)
    active_dispatch = await state.active_dispatches.get_for_responder(responder_id)

    snowflake_row = {
        "responder_id": str(on_scene_responder.id),
        "callsign": on_scene_responder.callsign,
        "incident_id": str(incident.id),
        "cluster_id": None,
        "arrival_timestamp": ping.timestamp.isoformat(),
        "ping_lat": ping.lat,
        "ping_lng": ping.lng,
        "accuracy_m": ping.accuracy_m,
        "route_id": active_dispatch.route_id if active_dispatch is not None else None,
        "assignment_id": active_dispatch.dispatch_id if active_dispatch is not None else str(incident.id),
        "detection_method": detection.detection_method,
        "distance_m": detection.distance_m,
    }
    if state.snowflake is not None:
        state.snowflake.write("responder_arrivals", snowflake_row)

    await state.events.publish({
        "type": "responder_arrived",
        "data": {
            "responder_id": str(responder_id),
            "responder": on_scene_responder.model_dump(mode="json"),
            "callsign": on_scene_responder.callsign,
            "incident_id": str(incident.id),
            "arrival_timestamp": ping.timestamp.isoformat(),
            "location": location.model_dump(),
            "distance_m": detection.distance_m,
            "accuracy_m": ping.accuracy_m,
            "detection_method": detection.detection_method,
        },
        "sequence_id": state.events.next_sequence_id(),
    })

    return {
        "responder_id": str(responder_id),
        "arrival_detected": True,
        "incident_id": str(incident.id),
        "distance_m": detection.distance_m,
        "detection_method": detection.detection_method,
    }


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

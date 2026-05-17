"""POST /routing/optimize — computes responder route assignments."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from disaster.models import (
    IncidentReport,
    IncidentStatus,
    Location,
    ResponderStatus,
    ResponderUnit,
)
from disaster.routing import DispatchTarget, optimize, optimize_weighted_flow
from disaster.store import (
    ActiveDispatch,
    DispatchConflictError,
    RouteRecommendation,
    RouteRecommendationLeg,
)

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])

DEMO_ROAD_ACCESS: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "Harbor flood closure",
                "confidence": 0.92,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-94.7899, 29.3097],
                    [-94.7873, 29.3097],
                    [-94.7873, 29.3123],
                    [-94.7899, 29.3123],
                    [-94.7899, 29.3097],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "road_status": "confirmed_closed",
                "label": "Seawall washout",
                "confidence": 0.88,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-94.8057, 29.2796],
                    [-94.8012, 29.2796],
                    [-94.8012, 29.2824],
                    [-94.8057, 29.2824],
                    [-94.8057, 29.2796],
                ]],
            },
        },
    ],
}


class DispatchCluster(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    location: Location
    priority_score: float = Field(ge=0.0, le=1.0)
    demand_count: int = Field(default=1, ge=1)
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    preferred_capabilities: list[str] = Field(default_factory=list, max_length=20)
    member_incident_ids: list[str] = Field(default_factory=list, max_length=200)

    def to_target(self) -> DispatchTarget:
        return DispatchTarget(
            id=self.id,
            target_type="cluster",
            location=self.location,
            priority_score=self.priority_score,
            demand_count=self.demand_count,
            required_capabilities=tuple(self.required_capabilities),
            preferred_capabilities=tuple(self.preferred_capabilities),
            member_incident_ids=tuple(self.member_incident_ids),
        )


class RoutingOptimizeRequest(BaseModel):
    responders: list[ResponderUnit] | None = None
    incidents: list[IncidentReport] | None = None
    clusters: list[DispatchCluster] = Field(default_factory=list)
    road_access: dict[str, Any] | None = None
    accepted_assignments: dict[UUID, str] = Field(default_factory=dict)
    route_stop_limit: int = Field(default=5, ge=1, le=20)
    max_candidates: int | None = Field(default=None, ge=1, le=500)


class StartDispatchRequest(BaseModel):
    route_id: str = Field(min_length=1, max_length=120)
    leg_id: str = Field(min_length=1, max_length=240)
    started_by: str = Field(min_length=1, max_length=120)


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/optimize")
async def optimize_routes(
    request: Request,
    payload: Annotated[RoutingOptimizeRequest | None, Body()] = None,
    prefer_vrp: bool = False,
) -> dict[str, Any]:
    """
    Recompute dispatch. Defaults to weighted flow-time; pass ?prefer_vrp=true
    without a stub body to exercise the legacy OR-Tools/greedy path.
    """
    state = _state(request)
    if payload is None:
        incidents = [
            incident for incident in await state.incidents.list()
            if incident.status in {IncidentStatus.NEW, IncidentStatus.DISPATCHED}
        ]
        responders = await state.responders.list()
        if prefer_vrp:
            assignment = optimize(incidents, responders, prefer_vrp=True)
        else:
            targets = [DispatchTarget.from_incident(incident) for incident in incidents]
            assignment = optimize_weighted_flow(targets, responders, road_access=DEMO_ROAD_ACCESS)
    else:
        responders = payload.responders
        if responders is None:
            responders = await state.responders.list()
        targets = []
        if payload.incidents is not None:
            targets.extend(DispatchTarget.from_incident(incident) for incident in payload.incidents)
        targets.extend(cluster.to_target() for cluster in payload.clusters)
        if payload.incidents is None and not payload.clusters:
            incidents = [
                incident for incident in await state.incidents.list()
                if incident.status in {IncidentStatus.NEW, IncidentStatus.DISPATCHED}
            ]
            targets.extend(DispatchTarget.from_incident(incident) for incident in incidents)
        assignment = optimize_weighted_flow(
            targets,
            responders,
            road_access=payload.road_access,
            route_stop_limit=payload.route_stop_limit,
            max_candidates=payload.max_candidates,
            accepted_assignments=payload.accepted_assignments,
        )

    route_id = str(uuid4())
    response_payload = _serialize_assignment(assignment, route_id=route_id)
    await state.route_recommendations.save(
        _build_recommendation(route_id=route_id, solver=assignment.solver, payload=response_payload)
    )

    await state.events.publish({
        "type": "route_recomputed",
        "data": {
            "route_id": route_id,
            "solver": assignment.solver,
            "responder_count": len(assignment.routes),
            "assigned_count": sum(len(legs) for legs in assignment.routes.values()),
            "unassigned_count": len(assignment.unassigned),
            "degraded_count": sum(
                1
                for legs in assignment.routes.values()
                for leg in legs
                if getattr(leg, "degraded", False)
            ),
        },
        "sequence_id": state.events.next_sequence_id(),
    })
    return response_payload


@router.post("/dispatches/start")
async def start_dispatch(
    request: Request,
    payload: StartDispatchRequest,
) -> dict[str, Any]:
    """Turn a route recommendation leg into a human-started dispatch."""

    state = _state(request)
    recommendation_leg = await state.route_recommendations.get_leg(payload.route_id, payload.leg_id)
    if recommendation_leg is None:
        raise HTTPException(status_code=404, detail="route recommendation leg not found")
    if recommendation_leg.incident_id is None:
        raise HTTPException(status_code=409, detail="dispatch start requires an incident-backed leg")

    responder = await state.responders.get(recommendation_leg.responder_id)
    if responder is None:
        raise HTTPException(status_code=404, detail=f"responder {recommendation_leg.responder_id} not found")
    incident = await state.incidents.get(recommendation_leg.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {recommendation_leg.incident_id} not found")

    new_dispatch = ActiveDispatch(
        dispatch_id=str(uuid4()),
        route_id=payload.route_id,
        leg_id=payload.leg_id,
        responder_id=recommendation_leg.responder_id,
        incident_id=recommendation_leg.incident_id,
        started_by=payload.started_by,
        started_at=datetime.now(UTC),
        solver=recommendation_leg.solver,
        leg=recommendation_leg.leg,
    )
    try:
        dispatch, created = await state.active_dispatches.start(new_dispatch)
    except DispatchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if created:
        responder = await state.responders.set_status(
            responder.id,
            ResponderStatus.EN_ROUTE,
            assigned_incident_id=incident.id,
        )
        incident = await state.incidents.update(
            incident.model_copy(update={"status": IncidentStatus.EN_ROUTE})
        )

        if state.snowflake is not None:
            state.snowflake.write("responder_dispatches", {
                "responder_id": str(responder.id),
                "incident_id": str(incident.id),
                "dispatched_at": dispatch.started_at.isoformat(),
                "distance_km": dispatch.leg.get("distance_km", 0.0),
                "eta_seconds": dispatch.leg.get("eta_seconds", 0.0),
                "solver": dispatch.solver,
            })

        event_data = _dispatch_response(dispatch, responder, incident)
        await state.events.publish({
            "type": "dispatch_started",
            "data": event_data,
            "sequence_id": state.events.next_sequence_id(),
        })
        return event_data

    current_responder = await state.responders.get(dispatch.responder_id)
    current_incident = await state.incidents.get(dispatch.incident_id)
    if current_responder is None or current_incident is None:
        raise HTTPException(status_code=404, detail="active dispatch references missing state")
    return _dispatch_response(dispatch, current_responder, current_incident)


def _serialize_assignment(assignment: Any, *, route_id: str) -> dict[str, Any]:
    payload = {
        "route_id": route_id,
        "solver": assignment.solver,
        "elapsed_ms": assignment.elapsed_ms,
        "unassigned": [str(target_id) for target_id in assignment.unassigned],
        "routes": {
            str(rid): [
                _serialize_leg(leg, route_id=route_id, responder_id=str(rid), leg_index=leg_index)
                for leg_index, leg in enumerate(legs)
            ]
            for rid, legs in assignment.routes.items()
        },
    }
    road_access = getattr(assignment, "road_access", None)
    if road_access is not None:
        payload["road_access"] = road_access
    return payload


def _serialize_leg(leg: Any, *, route_id: str, responder_id: str, leg_index: int) -> dict[str, Any]:
    target_id = getattr(leg, "target_id", None)
    target_type = getattr(leg, "target_type", None)
    incident_id = getattr(leg, "incident_id", None)
    if target_id is None and incident_id is not None:
        target_id = str(incident_id)
        target_type = "incident"

    serialized = {
        "leg_id": f"{route_id}:{responder_id}:{leg_index}",
        "responder_id": responder_id,
        "incident_id": str(incident_id) if incident_id else None,
        "target_id": str(target_id) if target_id is not None else None,
        "target_type": target_type,
        "from_location": leg.from_location.model_dump(),
        "to_location": leg.to_location.model_dump(),
        "distance_km": leg.distance_km,
        "eta_seconds": leg.eta_seconds,
    }
    if hasattr(leg, "target_id"):
        serialized.update({
            "member_incident_ids": list(leg.member_incident_ids),
            "arrival_seconds": leg.arrival_seconds,
            "route_geometry": leg.route_geometry,
            "degraded": leg.degraded,
            "provider_status": leg.provider_status,
            "warnings": leg.warnings,
            "assignment_reason": leg.assignment_reason,
        })
    return serialized


def _build_recommendation(*, route_id: str, solver: str, payload: dict[str, Any]) -> RouteRecommendation:
    legs: dict[str, RouteRecommendationLeg] = {}
    for responder_id, route_legs in payload.get("routes", {}).items():
        responder_uuid = _parse_uuid(responder_id)
        if responder_uuid is None:
            continue
        for leg in route_legs:
            leg_id = leg.get("leg_id")
            if not isinstance(leg_id, str):
                continue
            incident_id = _incident_id_from_leg(leg)
            legs[leg_id] = RouteRecommendationLeg(
                route_id=route_id,
                leg_id=leg_id,
                responder_id=responder_uuid,
                incident_id=incident_id,
                target_id=leg.get("target_id"),
                target_type=leg.get("target_type"),
                leg=leg,
                solver=solver,
            )
    return RouteRecommendation(route_id=route_id, solver=solver, payload=payload, legs=legs)


def _incident_id_from_leg(leg: dict[str, Any]) -> UUID | None:
    raw_incident_id = leg.get("incident_id")
    if raw_incident_id is None and leg.get("target_type") == "incident":
        raw_incident_id = leg.get("target_id")
    if not isinstance(raw_incident_id, str) or not raw_incident_id:
        return None
    return _parse_uuid(raw_incident_id)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _dispatch_response(
    dispatch: ActiveDispatch,
    responder: ResponderUnit,
    incident: IncidentReport,
) -> dict[str, Any]:
    assignment = {
        "assignment_id": dispatch.dispatch_id,
        "route_id": dispatch.route_id,
        "leg_id": dispatch.leg_id,
        "responder_id": str(dispatch.responder_id),
        "incident_id": str(dispatch.incident_id),
        "status": responder.status.value,
        "eta_seconds": dispatch.leg.get("eta_seconds"),
        "distance_km": dispatch.leg.get("distance_km"),
        "route_leg": dispatch.leg,
        "leg": dispatch.leg,
        "incident": incident.model_dump(mode="json"),
    }
    return {
        "dispatch_id": dispatch.dispatch_id,
        "assignment_id": dispatch.dispatch_id,
        "route_id": dispatch.route_id,
        "leg_id": dispatch.leg_id,
        "responder_id": str(dispatch.responder_id),
        "incident_id": str(dispatch.incident_id),
        "started_by": dispatch.started_by,
        "started_at": dispatch.started_at.isoformat(),
        "status": responder.status.value,
        "solver": dispatch.solver,
        "eta_seconds": dispatch.leg.get("eta_seconds"),
        "distance_km": dispatch.leg.get("distance_km"),
        "route_leg": dispatch.leg,
        "assignment": assignment,
        "responder": responder.model_dump(mode="json"),
        "incident": incident.model_dump(mode="json"),
    }

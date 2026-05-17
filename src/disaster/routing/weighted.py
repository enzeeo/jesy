"""Weighted flow-time route optimizer for disaster dispatch.

The scoring model follows flood-rescue DVRP research: upstream triage owns the
priority score, while this layer minimizes weighted waiting time across the
currently routable work set.
"""
from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from disaster.models import IncidentReport, Location, ResponderUnit
from disaster.routing.greedy import _AVG_RESPONSE_KPH, _haversine_km

HARD_AVOID_STATUSES = {"confirmed_closed", "likely_flooded"}
SOFT_PENALTY_STATUSES = {"restricted", "uncertain_needs_verification"}
HARD_AVOID_STUB_WARNING = "hard road closures not enforced by stub provider"
SOFT_ROAD_PENALTY_SECONDS = 90.0
HARD_ROAD_DEGRADED_PENALTY_SECONDS = 300.0
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
ORS_TIMEOUT_SECONDS = 2.5
LIVE_ROUTING_ENV = "OPENROUTESERVICE_LIVE_ROUTING"


@dataclass(frozen=True)
class DispatchTarget:
    """A dispatchable incident or upstream incident cluster."""

    id: str
    location: Location
    priority_score: float
    target_type: str = "incident"
    demand_count: int = 1
    required_capabilities: tuple[str, ...] = ()
    preferred_capabilities: tuple[str, ...] = ()
    member_incident_ids: tuple[str, ...] = ()

    @classmethod
    def from_incident(cls, incident: IncidentReport) -> DispatchTarget:
        """Build a dispatch target from the authoritative incident record."""

        return cls(
            id=str(incident.id),
            target_type="incident",
            location=incident.location,
            priority_score=incident.priority_score,
            demand_count=max(1, len(incident.victims)),
            member_incident_ids=(str(incident.id),),
        )


@dataclass
class WeightedRouteLeg:
    """One optimized stop on a responder route."""

    target_id: str
    target_type: str
    from_location: Location
    to_location: Location
    distance_km: float
    eta_seconds: float
    arrival_seconds: float
    route_geometry: dict[str, Any]
    incident_id: str | None = None
    member_incident_ids: tuple[str, ...] = ()
    degraded: bool = False
    provider_status: str = "stub_haversine"
    warnings: list[str] = field(default_factory=list)
    assignment_reason: str = "weighted_flow_min_cost"


@dataclass(frozen=True)
class RouteEstimate:
    """Provider-normalized route estimate."""

    distance_km: float
    eta_seconds: float
    route_geometry: dict[str, Any]
    provider_status: str
    degraded: bool = False
    warnings: tuple[str, ...] = ()


@dataclass
class WeightedAssignment:
    """Per-responder weighted route assignment and provider provenance."""

    routes: dict[UUID, list[WeightedRouteLeg]] = field(default_factory=dict)
    unassigned: list[str] = field(default_factory=list)
    solver: str = "weighted_flow"
    elapsed_ms: float = 0.0
    road_access: dict[str, Any] = field(default_factory=dict)


def optimize_weighted_flow(
    targets: list[DispatchTarget],
    responders: list[ResponderUnit],
    *,
    road_access: Mapping[str, Any] | None = None,
    route_stop_limit: int = 5,
    max_candidates: int | None = None,
    accepted_assignments: Mapping[UUID | str, str] | None = None,
) -> WeightedAssignment:
    """Assign responders by minimizing weighted arrival time.

    This is an insertion-style online heuristic, not an exact VRP solver. It
    freezes accepted/current legs, then repeatedly appends the feasible
    responder-target pair with the lowest marginal weighted flow-time cost.
    """

    started_at = time.monotonic()
    route_stop_limit = max(1, route_stop_limit)
    road_summary = summarize_road_access(road_access)
    routes: dict[UUID, list[WeightedRouteLeg]] = {responder.id: [] for responder in responders}
    current_locations: dict[UUID, Location] = {
        responder.id: responder.location for responder in responders
    }
    current_arrival_seconds: dict[UUID, float] = {responder.id: 0.0 for responder in responders}
    remaining_stops: dict[UUID, int] = {responder.id: route_stop_limit for responder in responders}
    available_targets = {target.id: target for target in targets}

    for responder in responders:
        frozen_target_id = _accepted_target_id(accepted_assignments, responder.id)
        if frozen_target_id is None:
            continue
        target = available_targets.get(frozen_target_id)
        if target is None or not _responder_can_serve(responder, target):
            continue
        leg = _make_leg(
            responder,
            target,
            current_locations[responder.id],
            current_arrival_seconds[responder.id],
            road_summary,
            assignment_reason="accepted_leg_frozen",
            allow_live_provider=True,
        )
        routes[responder.id].append(leg)
        current_locations[responder.id] = target.location
        current_arrival_seconds[responder.id] = leg.arrival_seconds
        remaining_stops[responder.id] -= 1
        available_targets.pop(target.id, None)

    candidate_limit = max_candidates
    if candidate_limit is None:
        candidate_limit = max(1, len(responders) * route_stop_limit * 3)

    while available_targets and any(stops > 0 for stops in remaining_stops.values()):
        candidates = _ranked_candidates(list(available_targets.values()), candidate_limit)
        best_choice: tuple[float, ResponderUnit, DispatchTarget, WeightedRouteLeg] | None = None

        for responder in responders:
            if remaining_stops[responder.id] <= 0:
                continue
            for target in candidates:
                if target.id not in available_targets:
                    continue
                if not _responder_can_serve(responder, target):
                    continue
                leg = _make_leg(
                    responder,
                    target,
                    current_locations[responder.id],
                    current_arrival_seconds[responder.id],
                    road_summary,
                    assignment_reason="weighted_flow_min_cost",
                    allow_live_provider=False,
                )
                score = _weighted_flow_score(target, leg, candidates)
                if best_choice is None or score < best_choice[0]:
                    best_choice = (score, responder, target, leg)

        if best_choice is None:
            break

        _, responder, target, _scored_leg = best_choice
        leg = _make_leg(
            responder,
            target,
            current_locations[responder.id],
            current_arrival_seconds[responder.id],
            road_summary,
            assignment_reason="weighted_flow_min_cost",
            allow_live_provider=True,
        )
        routes[responder.id].append(leg)
        current_locations[responder.id] = target.location
        current_arrival_seconds[responder.id] = leg.arrival_seconds
        remaining_stops[responder.id] -= 1
        available_targets.pop(target.id, None)

    return WeightedAssignment(
        routes=routes,
        unassigned=sorted(available_targets),
        elapsed_ms=(time.monotonic() - started_at) * 1000.0,
        road_access=road_summary,
    )


def summarize_road_access(road_access: Mapping[str, Any] | None) -> dict[str, Any]:
    """Summarize road-access GeoJSON into routing policy counts."""

    features = []
    if road_access and road_access.get("type") == "FeatureCollection":
        raw_features = road_access.get("features", [])
        if isinstance(raw_features, list):
            features = [feature for feature in raw_features if isinstance(feature, dict)]

    status_counts: dict[str, int] = {}
    for feature in features:
        status = _feature_status(feature)
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1

    hard_count = sum(status_counts.get(status, 0) for status in HARD_AVOID_STATUSES)
    soft_count = sum(status_counts.get(status, 0) for status in SOFT_PENALTY_STATUSES)
    summary = {
        "feature_count": len(features),
        "hard_avoid_count": hard_count,
        "soft_penalty_count": soft_count,
        "status_counts": status_counts,
        "provider": "openrouteservice" if _live_routing_enabled() else "stub_haversine",
        "avoidance_strategy": "ors_avoid_polygons_when_enabled_else_stub_warning",
    }
    if road_access and road_access.get("type") == "FeatureCollection":
        summary["feature_collection"] = road_access
    return summary


def _accepted_target_id(
    accepted_assignments: Mapping[UUID | str, str] | None,
    responder_id: UUID,
) -> str | None:
    if not accepted_assignments:
        return None
    return accepted_assignments.get(responder_id) or accepted_assignments.get(str(responder_id))


def _ranked_candidates(targets: list[DispatchTarget], candidate_limit: int) -> list[DispatchTarget]:
    return sorted(
        targets,
        key=lambda target: (-(target.priority_score * target.demand_count), target.id),
    )[:candidate_limit]


def _make_leg(
    responder: ResponderUnit,
    target: DispatchTarget,
    from_location: Location,
    previous_arrival_seconds: float,
    road_summary: Mapping[str, Any],
    *,
    assignment_reason: str,
    allow_live_provider: bool,
) -> WeightedRouteLeg:
    route_estimate = _estimate_route(
        from_location,
        target.location,
        road_summary,
        allow_live_provider=allow_live_provider,
    )

    return WeightedRouteLeg(
        target_id=target.id,
        target_type=target.target_type,
        incident_id=target.id if target.target_type == "incident" else None,
        member_incident_ids=target.member_incident_ids,
        from_location=from_location,
        to_location=target.location,
        distance_km=route_estimate.distance_km,
        eta_seconds=route_estimate.eta_seconds,
        arrival_seconds=previous_arrival_seconds + route_estimate.eta_seconds,
        route_geometry=route_estimate.route_geometry,
        degraded=route_estimate.degraded,
        provider_status=route_estimate.provider_status,
        warnings=list(route_estimate.warnings),
        assignment_reason=assignment_reason,
    )


def _weighted_flow_score(
    target: DispatchTarget,
    leg: WeightedRouteLeg,
    candidate_targets: list[DispatchTarget],
) -> float:
    """Estimate total weighted waiting if this target becomes the next stop."""

    score = _target_weight(target) * leg.arrival_seconds
    for later_target in candidate_targets:
        if later_target.id == target.id:
            continue
        later_distance_km = _haversine_km(
            (target.location.lat, target.location.lng),
            (later_target.location.lat, later_target.location.lng),
        )
        later_eta_seconds = (later_distance_km / _AVG_RESPONSE_KPH) * 3600.0
        score += _target_weight(later_target) * (leg.arrival_seconds + later_eta_seconds)
    return score


def _target_weight(target: DispatchTarget) -> float:
    return max(0.01, target.priority_score) * max(1, target.demand_count)


def _responder_can_serve(responder: ResponderUnit, target: DispatchTarget) -> bool:
    if not target.required_capabilities:
        return True
    responder_tokens = {
        responder.type.value.lower(),
        responder.type.name.lower(),
        *(capability.lower() for capability in responder.capabilities),
    }
    return all(requirement.lower() in responder_tokens for requirement in target.required_capabilities)


def _feature_status(feature: Mapping[str, Any]) -> str | None:
    properties = feature.get("properties", {})
    if not isinstance(properties, Mapping):
        return None
    raw_status = properties.get("road_status") or properties.get("status")
    if raw_status is None:
        return None
    return str(raw_status).strip().lower()


def _estimate_route(
    from_location: Location,
    to_location: Location,
    road_summary: Mapping[str, Any],
    *,
    allow_live_provider: bool,
) -> RouteEstimate:
    api_key = os.environ.get("OPENROUTESERVICE_API_KEY", "")
    if api_key and allow_live_provider and _live_routing_enabled():
        estimate = _estimate_route_with_ors(from_location, to_location, road_summary, api_key)
        if estimate is not None:
            return estimate
    return _estimate_route_with_stub(from_location, to_location, road_summary)


def _live_routing_enabled() -> bool:
    return os.environ.get(LIVE_ROUTING_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _estimate_route_with_stub(
    from_location: Location,
    to_location: Location,
    road_summary: Mapping[str, Any],
    *,
    extra_warning: str | None = None,
) -> RouteEstimate:
    distance_km = _haversine_km(
        (from_location.lat, from_location.lng),
        (to_location.lat, to_location.lng),
    )
    eta_seconds = (distance_km / _AVG_RESPONSE_KPH) * 3600.0
    warnings: list[str] = []
    degraded = False

    hard_count = int(road_summary.get("hard_avoid_count", 0))
    soft_count = int(road_summary.get("soft_penalty_count", 0))
    if hard_count:
        degraded = True
        eta_seconds += HARD_ROAD_DEGRADED_PENALTY_SECONDS * hard_count
        warnings.append(HARD_AVOID_STUB_WARNING)
    if soft_count:
        eta_seconds += SOFT_ROAD_PENALTY_SECONDS * soft_count
        warnings.append("soft road access penalty applied")
    if extra_warning:
        warnings.append(extra_warning)

    return RouteEstimate(
        distance_km=distance_km,
        eta_seconds=eta_seconds,
        route_geometry={
            "type": "LineString",
            "coordinates": [
                [from_location.lng, from_location.lat],
                [to_location.lng, to_location.lat],
            ],
        },
        provider_status="stub_haversine",
        degraded=degraded,
        warnings=tuple(warnings),
    )


def _estimate_route_with_ors(
    from_location: Location,
    to_location: Location,
    road_summary: Mapping[str, Any],
    api_key: str,
) -> RouteEstimate | None:
    try:
        body: dict[str, Any] = {
            "coordinates": [
                [from_location.lng, from_location.lat],
                [to_location.lng, to_location.lat],
            ],
        }
        avoid_polygons = _build_avoid_polygons(road_summary)
        if avoid_polygons is not None:
            body["options"] = {"avoid_polygons": avoid_polygons}

        with httpx.Client(timeout=ORS_TIMEOUT_SECONDS) as client:
            response = client.post(
                os.environ.get("OPENROUTESERVICE_DIRECTIONS_URL", ORS_DIRECTIONS_URL),
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        geojson = response.json()
        feature = geojson["features"][0]
        summary = feature["properties"]["summary"]
        geometry = feature["geometry"]
        return RouteEstimate(
            distance_km=float(summary["distance"]) / 1000.0,
            eta_seconds=float(summary["duration"]),
            route_geometry=geometry,
            provider_status="openrouteservice",
            degraded=False,
            warnings=(),
        )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return _estimate_route_with_stub(
            from_location,
            to_location,
            road_summary,
            extra_warning="openrouteservice unavailable; using stub haversine",
        )


def _build_avoid_polygons(road_summary: Mapping[str, Any]) -> dict[str, Any] | None:
    feature_collection = road_summary.get("feature_collection")
    if not isinstance(feature_collection, Mapping):
        return None
    raw_features = feature_collection.get("features", [])
    if not isinstance(raw_features, list):
        return None

    polygons: list[Any] = []
    for feature in raw_features:
        if not isinstance(feature, Mapping):
            continue
        if _feature_status(feature) not in HARD_AVOID_STATUSES:
            continue
        geometry = feature.get("geometry", {})
        if not isinstance(geometry, Mapping):
            continue
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if not coordinates:
            continue
        if geometry_type == "Polygon":
            polygons.append(coordinates)
        elif geometry_type == "MultiPolygon":
            polygons.extend(coordinates)

    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}

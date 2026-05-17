"""
In-memory store for incidents + responders.

Hackathon scope: dict + asyncio.Lock. No SQLite, no Postgres.
Production would back this with sqlite or Postgres but the API stays the same.

  ┌──────────── IncidentStore ─────────────┐    ┌──────── ResponderStore ─────────┐
  │  insert(report) → IncidentReport       │    │  upsert(unit) → ResponderUnit   │
  │  get(id)        → IncidentReport|None  │    │  get(id)      → ResponderUnit|None│
  │  update(report) → IncidentReport       │    │  list()       → list[ResponderUnit]│
  │  list()         → list[IncidentReport] │    │  set_status(id, status)         │
  │  find_by_sim(run_id, ext_id)           │    └─────────────────────────────────┘
  │     (idempotency for simulator replays)│
  └────────────────────────────────────────┘
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from disaster.models import IncidentReport, ResponderStatus, ResponderUnit
from disaster.road_access import demo_road_access


class DispatchConflictError(RuntimeError):
    """Raised when a responder already has a different active dispatch."""


@dataclass(frozen=True)
class RouteRecommendationLeg:
    route_id: str
    leg_id: str
    responder_id: UUID
    incident_id: UUID | None
    target_id: str | None
    target_type: str | None
    leg: dict[str, Any]
    solver: str


@dataclass(frozen=True)
class RouteRecommendation:
    route_id: str
    solver: str
    payload: dict[str, Any]
    legs: dict[str, RouteRecommendationLeg]


@dataclass(frozen=True)
class ActiveDispatch:
    dispatch_id: str
    route_id: str
    leg_id: str
    responder_id: UUID
    incident_id: UUID
    started_by: str
    started_at: datetime
    solver: str
    leg: dict[str, Any]


class RoadAccessStore:
    def __init__(self) -> None:
        self._feature_collection: dict[str, Any] = demo_road_access()
        self._lock = asyncio.Lock()

    async def get(self) -> dict[str, Any]:
        async with self._lock:
            return deepcopy(self._feature_collection)

    async def set(self, feature_collection: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self._feature_collection = deepcopy(feature_collection)
            return deepcopy(self._feature_collection)


class IncidentStore:
    def __init__(self) -> None:
        self._incidents: dict[UUID, IncidentReport] = {}
        # idempotency: (sim_run_id, external_id) → IncidentReport.id
        self._sim_index: dict[tuple[str, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def insert(self, report: IncidentReport, *, external_id: str | None = None) -> IncidentReport:
        async with self._lock:
            if report.sim_run_id and external_id:
                key = (report.sim_run_id, external_id)
                existing_id = self._sim_index.get(key)
                if existing_id is not None:
                    return self._incidents[existing_id]
                self._sim_index[key] = report.id
            self._incidents[report.id] = report
            return report

    async def get(self, incident_id: UUID) -> IncidentReport | None:
        async with self._lock:
            return self._incidents.get(incident_id)

    async def update(self, report: IncidentReport) -> IncidentReport:
        async with self._lock:
            if report.id not in self._incidents:
                raise KeyError(f"incident {report.id} not found")
            self._incidents[report.id] = report
            return report

    async def list(self) -> list[IncidentReport]:
        async with self._lock:
            return list(self._incidents.values())

    async def count(self) -> int:
        async with self._lock:
            return len(self._incidents)


class ResponderStore:
    def __init__(self) -> None:
        self._units: dict[UUID, ResponderUnit] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, unit: ResponderUnit) -> ResponderUnit:
        async with self._lock:
            self._units[unit.id] = unit
            return unit

    async def get(self, unit_id: UUID) -> ResponderUnit | None:
        async with self._lock:
            return self._units.get(unit_id)

    async def list(self) -> list[ResponderUnit]:
        async with self._lock:
            return list(self._units.values())

    async def set_status(
        self,
        unit_id: UUID,
        status: ResponderStatus,
        *,
        assigned_incident_id: UUID | None = None,
    ) -> ResponderUnit:
        async with self._lock:
            unit = self._units.get(unit_id)
            if unit is None:
                raise KeyError(f"responder {unit_id} not found")
            updated = unit.model_copy(update={
                "status": status,
                "assigned_incident_id": assigned_incident_id,
            })
            self._units[unit_id] = updated
            return updated


class RouteRecommendationStore:
    def __init__(self) -> None:
        self._recommendations: dict[str, RouteRecommendation] = {}
        self._latest_route_id: str | None = None
        self._lock = asyncio.Lock()

    async def save(self, recommendation: RouteRecommendation) -> RouteRecommendation:
        async with self._lock:
            self._recommendations[recommendation.route_id] = recommendation
            self._latest_route_id = recommendation.route_id
            return recommendation

    async def get_leg(self, route_id: str, leg_id: str) -> RouteRecommendationLeg | None:
        async with self._lock:
            recommendation = self._recommendations.get(route_id)
            if recommendation is None:
                return None
            return recommendation.legs.get(leg_id)

    async def latest_route_id(self) -> str | None:
        async with self._lock:
            return self._latest_route_id


class ActiveDispatchStore:
    def __init__(self) -> None:
        self._dispatches_by_leg: dict[tuple[str, str], ActiveDispatch] = {}
        self._dispatches_by_responder: dict[UUID, ActiveDispatch] = {}
        self._lock = asyncio.Lock()

    async def start(self, dispatch: ActiveDispatch) -> tuple[ActiveDispatch, bool]:
        async with self._lock:
            dispatch_key = (dispatch.route_id, dispatch.leg_id)
            existing = self._dispatches_by_leg.get(dispatch_key)
            if existing is not None:
                return existing, False

            responder_dispatch = self._dispatches_by_responder.get(dispatch.responder_id)
            if responder_dispatch is not None:
                raise DispatchConflictError(
                    f"responder {dispatch.responder_id} already has active dispatch "
                    f"{responder_dispatch.dispatch_id}"
                )

            self._dispatches_by_leg[dispatch_key] = dispatch
            self._dispatches_by_responder[dispatch.responder_id] = dispatch
            return dispatch, True

    async def get_for_responder(self, responder_id: UUID) -> ActiveDispatch | None:
        async with self._lock:
            return self._dispatches_by_responder.get(responder_id)

    async def complete_for_responder(self, responder_id: UUID) -> ActiveDispatch | None:
        async with self._lock:
            dispatch = self._dispatches_by_responder.pop(responder_id, None)
            if dispatch is None:
                return None
            self._dispatches_by_leg.pop((dispatch.route_id, dispatch.leg_id), None)
            return dispatch

    async def list(self) -> list[ActiveDispatch]:
        async with self._lock:
            return list(self._dispatches_by_responder.values())

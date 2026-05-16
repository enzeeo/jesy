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
from uuid import UUID

from disaster.models import IncidentReport, ResponderStatus, ResponderUnit


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

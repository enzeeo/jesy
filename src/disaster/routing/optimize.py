"""
Routing top-level. Tries OR-Tools VRP with a 2s budget; falls back to greedy.

  ┌──────────── inputs ──────────────┐
  │  list[IncidentReport] (unresolved)│
  │  list[ResponderUnit] (available)  │
  │  time_budget_s = 2.0              │
  └────────────────┬─────────────────┘
                   │
                   ▼
        ┌──── try VRP ────┐  timeout / no solution
        │ ortools VRP     │ ───────────────────────▶ greedy_assign()
        └─────────────────┘                          (nearest available)
                   │
                   ▼
        ┌──── Assignment ──────┐
        │ {responder → ordered  │
        │  list[RouteLeg]}      │
        └───────────────────────┘
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from disaster.errors import NoFeasibleSolution
from disaster.models import IncidentReport, Location, ResponderUnit
from disaster.routing.greedy import greedy_assign

log = logging.getLogger(__name__)


@dataclass
class RouteLeg:
    """One step on a responder's route: go from `from_location` to incident."""
    incident_id: UUID
    from_location: Location
    to_location: Location
    distance_km: float
    eta_seconds: float


@dataclass
class Assignment:
    """Per-responder ordered route + solver provenance."""
    routes: dict[UUID, list[RouteLeg]] = field(default_factory=dict)
    unassigned: list[UUID] = field(default_factory=list)
    solver: str = "greedy"      # "vrp" or "greedy"
    elapsed_ms: float = 0.0


def optimize(
    incidents: list[IncidentReport],
    responders: list[ResponderUnit],
    *,
    time_budget_s: float = 2.0,
    prefer_vrp: bool = True,
) -> Assignment:
    """
    Compute responder→route assignments. Greedy by default for hackathon demo;
    VRP available behind `prefer_vrp=True`. Always returns a usable Assignment.
    """
    if not incidents:
        return Assignment(solver="greedy", routes={r.id: [] for r in responders})

    if not responders:
        return Assignment(
            solver="greedy",
            unassigned=[i.id for i in incidents],
        )

    if prefer_vrp:
        try:
            from disaster.routing.vrp import solve_vrp
            return solve_vrp(incidents, responders, time_budget_s=time_budget_s)
        except NoFeasibleSolution as e:
            log.warning("vrp: %s — falling back to greedy", e)
        except ImportError:
            log.warning("vrp: ortools not available — falling back to greedy")

    return greedy_assign(incidents, responders)

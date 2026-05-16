"""Tests for greedy + VRP routing (Phase C)."""
from __future__ import annotations

import math

import pytest

from disaster.errors import NoFeasibleSolution
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    ResponderStatus,
    ResponderType,
    ResponderUnit,
    Severity,
    Victim,
)
from disaster.routing import greedy_assign, optimize, solve_vrp


def _victim() -> Victim:
    return Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS)


def _incident(lat: float, lng: float, *, priority: float = 0.5, severity: Severity = Severity.DELAYED) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=lat, lng=lng, description=f"{lat},{lng}"),
        victims=[_victim()],
        priority_score=priority,
        severity=severity,
    )


def _responder(callsign: str, lat: float, lng: float) -> ResponderUnit:
    return ResponderUnit(
        callsign=callsign,
        type=ResponderType.ALS,
        location=Location(lat=lat, lng=lng, description=f"{callsign} base"),
        status=ResponderStatus.IDLE,
    )


# ── Greedy ───────────────────────────────────────────────────────────────────

def test_greedy_assigns_each_responder_to_closest_incident():
    # Two responders, two incidents at clearly distinct distances
    r_near = _responder("ALS-1", 19.7, -155.09)        # at incident A
    r_far = _responder("ALS-2", 19.80, -155.0)         # ~10 km north
    a = _incident(19.7, -155.09, priority=0.9)         # high priority near r_near
    b = _incident(19.80, -155.0, priority=0.4)         # lower priority near r_far

    assignment = greedy_assign([a, b], [r_near, r_far])

    # Highest priority taken first → r_near (closer to a) gets a
    assert any(leg.incident_id == a.id for leg in assignment.routes[r_near.id])
    assert any(leg.incident_id == b.id for leg in assignment.routes[r_far.id])
    assert assignment.unassigned == []


def test_greedy_unassigns_excess_incidents():
    r = _responder("ALS-1", 19.7, -155.0)
    a = _incident(19.7, -155.0)
    b = _incident(19.71, -155.0)
    assignment = greedy_assign([a, b], [r])
    # One responder, one assignment, one unassigned
    total_assigned = sum(len(legs) for legs in assignment.routes.values())
    assert total_assigned == 1
    assert len(assignment.unassigned) == 1


def test_greedy_higher_priority_assigned_first():
    """If a low-priority incident is closer, the high-priority one still wins."""
    r = _responder("ALS-1", 19.700, -155.000)
    far_high = _incident(19.800, -155.000, priority=0.95)   # far, urgent
    near_low = _incident(19.701, -155.000, priority=0.10)   # close, minor
    assignment = greedy_assign([far_high, near_low], [r])
    assert assignment.routes[r.id][0].incident_id == far_high.id
    assert assignment.unassigned == [near_low.id]


def test_greedy_eta_proportional_to_distance():
    r = _responder("ALS-1", 19.700, -155.000)
    near = _incident(19.701, -155.000)
    assignment = greedy_assign([near], [r])
    leg = assignment.routes[r.id][0]
    assert leg.distance_km > 0
    # 50 km/h avg → ~72 seconds per km
    assert math.isclose(leg.eta_seconds, leg.distance_km * 3600 / 50.0, rel_tol=1e-9)


# ── Top-level optimize() ─────────────────────────────────────────────────────

def test_optimize_with_no_incidents_returns_empty_routes():
    r = _responder("ALS-1", 19.7, -155.0)
    a = optimize([], [r], prefer_vrp=False)
    assert a.routes[r.id] == []
    assert a.unassigned == []


def test_optimize_with_no_responders_unassigns_all():
    i = _incident(19.7, -155.0)
    a = optimize([i], [], prefer_vrp=False)
    assert a.unassigned == [i.id]
    assert a.routes == {}


def test_optimize_falls_back_to_greedy_when_vrp_unavailable(monkeypatch):
    """Simulate ortools not installed → optimize() still returns a valid Assignment."""
    def boom(*_a, **_kw):
        raise NoFeasibleSolution("simulated VRP unavailable")

    monkeypatch.setattr("disaster.routing.vrp.solve_vrp", boom)
    r = _responder("ALS-1", 19.7, -155.0)
    i = _incident(19.7, -155.0)
    result = optimize([i], [r], prefer_vrp=True)
    assert result.solver == "greedy"
    assert len(result.routes[r.id]) == 1


# ── VRP smoke (only if ortools is importable) ────────────────────────────────

def test_vrp_smoke_solves_small_instance():
    pytest.importorskip("ortools")
    r1 = _responder("ALS-1", 19.70, -155.00)
    r2 = _responder("ALS-2", 19.80, -155.05)
    i1 = _incident(19.71, -155.01, priority=0.9)
    i2 = _incident(19.79, -155.06, priority=0.7)
    a = solve_vrp([i1, i2], [r1, r2], time_budget_s=2.0)
    assert a.solver == "vrp"
    total = sum(len(legs) for legs in a.routes.values())
    assert total == 2
    assert a.unassigned == []


# ── Integration: /routing/optimize endpoint ─────────────────────────────────

async def test_optimize_endpoint_publishes_route_recomputed():
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_t, _r): pass

    state = AppState()
    app = create_app(snowflake_writer=SnowflakeWriter(noop, flush_interval_s=0.05), state=state)
    await state.snowflake.start()
    try:
        await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
        await state.incidents.insert(_incident(19.71, -155.01, priority=0.8))

        agen = state.events.subscribe()
        consumer = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/routing/optimize")
            assert r.status_code == 200
            body = r.json()
            assert body["solver"] in {"greedy", "vrp"}
            assert len(body["routes"]) == 1

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "route_recomputed"
    finally:
        await state.snowflake.stop(0.5)

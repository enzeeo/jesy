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
from disaster.routing.weighted import DispatchTarget, optimize_weighted_flow


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


def test_greedy_chains_up_to_capacity_per_responder():
    """Default vehicle_capacity=5 — one responder takes up to 5 incidents."""
    r = _responder("ALS-1", 19.7, -155.0)
    incidents = [_incident(19.7 + 0.001 * i, -155.0) for i in range(7)]
    assignment = greedy_assign(incidents, [r])
    total_assigned = sum(len(legs) for legs in assignment.routes.values())
    assert total_assigned == 5
    assert len(assignment.unassigned) == 2


def test_greedy_capacity_one_falls_back_to_one_per_responder():
    """vehicle_capacity=1 reproduces the original 'one per responder' behavior."""
    r = _responder("ALS-1", 19.7, -155.0)
    a = _incident(19.7, -155.0)
    b = _incident(19.71, -155.0)
    assignment = greedy_assign([a, b], [r], vehicle_capacity=1)
    total_assigned = sum(len(legs) for legs in assignment.routes.values())
    assert total_assigned == 1
    assert len(assignment.unassigned) == 1


def test_greedy_higher_priority_assigned_first():
    """If a low-priority incident is closer, the high-priority one is taken FIRST."""
    r = _responder("ALS-1", 19.700, -155.000)
    far_high = _incident(19.800, -155.000, priority=0.95)   # far, urgent
    near_low = _incident(19.701, -155.000, priority=0.10)   # close, minor
    assignment = greedy_assign([far_high, near_low], [r])
    # First leg is the high-priority incident, regardless of proximity.
    assert assignment.routes[r.id][0].incident_id == far_high.id
    # With default capacity=5, both fit; near_low becomes leg #2.
    assert assignment.routes[r.id][1].incident_id == near_low.id


def test_greedy_eta_proportional_to_distance():
    r = _responder("ALS-1", 19.700, -155.000)
    near = _incident(19.701, -155.000)
    assignment = greedy_assign([near], [r])
    leg = assignment.routes[r.id][0]
    assert leg.distance_km > 0
    # 50 km/h avg → ~72 seconds per km
    assert math.isclose(leg.eta_seconds, leg.distance_km * 3600 / 50.0, rel_tol=1e-9)


# ── Weighted flow-time optimizer ─────────────────────────────────────────────

def test_weighted_flow_can_visit_closer_lower_priority_first():
    """Weighted flow-time may beat strict priority when total waiting cost drops."""
    responder = _responder("ALS-1", 19.700, -155.000)
    far_high = _incident(19.900, -155.000, priority=0.90)
    near_low = _incident(19.701, -155.000, priority=0.80)

    assignment = optimize_weighted_flow(
        [DispatchTarget.from_incident(far_high), DispatchTarget.from_incident(near_low)],
        [responder],
        route_stop_limit=2,
    )

    route = assignment.routes[responder.id]
    assert route[0].target_id == str(near_low.id)
    assert route[1].target_id == str(far_high.id)
    assert assignment.solver == "weighted_flow"


def test_weighted_flow_freezes_accepted_current_leg():
    responder = _responder("ALS-1", 19.700, -155.000)
    accepted = _incident(19.900, -155.000, priority=0.30)
    closer = _incident(19.701, -155.000, priority=0.90)

    assignment = optimize_weighted_flow(
        [DispatchTarget.from_incident(accepted), DispatchTarget.from_incident(closer)],
        [responder],
        route_stop_limit=2,
        accepted_assignments={responder.id: str(accepted.id)},
    )

    route = assignment.routes[responder.id]
    assert route[0].target_id == str(accepted.id)
    assert route[0].assignment_reason == "accepted_leg_frozen"
    assert route[1].target_id == str(closer.id)


def test_weighted_flow_marks_degraded_when_hard_avoid_roads_have_no_live_provider():
    responder = _responder("ALS-1", 19.700, -155.000)
    incident = _incident(19.701, -155.000, priority=0.8)
    road_access = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"road_status": "confirmed_closed", "confidence": 0.95},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-155.001, 19.699],
                    [-154.999, 19.699],
                    [-154.999, 19.702],
                    [-155.001, 19.702],
                    [-155.001, 19.699],
                ]],
            },
        }],
    }

    assignment = optimize_weighted_flow(
        [DispatchTarget.from_incident(incident)],
        [responder],
        road_access=road_access,
    )

    leg = assignment.routes[responder.id][0]
    assert leg.degraded is True
    assert leg.provider_status == "stub_haversine"
    assert "hard road closures not enforced by stub provider" in leg.warnings


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
            assert body["solver"] in {"greedy", "vrp", "weighted_flow"}
            assert len(body["routes"]) == 1

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "route_recomputed"
    finally:
        await state.snowflake.stop(0.5)


async def test_optimize_then_start_first_leg_updates_state_and_writes_dispatch_once():
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.models import IncidentStatus
    from disaster.snowflake import SnowflakeWriter

    collected: dict[str, list[dict]] = {}

    async def collect(table, rows):
        collected.setdefault(table, []).extend(rows)

    state = AppState()
    writer = SnowflakeWriter(collect, flush_interval_s=0.01)
    app = create_app(snowflake_writer=writer, state=state)
    await writer.start()
    try:
        responder = await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
        incident = await state.incidents.insert(_incident(19.71, -155.01, priority=0.8))

        agen = state.events.subscribe()
        consumer = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            optimize_response = await client.post("/routing/optimize")
            assert optimize_response.status_code == 200
            optimized = optimize_response.json()
            route_id = optimized["route_id"]
            leg_id = optimized["routes"][str(responder.id)][0]["leg_id"]

            start_response = await client.post(
                "/routing/dispatches/start",
                json={
                    "route_id": route_id,
                    "leg_id": leg_id,
                    "started_by": "dispatcher-a",
                },
            )
            repeat_response = await client.post(
                "/routing/dispatches/start",
                json={
                    "route_id": route_id,
                    "leg_id": leg_id,
                    "started_by": "dispatcher-a",
                },
            )

        assert start_response.status_code == 200
        assert repeat_response.status_code == 200
        assert repeat_response.json()["dispatch_id"] == start_response.json()["dispatch_id"]

        updated_responder = await state.responders.get(responder.id)
        updated_incident = await state.incidents.get(incident.id)
        assert updated_responder is not None
        assert updated_responder.status == ResponderStatus.EN_ROUTE
        assert updated_responder.assigned_incident_id == incident.id
        assert updated_incident is not None
        assert updated_incident.status == IncidentStatus.EN_ROUTE

        event = await asyncio.wait_for(consumer, timeout=1.0)
        while event["type"] != "dispatch_started":
            event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        await agen.aclose()
        assert event["data"]["route_id"] == route_id
        assert event["data"]["leg_id"] == leg_id
        assert event["data"]["responder_id"] == str(responder.id)

        await writer.stop(0.5)
        assert writer.metrics.enqueued == 1
        assert len(collected["responder_dispatches"]) == 1
    finally:
        await writer.stop(0.5)


async def test_start_dispatch_rejects_unknown_route_and_assignment_endpoint_returns_active_route():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    state = AppState()
    responder = await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
    await state.incidents.insert(_incident(19.71, -155.01, priority=0.8))
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post(
            "/routing/dispatches/start",
            json={"route_id": "missing-route", "leg_id": "missing-leg", "started_by": "dispatcher-a"},
        )
        assert missing.status_code == 404

        optimized = (await client.post("/routing/optimize")).json()
        route_id = optimized["route_id"]
        leg_id = optimized["routes"][str(responder.id)][0]["leg_id"]
        started = await client.post(
            "/routing/dispatches/start",
            json={"route_id": route_id, "leg_id": leg_id, "started_by": "dispatcher-a"},
        )
        assert started.status_code == 200

        assignment = await client.get(f"/responders/{responder.id}/assignment")
        assert assignment.status_code == 200
        payload = assignment.json()
        assert payload["route_id"] == route_id
        assert payload["leg_id"] == leg_id
        assert payload["responder_id"] == str(responder.id)
        assert payload["status"] == "en_route"


async def test_optimize_endpoint_accepts_stub_body_with_cluster_and_road_access():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    responder = _responder("ALS-1", 19.700, -155.000)
    road_access = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"road_status": "restricted", "confidence": 0.70},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-155.002, 19.699],
                    [-154.998, 19.699],
                    [-154.998, 19.702],
                    [-155.002, 19.702],
                    [-155.002, 19.699],
                ]],
            },
        }],
    }
    body = {
        "responders": [responder.model_dump(mode="json")],
        "clusters": [{
            "id": "cluster-hilo-1",
            "location": {"lat": 19.701, "lng": -155.000, "description": "cluster centroid"},
            "priority_score": 0.85,
            "demand_count": 3,
            "member_incident_ids": ["caller-a", "caller-b"],
            "required_capabilities": ["ALS"],
        }],
        "road_access": road_access,
        "route_stop_limit": 1,
    }

    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=AppState())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/routing/optimize", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["solver"] == "weighted_flow"
    assert payload["road_access"]["feature_count"] == 1
    route = payload["routes"][str(responder.id)]
    assert route[0]["target_id"] == "cluster-hilo-1"
    assert route[0]["target_type"] == "cluster"
    assert route[0]["route_geometry"]["type"] == "LineString"

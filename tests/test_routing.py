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
from disaster.routing.weighted import (
    DispatchTarget,
    RouteEstimate,
    _estimate_route,
    _estimate_route_with_mapbox,
    optimize_weighted_flow,
)


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


@pytest.fixture(autouse=True)
def clear_live_route_provider_tokens(monkeypatch):
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "")
    monkeypatch.setenv("NEXT_PUBLIC_MAPBOX_TOKEN", "")
    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "")
    monkeypatch.delenv("OPENROUTESERVICE_LIVE_ROUTING", raising=False)


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


def test_weighted_flow_does_not_use_live_provider_when_only_api_key_is_set(monkeypatch):
    responder = _responder("ALS-1", 19.700, -155.000)
    incidents = [_incident(19.701 + (0.001 * i), -155.000, priority=0.8) for i in range(4)]

    def fail_live_provider(*_args, **_kwargs):
        raise AssertionError("live route provider should be opt-in")

    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTESERVICE_LIVE_ROUTING", raising=False)
    monkeypatch.setattr("disaster.routing.weighted._estimate_route_with_ors", fail_live_provider)

    assignment = optimize_weighted_flow(
        [DispatchTarget.from_incident(incident) for incident in incidents],
        [responder],
        route_stop_limit=2,
    )

    assert len(assignment.routes[responder.id]) == 2
    assert assignment.road_access["provider"] == "stub_haversine"


def test_weighted_flow_live_provider_only_runs_for_final_legs(monkeypatch):
    responders = [
        _responder("ALS-1", 19.700, -155.000),
        _responder("ALS-2", 19.705, -155.005),
    ]
    incidents = [_incident(19.701 + (0.001 * i), -155.000, priority=0.8) for i in range(6)]
    call_count = 0

    def fake_live_provider(from_location, to_location, _road_summary, _api_key):
        nonlocal call_count
        call_count += 1
        return RouteEstimate(
            distance_km=1.0,
            eta_seconds=60.0,
            route_geometry={
                "type": "LineString",
                "coordinates": [
                    [from_location.lng, from_location.lat],
                    [to_location.lng, to_location.lat],
                ],
            },
            provider_status="openrouteservice",
        )

    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTESERVICE_LIVE_ROUTING", "true")
    monkeypatch.setattr("disaster.routing.weighted._estimate_route_with_ors", fake_live_provider)

    assignment = optimize_weighted_flow(
        [DispatchTarget.from_incident(incident) for incident in incidents],
        responders,
        route_stop_limit=2,
    )

    assigned_leg_count = sum(len(legs) for legs in assignment.routes.values())
    assert assigned_leg_count == 4
    assert call_count == assigned_leg_count


def test_mapbox_provider_parses_geojson_geometry(monkeypatch):
    from_location = Location(lat=29.3013, lng=-94.7977, description="station")
    to_location = Location(lat=29.3115, lng=-94.7893, description="caller")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "routes": [{
                    "distance": 1542.0,
                    "duration": 210.5,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-94.7977, 29.3013],
                            [-94.7930, 29.3062],
                            [-94.7893, 29.3115],
                        ],
                    },
                }],
            }

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, *, params):
            assert params["overview"] == "full"
            assert params["geometries"] == "geojson"
            assert params["access_token"] == "mapbox-token"
            return FakeResponse()

    monkeypatch.setattr("disaster.routing.weighted.httpx.Client", FakeClient)

    estimate = _estimate_route_with_mapbox(from_location, to_location, "mapbox-token")

    assert estimate is not None
    assert estimate.provider_status == "mapbox_directions"
    assert estimate.distance_km == pytest.approx(1.542)
    assert estimate.eta_seconds == pytest.approx(210.5)
    assert len(estimate.route_geometry["coordinates"]) == 3


def test_mapbox_failure_falls_back_to_stub_with_warning(monkeypatch):
    from_location = Location(lat=29.3013, lng=-94.7977, description="station")
    to_location = Location(lat=29.3115, lng=-94.7893, description="caller")

    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "mapbox-token")
    monkeypatch.setattr("disaster.routing.weighted._estimate_route_with_mapbox", lambda *_args: None)

    estimate = _estimate_route(
        from_location,
        to_location,
        {"hard_avoid_count": 0, "soft_penalty_count": 0},
        allow_live_provider=True,
    )

    assert estimate.provider_status == "stub_haversine"
    assert estimate.route_geometry["coordinates"] == [
        [from_location.lng, from_location.lat],
        [to_location.lng, to_location.lat],
    ]
    assert "mapbox directions unavailable; using fallback provider" in estimate.warnings


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
            assert body["road_access"]["feature_count"] == 2
            assert body["road_access"]["hard_avoid_count"] == 2
            assert body["road_access"]["feature_collection"]["type"] == "FeatureCollection"

        first_event = await asyncio.wait_for(consumer, timeout=1.0)
        second_event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        await agen.aclose()
        event_types = {first_event["type"], second_event["type"]}
        assert event_types == {"route_recomputed", "road_access_updated"}
        road_event = first_event if first_event["type"] == "road_access_updated" else second_event
        assert road_event["data"]["hard_avoid_count"] == 2
    finally:
        await state.snowflake.stop(0.5)


async def test_road_access_endpoint_returns_demo_blocked_roads():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=AppState())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/routing/road-access")

    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_count"] == 2
    assert payload["hard_avoid_count"] == 2
    assert payload["feature_collection"]["type"] == "FeatureCollection"


async def test_blocked_roads_endpoint_returns_demo_stub_labels_and_geojson():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=AppState())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/routing/blocked-roads")

    assert response.status_code == 200
    payload = response.json()
    labels = {road["label"] for road in payload["blocked_roads"]}
    assert labels == {"Harbor flood closure", "Seawall washout"}
    assert payload["blocked_count"] == 2
    assert payload["hard_avoid_count"] == 2
    assert payload["feature_collection"]["type"] == "FeatureCollection"
    assert len(payload["feature_collection"]["features"]) == 2


async def test_demo_reset_and_seed_publish_road_access_updated():
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    state = AppState()
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)
    transport = ASGITransport(app=app)
    agen = state.events.subscribe()
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first_seed_task = asyncio.create_task(agen.__anext__())
            await asyncio.sleep(0.01)
            seed_response = await client.post("/demo/seed-responders")
            assert seed_response.status_code == 200
            first_seed_event = await asyncio.wait_for(first_seed_task, timeout=1.0)
            second_seed_event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
            seed_event_types = {first_seed_event["type"], second_seed_event["type"]}
            assert seed_event_types == {"responders_seeded", "road_access_updated"}
            seed_road_event = (
                first_seed_event if first_seed_event["type"] == "road_access_updated" else second_seed_event
            )
            assert seed_road_event["data"]["hard_avoid_count"] == 2

            first_reset_task = asyncio.create_task(agen.__anext__())
            await asyncio.sleep(0.01)
            reset_response = await client.post("/demo/reset")
            assert reset_response.status_code == 200
            first_reset_event = await asyncio.wait_for(first_reset_task, timeout=1.0)
            second_reset_event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
            reset_event_types = {first_reset_event["type"], second_reset_event["type"]}
            assert reset_event_types == {"state_reset", "road_access_updated"}
            reset_road_event = (
                first_reset_event if first_reset_event["type"] == "road_access_updated" else second_reset_event
            )
            assert reset_road_event["data"]["hard_avoid_count"] == 2
    finally:
        await agen.aclose()


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


async def test_start_dispatch_rebases_stale_leg_to_current_responder_location():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    state = AppState()
    responder = await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
    incident = await state.incidents.insert(_incident(19.80, -155.00, priority=0.8))
    current_location = Location(lat=19.76, lng=-155.02, description="completed aid location")
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        optimized = (await client.post("/routing/optimize")).json()
        leg = optimized["routes"][str(responder.id)][0]
        assert leg["from_location"]["lat"] == pytest.approx(responder.location.lat)

        await state.responders.upsert(responder.model_copy(update={"location": current_location}))
        started = await client.post(
            "/routing/dispatches/start",
            json={
                "route_id": optimized["route_id"],
                "leg_id": leg["leg_id"],
                "started_by": "dispatcher-a",
            },
        )

    assert started.status_code == 200
    route_leg = started.json()["route_leg"]
    assert route_leg["from_location"]["lat"] == pytest.approx(current_location.lat)
    assert route_leg["from_location"]["lng"] == pytest.approx(current_location.lng)
    assert route_leg["route_geometry"]["coordinates"][0] == [
        pytest.approx(current_location.lng),
        pytest.approx(current_location.lat),
    ]
    assert route_leg["to_location"]["lat"] == pytest.approx(incident.location.lat)


async def test_optimize_endpoint_freezes_active_dispatch_from_backend_state():
    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    state = AppState()
    responder = await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
    active_incident = await state.incidents.insert(_incident(19.90, -155.00, priority=0.30))
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        optimized = (await client.post("/routing/optimize")).json()
        active_leg_id = optimized["routes"][str(responder.id)][0]["leg_id"]
        started = await client.post(
            "/routing/dispatches/start",
            json={
                "route_id": optimized["route_id"],
                "leg_id": active_leg_id,
                "started_by": "dispatcher-a",
            },
        )
        assert started.status_code == 200

        await state.incidents.insert(_incident(19.701, -155.00, priority=0.95))
        recomputed = await client.post("/routing/optimize")

    assert recomputed.status_code == 200
    route = recomputed.json()["routes"][str(responder.id)]
    assert route[0]["target_id"] == str(active_incident.id)
    assert route[0]["incident_id"] == str(active_incident.id)
    assert route[0]["assignment_reason"] == "accepted_leg_frozen"


async def test_complete_assignment_releases_responder_for_next_optimized_call():
    import asyncio
    from datetime import UTC, datetime, timedelta

    from httpx import ASGITransport, AsyncClient

    from disaster.app.deps import AppState
    from disaster.app.main import create_app
    from disaster.models import IncidentStatus
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table, _rows): pass

    state = AppState()
    responder = await state.responders.upsert(_responder("ALS-1", 19.70, -155.00))
    active_incident = await state.incidents.insert(_incident(19.90, -155.00, priority=0.30))
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)
    transport = ASGITransport(app=app)

    agen = state.events.subscribe()
    consumer = asyncio.create_task(agen.__anext__())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        optimized = (await client.post("/routing/optimize")).json()
        active_leg_id = optimized["routes"][str(responder.id)][0]["leg_id"]
        started = await client.post(
            "/routing/dispatches/start",
            json={
                "route_id": optimized["route_id"],
                "leg_id": active_leg_id,
                "started_by": "dispatcher-a",
            },
        )
        assert started.status_code == 200

        next_incident = await state.incidents.insert(_incident(19.701, -155.00, priority=0.95))
        recomputed = await client.post("/routing/optimize")
        assert recomputed.status_code == 200
        en_route_leg = recomputed.json()["routes"][str(responder.id)][0]
        assert en_route_leg["target_id"] == str(active_incident.id)
        assert en_route_leg["assignment_reason"] == "accepted_leg_frozen"

        first_ping_at = datetime.now(UTC)
        for timestamp in [first_ping_at, first_ping_at + timedelta(seconds=5)]:
            arrival = await client.post(
                f"/responders/{responder.id}/location",
                json={
                    "lat": active_incident.location.lat,
                    "lng": active_incident.location.lng,
                    "accuracy_m": 8,
                    "timestamp": timestamp.isoformat(),
                },
            )
        assert arrival.status_code == 200
        assert arrival.json()["arrival_detected"] is True

        completed = await client.post(
            f"/responders/{responder.id}/assignment/complete",
            json={"completed_by": "responder-a"},
        )
        assert completed.status_code == 200
        assert completed.json()["assignment_id"] == started.json()["dispatch_id"]

        assignment = await client.get(f"/responders/{responder.id}/assignment")
        released_route = await client.post("/routing/optimize")

    assert assignment.status_code == 200
    assert assignment.json() is None
    updated_responder = await state.responders.get(responder.id)
    resolved_incident = await state.incidents.get(active_incident.id)
    assert updated_responder is not None
    assert updated_responder.status == ResponderStatus.IDLE
    assert updated_responder.assigned_incident_id is None
    assert resolved_incident is not None
    assert resolved_incident.status == IncidentStatus.RESOLVED
    next_route = released_route.json()["routes"][str(responder.id)]
    assert next_route[0]["target_id"] == str(next_incident.id)
    assert next_route[0]["from_location"]["lat"] == pytest.approx(active_incident.location.lat)
    assert next_route[0]["from_location"]["lng"] == pytest.approx(active_incident.location.lng)

    event = await asyncio.wait_for(consumer, timeout=1.0)
    while event["type"] != "dispatch_completed":
        event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
    await agen.aclose()
    assert event["data"]["responder_id"] == str(responder.id)
    assert event["data"]["incident_id"] == str(active_incident.id)
    assert event["data"]["status"] == "idle"


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

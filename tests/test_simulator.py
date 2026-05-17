"""Tests for DisasterSimulator + /sim endpoints."""
from __future__ import annotations

import asyncio
import contextlib
import math

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import Severity
from disaster.road_access import demo_road_access
from disaster.simulator import DisasterSimulator, generate_texas_flood_profile
from disaster.simulator.disaster_sim import ASHEVILLE_CALLER_ANCHORS

# ── Generator ────────────────────────────────────────────────────────────────

def test_generates_requested_count():
    events = generate_texas_flood_profile(count=50)
    assert len(events) == 50


def test_deterministic_given_seed():
    a = generate_texas_flood_profile(count=10, seed=42)
    b = generate_texas_flood_profile(count=10, seed=42)
    assert [e.incident.severity for e in a] == [e.incident.severity for e in b]
    assert [e.external_id for e in a] == [e.external_id for e in b]


def test_severity_distribution_approximately_matches_profile():
    events = generate_texas_flood_profile(count=500, seed=1)
    counts = {s: 0 for s in Severity}
    for e in events:
        counts[e.incident.severity] += 1
    # Profile: 12% Immediate, 35% Delayed, 50% Minor, 3% Deceased (loose bounds)
    assert 0.07 <= counts[Severity.IMMEDIATE] / 500 <= 0.18
    assert 0.30 <= counts[Severity.DELAYED] / 500 <= 0.42
    assert 0.42 <= counts[Severity.MINOR] / 500 <= 0.58


def test_asheville_land_anchor_locations():
    """All incidents stay near known Asheville land anchors without stacking on exact points."""
    events = generate_texas_flood_profile(count=100)
    unique_points = {
        (round(e.incident.location.lat, 6), round(e.incident.location.lng, 6))
        for e in events
    }

    assert len(unique_points) == len(events)

    for e in events:
        nearest_anchor_km = min(
            _haversine_km(
                (e.incident.location.lat, e.incident.location.lng),
                (anchor_latitude, anchor_longitude),
            )
            for anchor_latitude, anchor_longitude, _description in ASHEVILLE_CALLER_ANCHORS
        )
        assert nearest_anchor_km <= 0.75
        assert 35.53 < e.incident.location.lat < 35.66
        assert -82.66 < e.incident.location.lng < -82.48


def test_asheville_land_anchors_avoid_default_flood_polygons():
    flood_polygons = [
        feature["geometry"]["coordinates"][0]
        for feature in demo_road_access()["features"]
        if feature["geometry"]["type"] == "Polygon"
    ]

    for lat, lng, _description in ASHEVILLE_CALLER_ANCHORS:
        assert not any(_point_in_polygon(lng, lat, polygon) for polygon in flood_polygons)


def test_generated_asheville_locations_avoid_default_flood_polygons():
    flood_polygons = [
        feature["geometry"]["coordinates"][0]
        for feature in demo_road_access()["features"]
        if feature["geometry"]["type"] == "Polygon"
    ]
    events = generate_texas_flood_profile(count=200)

    for event in events:
        lat = event.incident.location.lat
        lng = event.incident.location.lng
        assert not any(_point_in_polygon(lng, lat, polygon) for polygon in flood_polygons)


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, vertex in enumerate(polygon):
        xi, yi = vertex
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_latitude, left_longitude = left
    right_latitude, right_longitude = right
    earth_radius_km = 6371.0
    latitude_delta = math.radians(right_latitude - left_latitude)
    longitude_delta = math.radians(right_longitude - left_longitude)
    a = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(left_latitude))
        * math.cos(math.radians(right_latitude))
        * math.sin(longitude_delta / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def test_external_ids_unique():
    events = generate_texas_flood_profile(count=200)
    assert len({e.external_id for e in events}) == 200


def test_emit_delays_monotonic_and_within_window():
    events = generate_texas_flood_profile(count=100, demo_window_s=60.0)
    delays = [e.delay_s for e in events]
    assert delays == sorted(delays)
    assert delays[0] >= 0.0
    assert delays[-1] <= 60.0


# ── Runner ───────────────────────────────────────────────────────────────────

async def test_runner_emits_in_order_with_compressed_timing():
    received: list[str] = []

    async def on_incident(incident, external_id):
        received.append(external_id)

    sim = DisasterSimulator(on_incident=on_incident)
    await sim.start(count=5, demo_window_s=0.2, run_id="test")
    # Wait for sim to finish (polling is fine for a 5-event test).
    deadline = 2.0
    elapsed = 0.0
    step = 0.05
    while sim.running and elapsed < deadline:
        await asyncio.sleep(step)
        elapsed += step
    assert not sim.running
    assert len(received) == 5
    assert received == sorted(received)
    assert sim.events_emitted == 5
    assert sim.events_dropped == 0


async def test_runner_stop_cancels_in_flight():
    received: list[str] = []

    async def on_incident(incident, external_id):
        received.append(external_id)

    sim = DisasterSimulator(on_incident=on_incident)
    await sim.start(count=100, demo_window_s=10.0, run_id="test")
    await asyncio.sleep(0.1)
    await sim.stop()
    # Some emitted, but not all — stop interrupted the run
    assert len(received) < 100


# ── /sim endpoints ───────────────────────────────────────────────────────────

async def test_sim_start_creates_incidents_and_broadcasts():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/sim/start", json={"count": 5, "demo_window_s": 0.2})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "started"
        # Let it finish
        await asyncio.sleep(0.6)
        assert await state.incidents.count() == 5

        s = await ac.get("/sim/status")
        assert s.json()["events_emitted"] == 5


async def test_sim_start_stages_road_block_updates():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    agen = state.events.subscribe()
    road_counts: list[int] = []
    next_event: asyncio.Task | None = None

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            next_event = asyncio.create_task(agen.__anext__())
            await asyncio.sleep(0.01)
            r = await ac.post(
                "/sim/start",
                json={"count": 1, "demo_window_s": 0.3, "road_block_updates": 2},
            )
            assert r.status_code == 200

            deadline = asyncio.get_running_loop().time() + 1.5
            while len(road_counts) < 3 and asyncio.get_running_loop().time() < deadline:
                event = await asyncio.wait_for(next_event, timeout=1.0)
                if event["type"] == "road_access_updated":
                    road_counts.append(event["data"]["hard_avoid_count"])
                next_event = asyncio.create_task(agen.__anext__())

        assert road_counts == [4, 5, 6]
        road_access = await state.road_access.get()
        assert len(road_access["features"]) == 6
    finally:
        sim = getattr(state, "_sim", None)
        if sim is not None:
            await sim.stop()
        road_block_task = getattr(state, "_road_block_task", None)
        if road_block_task is not None:
            road_block_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await road_block_task
        if next_event is not None and not next_event.done():
            next_event.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await next_event
        await agen.aclose()


async def test_sim_idempotent_replay():
    """Same run_id replayed → no duplicate incidents inserted (store dedupes)."""
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/sim/start", json={"count": 5, "demo_window_s": 0.2, "run_id": "dup"})
        await asyncio.sleep(0.6)
        assert await state.incidents.count() == 5

        # Replay same run_id
        await ac.post("/sim/start", json={"count": 5, "demo_window_s": 0.2, "run_id": "dup"})
        await asyncio.sleep(0.6)
        assert await state.incidents.count() == 5  # NOT 10

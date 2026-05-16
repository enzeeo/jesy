"""Tests for DisasterSimulator + /sim endpoints."""
from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import Severity
from disaster.simulator import DisasterSimulator, generate_hilo_tsunami_profile

# ── Generator ────────────────────────────────────────────────────────────────

def test_generates_requested_count():
    events = generate_hilo_tsunami_profile(count=50)
    assert len(events) == 50


def test_deterministic_given_seed():
    a = generate_hilo_tsunami_profile(count=10, seed=42)
    b = generate_hilo_tsunami_profile(count=10, seed=42)
    assert [e.incident.severity for e in a] == [e.incident.severity for e in b]
    assert [e.external_id for e in a] == [e.external_id for e in b]


def test_severity_distribution_approximately_matches_profile():
    events = generate_hilo_tsunami_profile(count=500, seed=1)
    counts = {s: 0 for s in Severity}
    for e in events:
        counts[e.incident.severity] += 1
    # Profile: 12% Immediate, 35% Delayed, 50% Minor, 3% Deceased (loose bounds)
    assert 0.07 <= counts[Severity.IMMEDIATE] / 500 <= 0.18
    assert 0.30 <= counts[Severity.DELAYED] / 500 <= 0.42
    assert 0.42 <= counts[Severity.MINOR] / 500 <= 0.58


def test_coastal_weighting():
    """All incidents land near the coastal corridor (lat near 19.73)."""
    events = generate_hilo_tsunami_profile(count=100)
    for e in events:
        assert 19.70 < e.incident.location.lat < 19.75


def test_external_ids_unique():
    events = generate_hilo_tsunami_profile(count=200)
    assert len({e.external_id for e in events}) == 200


def test_emit_delays_monotonic_and_within_window():
    events = generate_hilo_tsunami_profile(count=100, demo_window_s=60.0)
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

"""
Regression tests for AAR Hour 0 plumbing — the prerequisites without which the
AAR sees no data.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
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
from disaster.snowflake import SnowflakeWriter


def _incident(lat: float = 19.7, lng: float = -155.0) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=lat, lng=lng, description=f"{lat},{lng}"),
        victims=[Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS)],
        priority_score=0.5,
        severity=Severity.DELAYED,
    )


def _responder(callsign: str, lat: float = 19.7, lng: float = -155.0) -> ResponderUnit:
    return ResponderUnit(
        callsign=callsign,
        type=ResponderType.ALS,
        location=Location(lat=lat, lng=lng, description=f"{callsign} base"),
        status=ResponderStatus.IDLE,
    )


async def test_routing_optimize_writes_responder_dispatches_with_sim_run_id():
    """H0.1 — /routing/optimize must persist dispatch rows so AAR has a baseline."""
    captured: list[tuple[str, list[dict]]] = []

    async def capture(table: str, rows: list[dict]) -> None:
        captured.append((table, rows))

    state = AppState()
    state.active_sim_run_id = "test-run"
    app = create_app(
        snowflake_writer=SnowflakeWriter(capture, flush_interval_s=0.05, batch_size=1),
        state=state,
    )
    await state.snowflake.start()
    try:
        await state.responders.upsert(_responder("ALS-1"))
        await state.incidents.insert(_incident(19.71, -155.01))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/routing/optimize")
            assert r.status_code == 200

        # Give the writer a moment to flush (interval is 50ms)
        import asyncio
        await asyncio.sleep(0.2)

        dispatch_rows = [r for table, rows in captured for r in rows if table == "responder_dispatches"]
        assert len(dispatch_rows) >= 1
        # Every row must carry sim_run_id
        assert all(r.get("sim_run_id") == "test-run" for r in dispatch_rows)
        assert all(r.get("solver") in {"greedy", "vrp"} for r in dispatch_rows)
        # Schema columns present
        for r in dispatch_rows:
            assert "responder_id" in r
            assert "incident_id" in r
            assert "dispatched_at" in r
            assert "distance_km" in r
            assert "eta_seconds" in r
    finally:
        await state.snowflake.stop(0.5)


async def test_sim_start_sets_active_sim_run_id():
    state = AppState()
    app = create_app(state=state)
    # Use a long window so the sim is genuinely "in progress" when we assert.
    # A tiny window + low count finishes synchronously and the auto-clear
    # callback (registered on the sim task done-handler) would have already
    # cleared active_sim_run_id by the time we look.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/sim/start", json={"count": 200, "run_id": "sim-run-1", "demo_window_s": 60})
        assert r.status_code == 200
        assert state.active_sim_run_id == "sim-run-1"
        await c.post("/sim/stop")
    assert state.active_sim_run_id is None


async def test_sim_stop_clears_active_sim_run_id():
    state = AppState()
    app = create_app(state=state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/sim/start", json={"count": 200, "run_id": "sim-run-1", "demo_window_s": 60})
        assert state.active_sim_run_id == "sim-run-1"
        r = await c.post("/sim/stop")
        assert r.status_code == 200
    assert state.active_sim_run_id is None


async def test_sim_natural_completion_auto_clears_active_sim_run_id():
    """Regression: simulator finishing on its own (no /sim/stop call) must
    clear active_sim_run_id, otherwise the AAR stays stuck in 'Run in progress'."""
    import asyncio

    state = AppState()
    app = create_app(state=state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Tiny window — finishes in well under a second.
        r = await c.post("/sim/start", json={"count": 3, "run_id": "auto-clear", "demo_window_s": 0.2})
        assert r.status_code == 200
        # Yield long enough for the simulator to drain its event queue.
        await asyncio.sleep(0.5)
    assert state.active_sim_run_id is None, "auto-clear must fire when sim finishes naturally"


async def test_sim_start_409_when_another_run_active():
    state = AppState()
    state.active_sim_run_id = "existing-run"
    app = create_app(state=state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/sim/start", json={"count": 1, "run_id": "different-run", "demo_window_s": 0.5})
        assert r.status_code == 409
        assert "another sim run" in r.json()["detail"].lower()


@pytest.mark.parametrize("scenario", ["pier4_immediate", "banyan_delayed", "wailoa_minor"])
async def test_demo_trigger_call_stamps_active_sim_run_id(scenario):
    """H0.2 — /demo/trigger-call must stamp incident with active_sim_run_id."""
    state = AppState()
    state.active_sim_run_id = "active-call-test"
    app = create_app(state=state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/demo/trigger-call?scenario={scenario}")
        assert r.status_code == 200

    incidents = await state.incidents.list()
    assert all(i.sim_run_id == "active-call-test" for i in incidents)


async def test_incidents_post_stamps_active_sim_run_id():
    """H0.2 — caller-ui POST /incidents must stamp from active_sim_run_id."""
    state = AppState()
    state.active_sim_run_id = "caller-ui-test"
    app = create_app(state=state)

    payload = _incident().model_dump(mode="json")
    payload["sim_run_id"] = None  # client doesn't set it

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/incidents", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["sim_run_id"] == "caller-ui-test"


async def test_incidents_post_preserves_client_supplied_sim_run_id():
    """If client explicitly sets sim_run_id, don't overwrite it."""
    state = AppState()
    state.active_sim_run_id = "active-run"
    app = create_app(state=state)

    payload = _incident().model_dump(mode="json")
    payload["sim_run_id"] = "client-chose-this"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/incidents", json=payload)
        assert r.status_code == 201
        assert r.json()["sim_run_id"] == "client-chose-this"

"""Integration tests for /api/analysis routes."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from disaster.analysis.aar import clear_cache
from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    ResponderType,
    ResponderUnit,
    Victim,
)
from disaster.snowflake import SnowflakeWriter


def _inc(*, sim_run_id: str | None, lat: float = 19.7, lng: float = -155.0) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=lat, lng=lng, description="x"),
        victims=[Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS)],
        sim_run_id=sim_run_id,
    )


def _responder(callsign: str) -> ResponderUnit:
    return ResponderUnit(
        callsign=callsign,
        type=ResponderType.ALS,
        location=Location(lat=19.7, lng=-155.0, description=f"{callsign}"),
    )


async def _noop(_t, _r): pass


@pytest.fixture(autouse=True)
def _reset():
    clear_cache()
    yield
    clear_cache()


async def test_get_aar_returns_200_with_full_payload():
    state = AppState()
    app = create_app(snowflake_writer=SnowflakeWriter(_noop), state=state)
    await state.snowflake.start()
    try:
        await state.incidents.insert(_inc(sim_run_id="r-200"))
        await state.responders.upsert(_responder("A"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/analysis/r-200")
        assert r.status_code == 200
        body = r.json()
        assert body["sim_run_id"] == "r-200"
        assert "scorecard" in body
        assert "counterfactual" in body
        assert "vulnerability" in body
        assert "timeline" in body
        assert "incidents_geo" in body
    finally:
        await state.snowflake.stop(0.5)


async def test_get_aar_returns_404_for_unknown_run():
    state = AppState()
    app = create_app(snowflake_writer=SnowflakeWriter(_noop), state=state)
    await state.snowflake.start()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/analysis/no-such-run")
        assert r.status_code == 404
    finally:
        await state.snowflake.stop(0.5)


async def test_runs_index_returns_distinct_sim_run_ids():
    state = AppState()
    app = create_app(snowflake_writer=SnowflakeWriter(_noop), state=state)
    await state.snowflake.start()
    try:
        await state.incidents.insert(_inc(sim_run_id="r-a"))
        await state.incidents.insert(_inc(sim_run_id="r-a"))
        await state.incidents.insert(_inc(sim_run_id="r-b"))
        await state.incidents.insert(_inc(sim_run_id=None))  # unattached, should be ignored
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/analysis/runs")
        assert r.status_code == 200
        body = r.json()
        run_ids = {r["sim_run_id"] for r in body["runs"]}
        assert run_ids == {"r-a", "r-b"}
        # r-a has 2 incidents, r-b has 1
        counts = {r["sim_run_id"]: r["incident_count"] for r in body["runs"]}
        assert counts == {"r-a": 2, "r-b": 1}
    finally:
        await state.snowflake.stop(0.5)


async def test_narrative_endpoint_returns_fallback_without_llm():
    state = AppState()
    # Don't wire LLM client
    app = create_app(snowflake_writer=SnowflakeWriter(_noop), state=state)
    await state.snowflake.start()
    try:
        await state.incidents.insert(_inc(sim_run_id="r-narr"))
        await state.responders.upsert(_responder("A"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/analysis/r-narr/narrative")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "fallback"
        assert body["narrative"]  # non-empty
    finally:
        await state.snowflake.stop(0.5)


async def test_narrative_for_live_run_returns_in_progress_message():
    state = AppState()
    state.active_sim_run_id = "live"
    app = create_app(snowflake_writer=SnowflakeWriter(_noop), state=state)
    await state.snowflake.start()
    try:
        await state.incidents.insert(_inc(sim_run_id="live"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/analysis/live/narrative")
        assert r.status_code == 200
        body = r.json()
        assert "in progress" in body["narrative"].lower()
        assert body["source"] == "fallback"
    finally:
        await state.snowflake.stop(0.5)

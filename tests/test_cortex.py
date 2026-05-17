"""Tests for /cortex/scan (Snowflake path + in-memory fallback)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    Perfusion,
    Severity,
    Victim,
)
from disaster.snowflake.cortex import detect_clusters, detect_clusters_snowflake


def _incident(injuries: list[str], lat: float = 35.62) -> IncidentReport:
    return IncidentReport(
        timestamp=datetime.now(UTC),
        location=Location(lat=lat, lng=-82.5515, description="x"),
        victims=[Victim(injuries=injuries, mobility=Mobility.WALKING,
                        breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.NORMAL)],
        severity=Severity.DELAYED,
    )


# ── In-memory matcher ────────────────────────────────────────────────────────

def test_in_memory_detects_respiratory_cluster():
    incidents = [_incident(["respiratory distress"]) for _ in range(3)]
    alerts = detect_clusters(incidents)
    assert len(alerts) == 1
    assert alerts[0]["injury_bucket"] == "respiratory"
    assert alerts[0]["sector"] == "NORTH"
    assert alerts[0]["count"] == 3


def test_in_memory_no_alert_below_threshold():
    incidents = [_incident(["respiratory distress"]) for _ in range(2)]
    assert detect_clusters(incidents) == []


def test_in_memory_ignores_other_bucket():
    """Non-bucketed injuries don't trigger alerts even at quorum."""
    incidents = [_incident(["chest pain"]) for _ in range(5)]
    assert detect_clusters(incidents) == []


# ── Snowflake path ───────────────────────────────────────────────────────────

async def test_snowflake_path_runs_query_and_shapes_alerts():
    """Mock the query runner; assert alerts mirror in-memory shape."""
    captured_sql: list[str] = []

    async def fake_runner(sql: str, _params: tuple):
        captured_sql.append(sql)
        return [
            {"INJURY_BUCKET": "respiratory", "SECTOR": "NORTH", "N": 4},
            {"INJURY_BUCKET": "trauma", "SECTOR": "SOUTH", "N": 3},
        ]

    alerts = await detect_clusters_snowflake(fake_runner)
    assert len(alerts) == 2
    assert {a["injury_bucket"] for a in alerts} == {"respiratory", "trauma"}
    assert alerts[0]["count"] == 4
    assert "clustering" in alerts[0]["message"]
    # Verify the SQL string is what we expect to ship
    assert "GROUP BY INJURY_BUCKET, SECTOR" in captured_sql[0]


async def test_snowflake_path_handles_lowercase_column_names():
    """Snowflake DictCursor returns lowercase keys with parameterized warehouse settings."""
    async def fake_runner(_sql: str, _params: tuple):
        return [{"injury_bucket": "burn", "sector": "CENTRAL", "n": 3}]
    alerts = await detect_clusters_snowflake(fake_runner)
    assert alerts[0]["injury_bucket"] == "burn"
    assert alerts[0]["count"] == 3


# ── /cortex/scan endpoint: Snowflake → in-memory fallback ────────────────────

async def test_endpoint_uses_snowflake_when_runner_configured():
    state = AppState()
    app = create_app(state=state)

    async def fake_runner(_sql: str, _params: tuple):
        return [{"INJURY_BUCKET": "respiratory", "SECTOR": "NORTH", "N": 5}]
    state._sf_query_runner = fake_runner

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/cortex/scan")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "snowflake"
        assert len(body["alerts"]) == 1
        assert body["alerts"][0]["injury_bucket"] == "respiratory"


async def test_endpoint_falls_back_to_in_memory_when_snowflake_errors():
    state = AppState()
    app = create_app(state=state)
    # Seed enough incidents to trigger the in-memory matcher
    for _ in range(3):
        await state.incidents.insert(_incident(["respiratory distress"]))

    async def broken_runner(_sql: str, _params: tuple):
        raise RuntimeError("warehouse offline")
    state._sf_query_runner = broken_runner

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/cortex/scan")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "in_memory"
        assert len(body["alerts"]) == 1


async def test_endpoint_in_memory_when_no_runner():
    state = AppState()
    app = create_app(state=state)
    for _ in range(3):
        await state.incidents.insert(_incident(["respiratory distress"]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/cortex/scan")
        body = r.json()
        assert body["source"] == "in_memory"
        assert len(body["alerts"]) == 1


async def test_endpoint_emits_sse_event_with_sequence_id():
    state = AppState()
    app = create_app(state=state)
    for _ in range(3):
        await state.incidents.insert(_incident(["respiratory distress"]))

    agen = state.events.subscribe()
    consumer = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.01)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/cortex/scan")
        assert r.json()["emitted_count"] == 1

    event = await asyncio.wait_for(consumer, timeout=1.0)
    await agen.aclose()
    assert event["type"] == "cortex_alert"
    assert "sequence_id" in event
    assert isinstance(event["sequence_id"], int)

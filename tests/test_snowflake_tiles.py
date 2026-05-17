"""Tests for Snowflake tile queries (in-memory fallback path)."""
from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    IncidentSource,
    Location,
    Mobility,
    Perfusion,
    Severity,
    Victim,
)
from disaster.snowflake import TILE_QUERIES
from disaster.snowflake.tiles import _synthetic_tile


def _incident(sev: Severity, *, lat: float = 29.30, conf: float = 0.95, source: IncidentSource = IncidentSource.VOICE) -> IncidentReport:
    return IncidentReport(
        timestamp=datetime.now(UTC),
        location=Location(lat=lat, lng=-94.79, description="x"),
        victims=[Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS,
                        perfusion=Perfusion.NORMAL)],
        severity=sev,
        confidence=conf,
        source=source,
        priority_score=0.7 if sev == Severity.IMMEDIATE else 0.4,
    )


# ── Unit: synthetic tile shapes ─────────────────────────────────────────────

def test_severity_distribution_counts_all_severities():
    incidents = [_incident(Severity.IMMEDIATE), _incident(Severity.IMMEDIATE), _incident(Severity.MINOR)]
    rows = _synthetic_tile("severity_distribution", incidents)
    by_sev = {r["severity"]: r["n"] for r in rows}
    assert by_sev["Immediate"] == 2
    assert by_sev["Minor"] == 1
    assert by_sev["Delayed"] == 0
    assert by_sev["Deceased"] == 0


def test_incident_rate_aggregates_per_minute():
    incidents = [_incident(Severity.IMMEDIATE) for _ in range(3)]
    rows = _synthetic_tile("incident_rate", incidents)
    total = sum(r["n"] for r in rows)
    assert total == 3


def test_geographic_equity_sectors():
    incidents = [
        _incident(Severity.IMMEDIATE, lat=35.62),   # NORTH
        _incident(Severity.MINOR, lat=35.56),        # SOUTH
        _incident(Severity.DELAYED, lat=35.59),      # CENTRAL
    ]
    rows = _synthetic_tile("geographic_equity", incidents)
    sectors = {r["sector"] for r in rows}
    assert sectors == {"NORTH", "SOUTH", "CENTRAL"}


def test_extraction_confidence_buckets():
    incidents = [
        _incident(Severity.MINOR, conf=0.95),    # high
        _incident(Severity.MINOR, conf=0.75),    # medium
        _incident(Severity.MINOR, conf=0.40),    # low
        _incident(Severity.MINOR, conf=0.95, source=IncidentSource.SIMULATED),  # ignored
    ]
    rows = _synthetic_tile("extraction_confidence", incidents)
    by_bucket = {r["bucket"]: r["n"] for r in rows}
    assert by_bucket["high"] == 1
    assert by_bucket["medium"] == 1
    assert by_bucket["low"] == 1


def test_response_time_percentiles_present():
    incidents = [_incident(Severity.IMMEDIATE) for _ in range(5)]
    rows = _synthetic_tile("response_time_percentiles", incidents)
    assert len(rows) == 1
    r = rows[0]
    assert r["severity"] == "Immediate"
    assert r["p50"] <= r["p99"]


# ── Integration: tile endpoint ──────────────────────────────────────────────

async def test_tile_endpoint_returns_in_memory_when_no_snowflake():
    state = AppState()
    app = create_app(state=state)
    await state.incidents.insert(_incident(Severity.IMMEDIATE))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/snowflake/tile/severity_distribution")
        assert r.status_code == 200
        body = r.json()
        assert body["tile"] == "severity_distribution"
        assert body["source"] == "in_memory"
        assert any(row["severity"] == "Immediate" and row["n"] == 1 for row in body["rows"])


async def test_tile_endpoint_unknown_tile_404():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/snowflake/tile/does_not_exist")
        assert r.status_code == 404


async def test_list_tiles_endpoint():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/snowflake/tiles")
        assert r.status_code == 200
        body = r.json()
        assert set(body["tiles"]) == set(TILE_QUERIES.keys())


async def test_tile_with_mock_runner_returns_snowflake_source():
    state = AppState()
    app = create_app(state=state)
    # Inject a fake runner that returns a known shape
    async def fake_runner(_sql, _params):
        return [{"severity": "Immediate", "n": 99}]
    state._sf_query_runner = fake_runner

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/snowflake/tile/severity_distribution")
        body = r.json()
        assert body["source"] == "snowflake"
        assert body["rows"] == [{"severity": "Immediate", "n": 99}]

"""Tests for Cortex incident reassessment."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

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
from disaster.snowflake.cortex_reassess import (
    parse_cortex_json,
    reassess_heuristic,
)


def _incident(description: str, *, severity: Severity = Severity.DELAYED) -> IncidentReport:
    return IncidentReport(
        id=uuid4(),
        timestamp=datetime.now(UTC),
        location=Location(lat=29.31, lng=-94.79, description=description),
        victims=[Victim(
            mobility=Mobility.UNKNOWN,
            breathing=Breathing.UNKNOWN,
            perfusion=Perfusion.UNKNOWN,
        )],
        severity=severity,
        priority_score=0.5,
        call_transcript="",
    )


def test_parse_cortex_json_valid():
    raw = '{"severity": "Immediate", "priority_score": 0.92, "reason": "trapped caller"}'
    result = parse_cortex_json(raw)
    assert result.severity == Severity.IMMEDIATE
    assert result.priority_score == 0.92
    assert "trapped" in result.reason


def test_heuristic_escalates_urgent_description():
    inc = _incident("Caller trapped, not breathing", severity=Severity.MINOR)
    result = reassess_heuristic(inc)
    assert result.severity == Severity.IMMEDIATE


async def test_reassess_endpoint_heuristic_fallback():
    state = AppState()
    inc = _incident("stable, walking with minor scratch", severity=Severity.IMMEDIATE)
    await state.incidents.insert(inc)
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/cortex/reassess/{inc.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "heuristic"
    assert body["incident"]["severity"] in {s.value for s in Severity}
    updated = await state.incidents.get(inc.id)
    assert updated is not None
    assert updated.severity.value == body["incident"]["severity"]


async def test_reassess_endpoint_uses_snowflake_runner():
    inc = _incident("crush injury, unresponsive", severity=Severity.MINOR)
    state = AppState()
    await state.incidents.insert(inc)

    async def fake_runner(sql: str, params: tuple) -> list[dict]:
        assert "CORTEX.COMPLETE" in sql
        return [{
            "RESPONSE": (
                '{"severity": "Immediate", "priority_score": 0.88, '
                '"reason": "crush and unresponsive per narrative"}'
            ),
        }]

    state._sf_query_runner = fake_runner
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/cortex/reassess/{inc.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "snowflake"
    assert body["incident"]["severity"] == "Immediate"
    assert body["incident"]["priority_score"] == 0.88
    updated = await state.incidents.get(inc.id)
    assert updated is not None
    assert updated.location.description == inc.location.description

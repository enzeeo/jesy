"""Chat API — Snowflake-off fallback path."""
from __future__ import annotations

import json
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
from disaster.snowflake.chat_backend import ChatContext, SqlGroundedCortexChatBackend


def _incident() -> IncidentReport:
    return IncidentReport(
        timestamp=datetime.now(UTC),
        location=Location(lat=29.31, lng=-94.79, description="Pier 21 flood"),
        victims=[Victim(
            mobility=Mobility.WALKING,
            breathing=Breathing.SPONTANEOUS,
            perfusion=Perfusion.NORMAL,
        )],
        severity=Severity.IMMEDIATE,
        priority_score=0.9,
    )


async def test_chat_fallback_when_snowflake_unavailable():
    state = AppState()
    await state.incidents.insert(_incident())
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sess = await ac.post("/chat/sessions", json={"scope": "global"})
        assert sess.status_code == 200
        session_id = sess.json()["session_id"]

        r = await ac.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "How many immediate incidents are open?"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["reply"]["warehouse_backed"] is False
    assert "immediate" in body["reply"]["content"].lower()
    assert body["reply"]["sources"]
    assert body["reply"]["sources"][0]["query_id"] == "in_memory_incidents"
    assert any(m["role"] == "assistant" for m in body["session"]["messages"])


async def test_chat_head_injury_in_memory():
    state = AppState()
    inc = _incident()
    inc.victims[0].injuries = ["head trauma"]
    await state.incidents.insert(inc)
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sess = await ac.post("/chat/sessions", json={"scope": "global"})
        session_id = sess.json()["session_id"]
        r = await ac.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "How many head injuries?"},
        )

    assert r.status_code == 200
    content = r.json()["reply"]["content"].lower()
    assert "head-related" in content
    assert "1 open incident" in content


async def test_chat_refuses_clinical_advice():
    state = AppState()
    app = create_app(state=state)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sess = await ac.post("/chat/sessions", json={})
        session_id = sess.json()["session_id"]
        r = await ac.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "What medication dosage should the victim take?"},
        )

    assert r.status_code == 200
    assert "cannot provide diagnosis" in r.json()["reply"]["content"].lower()


async def test_sql_chat_includes_latest_live_ops_agent_runs():
    async def fake_runner(sql: str, _params: tuple):
        if "AGENT_RUNS" in sql:
            return [{
                "RUN_ID": "ops-1",
                "AGENT_NAME": "Supervisor Agent",
                "OUTPUT_PAYLOAD": json.dumps({
                    "severity": "warning",
                    "summary": "Cluster monitor is warning; resource gap monitor is info.",
                }),
                "STARTED_AT": "2026-05-17T12:00:00+00:00",
            }]
        return []

    backend = SqlGroundedCortexChatBackend(fake_runner)
    reply = await backend.reply(
        "What is live ops seeing?",
        context=ChatContext(),
        history=[],
    )

    assert "live ops agents" in reply.content.lower()
    assert "supervisor agent warning" in reply.content.lower()
    assert any(source.query_id == "latest_agent_runs" for source in reply.sources)

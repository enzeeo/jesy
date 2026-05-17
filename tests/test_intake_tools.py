"""Integration tests for ElevenLabs server-tool endpoints under /intake/voice/."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.llm import LLMClient
from disaster.snowflake import SnowflakeWriter


def _fake_client_returning(content: str) -> LLMClient:
    async def fake(_p, _k):
        return {"content": content, "tokens": 50}
    return LLMClient(fake)


def _valid_extraction_json() -> str:
    return json.dumps({
        "location": {"lat": 19.7, "lng": -155.09, "description": "Pier 4"},
        "victims": [{
            "mobility": "cannot_follow_commands",
            "breathing": "spontaneous",
            "respiratory_rate": 32,
            "perfusion": "normal",
        }],
        "call_transcript": "caller reports trapped victim with rapid breathing",
        "confidence": 0.9,
    })


async def _make_app(*, client: LLMClient | None = None, secret: bytes | None = None):
    state = AppState()
    state.llm_client = client
    state.elevenlabs_secret = secret

    async def noop(_t, _r):
        pass

    app = create_app(snowflake_writer=SnowflakeWriter(noop, flush_interval_s=0.05), state=state)
    await state.snowflake.start()
    return app, state


def _signed(secret: bytes, body: bytes) -> dict[str, str]:
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return {"content-type": "application/json", "x-elevenlabs-signature": sig}


# ── create_incident_provisional ────────────────────────────────────────────────

async def test_provisional_builds_partial_incident_and_broadcasts():
    app, state = await _make_app()
    try:
        agen = state.events.subscribe()
        consumer = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversation_id": "conv-abc",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                    "raw_summary": "trapped",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["idempotent_replay"] is False
            assert body["incident_id"]

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "incident_created"
        assert event["data"]["status"] == "partial"
        assert event["data"]["source"] == "voice"

        assert await state.incidents.count() == 1
    finally:
        await state.snowflake.stop(0.5)


async def test_provisional_idempotent_per_conversation_id():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "conversation_id": "conv-same",
                "lat": 19.7,
                "lng": -155.09,
                "description": "Pier 4",
            }
            r1 = await ac.post("/intake/voice/tool/create_incident_provisional", json=payload)
            r2 = await ac.post("/intake/voice/tool/create_incident_provisional", json=payload)
            assert r1.status_code == 200
            assert r2.status_code == 200
            assert r1.json()["incident_id"] == r2.json()["incident_id"]
            assert r2.json()["idempotent_replay"] is True

        assert await state.incidents.count() == 1
    finally:
        await state.snowflake.stop(0.5)


async def test_provisional_accepts_camelcase_keys():
    """ElevenLabs auto-camelCases multi-word keys in tool schemas, so the agent
    sends bodies with conversationId/rawSummary. The Pydantic alias generator
    must accept these."""
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversationId": "conv-camel",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                    "rawSummary": "trapped",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["incident_id"]

        # And update_assessment with camelCase too — including nested victim.respiratoryRate
        incident_id = body["incident_id"]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r2 = await ac.post(
                "/intake/voice/tool/update_assessment",
                json={
                    "incidentId": incident_id,
                    "victim": {
                        "mobility": "cannot_follow_commands",
                        "breathing": "spontaneous",
                        "respiratoryRate": 32,
                        "perfusion": "normal",
                    },
                },
            )
            assert r2.status_code == 200, r2.text
            assert r2.json()["severity"] == "Immediate"
    finally:
        await state.snowflake.stop(0.5)


async def test_provisional_omits_caller_when_no_phone_hash():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversation_id": "c1",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                },
            )
            assert r.status_code == 200

        incident = (await state.incidents.list())[0]
        assert incident.caller is None
    finally:
        await state.snowflake.stop(0.5)


# ── update_assessment ──────────────────────────────────────────────────────────

async def test_update_assessment_runs_triage_and_publishes_severity_upgrade():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            create = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversation_id": "c-upgrade",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                },
            )
            incident_id = create.json()["incident_id"]

            # Drain the create event so we read severity_upgraded next.
            agen = state.events.subscribe()
            consumer = asyncio.create_task(agen.__anext__())
            await asyncio.sleep(0.01)

            r = await ac.post(
                "/intake/voice/tool/update_assessment",
                json={
                    "incident_id": incident_id,
                    "victim": {
                        "mobility": "cannot_follow_commands",
                        "breathing": "spontaneous",
                        "respiratory_rate": 32,
                        "perfusion": "normal",
                    },
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["severity"] == "Immediate"

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "severity_upgraded"
        assert event["data"]["previous_severity"] == "Delayed"
        assert event["data"]["severity"] == "Immediate"
    finally:
        await state.snowflake.stop(0.5)


async def test_update_assessment_unknown_id_returns_404():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/update_assessment",
                json={
                    "incident_id": str(uuid4()),
                    "victim": {"mobility": "walking"},
                },
            )
            assert r.status_code == 404
    finally:
        await state.snowflake.stop(0.5)


async def test_update_assessment_keeps_partial_when_still_incomplete():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            create = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversation_id": "c-still-partial",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                },
            )
            incident_id = create.json()["incident_id"]

            # Patch only injuries — breathing+mobility still UNKNOWN → IncompleteAssessment
            r = await ac.post(
                "/intake/voice/tool/update_assessment",
                json={
                    "incident_id": incident_id,
                    "victim": {"injuries": ["ankle pain"]},
                },
            )
            assert r.status_code == 200

        incident = await state.incidents.get(__import__("uuid").UUID(incident_id))
        assert incident.status.value == "partial"
        assert incident.victims[0].injuries == ["ankle pain"]
    finally:
        await state.snowflake.stop(0.5)


# ── query_nearby_resources (stub) ──────────────────────────────────────────────

async def test_query_nearby_resources_returns_canned_data():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/query_nearby_resources",
                json={"lat": 19.7, "lng": -155.09, "radius_km": 5.0},
            )
            assert r.status_code == 200
            body = r.json()
            assert len(body["units"]) > 0
            assert body["closest_eta_seconds"] is not None
            assert "minutes" in body["summary"]
    finally:
        await state.snowflake.stop(0.5)


async def test_query_nearby_resources_empty_when_radius_zero():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/query_nearby_resources",
                json={"lat": 19.7, "lng": -155.09, "radius_km": 0.1},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["units"] == []
            assert body["closest_eta_seconds"] is None
            assert "stay where" in body["summary"].lower()
    finally:
        await state.snowflake.stop(0.5)


# ── finalize ───────────────────────────────────────────────────────────────────

async def test_finalize_merges_into_provisional():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client=client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            create = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={
                    "conversation_id": "c-fin",
                    "lat": 19.7,
                    "lng": -155.09,
                    "description": "Pier 4",
                },
            )
            incident_id = create.json()["incident_id"]

            r = await ac.post(
                "/intake/voice/finalize",
                json={
                    "incident_id": incident_id,
                    "transcript": "victim trapped, breathing fast, cannot follow commands",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == incident_id  # same id, merged
            assert body["status"] == "new"
            assert body["severity"] == "Immediate"

        assert await state.incidents.count() == 1
    finally:
        await state.snowflake.stop(0.5)


async def test_finalize_creates_new_when_provisional_id_missing():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client=client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/finalize",
                json={
                    "incident_id": str(uuid4()),  # never existed
                    "transcript": "victim trapped, breathing fast",
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "new"

        assert await state.incidents.count() == 1
    finally:
        await state.snowflake.stop(0.5)


async def test_finalize_without_incident_id_creates_new():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client=client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/finalize",
                json={"transcript": "victim trapped, breathing fast"},
            )
            assert r.status_code == 200

        assert await state.incidents.count() == 1
    finally:
        await state.snowflake.stop(0.5)


async def test_finalize_503_when_llm_client_unset(monkeypatch):
    """Drop env so create_app() doesn't auto-wire a real OpenAI client."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app, state = await _make_app()
    assert state.llm_client is None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/finalize",
                json={"transcript": "x"},
            )
            assert r.status_code == 503
    finally:
        await state.snowflake.stop(0.5)


# ── HMAC: regression + new tool paths ──────────────────────────────────────────

async def test_tool_paths_require_hmac_when_secret_set():
    """All /intake/voice/tool/* and /intake/voice/finalize must be HMAC-gated."""
    secret = b"super-secret-key"
    app, state = await _make_app(secret=secret)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Unsigned → 401
            r = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                json={"conversation_id": "x", "lat": 19.7, "lng": -155.09, "description": "x"},
            )
            assert r.status_code == 401

            r = await ac.post(
                "/intake/voice/tool/query_nearby_resources",
                json={"lat": 19.7, "lng": -155.09},
            )
            assert r.status_code == 401
    finally:
        await state.snowflake.stop(0.5)


async def test_signed_tool_request_passes_hmac():
    secret = b"super-secret-key"
    app, state = await _make_app(secret=secret)
    try:
        body = json.dumps({
            "conversation_id": "c-signed",
            "lat": 19.7,
            "lng": -155.09,
            "description": "Pier 4",
        }).encode()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice/tool/create_incident_provisional",
                content=body,
                headers=_signed(secret, body),
            )
            assert r.status_code == 200, r.text
    finally:
        await state.snowflake.stop(0.5)


async def test_non_voice_paths_unaffected_by_hmac():
    """Regression guard: /healthz, /events, etc must NOT require HMAC after path-prefix change."""
    app, state = await _make_app(secret=b"some-secret")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/healthz")
            assert r.status_code == 200

            r = await ac.get("/responders")
            assert r.status_code == 200
    finally:
        await state.snowflake.stop(0.5)

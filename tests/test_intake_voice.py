"""Integration tests for voice intake pipeline (Phase D + HMAC middleware)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.llm import LLMClient
from disaster.snowflake import SnowflakeWriter


def _fake_client_returning(content: str) -> LLMClient:
    async def fake(_p, _k):
        return {"content": content, "tokens": 50}
    return LLMClient(fake)


def _fake_client_raising(exc: Exception) -> LLMClient:
    async def fail(_p, _k):
        raise exc
    return LLMClient(fail)


def _valid_extraction_json(transcript: str = "victim is walking") -> str:
    return json.dumps({
        "location": {"lat": 19.7, "lng": -155.09, "description": "Pier 4"},
        "victims": [{
            "mobility": "walking",
            "breathing": "spontaneous",
        }],
        "call_transcript": transcript,
        "confidence": 0.95,
    })


async def _make_app(client: LLMClient, *, secret: bytes | None = None):
    state = AppState()
    state.llm_client = client
    state.elevenlabs_secret = secret
    async def noop(_t, _r): pass
    app = create_app(snowflake_writer=SnowflakeWriter(noop, flush_interval_s=0.05), state=state)
    await state.snowflake.start()
    return app, state


# ── Happy path ───────────────────────────────────────────────────────────────

async def test_voice_intake_extracts_persists_and_broadcasts():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client)
    try:
        agen = state.events.subscribe()
        consumer = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "caller says victim is walking"})
            assert r.status_code == 201
            body = r.json()
            assert body["severity"] == "Minor"
            assert body["source"] == "voice"

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "incident_created"

        # Persisted
        assert await state.incidents.count() == 1
        # Snowflake got both rows
        # RAW submission + voice, CLEAN incident + victim(s)
        assert state.snowflake.metrics.enqueued >= 4
    finally:
        await state.snowflake.stop(0.5)


# ── Markdown-fenced JSON survives ────────────────────────────────────────────

async def test_voice_intake_handles_markdown_fenced_json():
    client = _fake_client_returning("```json\n" + _valid_extraction_json() + "\n```")
    app, state = await _make_app(client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "x"})
            assert r.status_code == 201
    finally:
        await state.snowflake.stop(0.5)


# ── Malformed JSON triggers strict retry ────────────────────────────────────

async def test_voice_intake_strict_retry_on_malformed_json():
    """First call returns prose, second call returns valid JSON."""
    calls = {"count": 0}

    async def two_phase(_p, _k):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"content": "I am sorry, I cannot do that.", "tokens": 10}
        return {"content": _valid_extraction_json(), "tokens": 50}

    client = LLMClient(two_phase)
    app, state = await _make_app(client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "x"})
            assert r.status_code == 201
            assert calls["count"] == 2
    finally:
        await state.snowflake.stop(0.5)


# ── Both backends down → 503 ────────────────────────────────────────────────

async def test_voice_intake_503_when_backends_exhausted():
    from disaster.errors import UpstreamUnavailable
    client = _fake_client_raising(UpstreamUnavailable("down"))
    app, state = await _make_app(client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "x"})
            assert r.status_code == 503
            assert "unavailable" in r.json()["detail"].lower()
    finally:
        await state.snowflake.stop(0.5)


# ── Missing transcript → 422 ─────────────────────────────────────────────────

async def test_voice_intake_missing_transcript_422():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={})
            assert r.status_code == 422
    finally:
        await state.snowflake.stop(0.5)


# ── Router unset → 503 ───────────────────────────────────────────────────────

async def test_voice_intake_503_when_router_unset(monkeypatch):
    """Drop the env so create_app() doesn't auto-wire a real OpenAI client."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    state = AppState()
    # Don't set llm_client; with no env key, create_app leaves it None.
    async def noop(_t, _r): pass
    app = create_app(snowflake_writer=SnowflakeWriter(noop, flush_interval_s=0.05), state=state)
    assert state.llm_client is None
    await state.snowflake.start()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "x"})
            assert r.status_code == 503
    finally:
        await state.snowflake.stop(0.5)


# ── HMAC middleware ──────────────────────────────────────────────────────────

async def test_hmac_rejects_unsigned_request_when_secret_set():
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client, secret=b"super-secret-key")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/intake/voice", json={"transcript": "x"})
            assert r.status_code == 401
            assert "invalid signature" in r.json()["error"].lower()
    finally:
        await state.snowflake.stop(0.5)


async def test_hmac_accepts_valid_signature():
    client = _fake_client_returning(_valid_extraction_json())
    secret = b"super-secret-key"
    app, state = await _make_app(client, secret=secret)
    try:
        body = json.dumps({"transcript": "valid"}).encode()
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice",
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-elevenlabs-signature": sig,
                },
            )
            assert r.status_code == 201
    finally:
        await state.snowflake.stop(0.5)


async def test_hmac_rejects_tampered_signature():
    client = _fake_client_returning(_valid_extraction_json())
    secret = b"super-secret-key"
    app, state = await _make_app(client, secret=secret)
    try:
        body = json.dumps({"transcript": "valid"}).encode()
        wrong_sig = hmac.new(b"wrong-key", body, hashlib.sha256).hexdigest()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/intake/voice",
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-elevenlabs-signature": wrong_sig,
                },
            )
            assert r.status_code == 401
    finally:
        await state.snowflake.stop(0.5)


async def test_hmac_middleware_does_not_affect_other_routes():
    """Only /intake/voice is HMAC-protected. Other routes work without signature."""
    client = _fake_client_returning(_valid_extraction_json())
    app, state = await _make_app(client, secret=b"some-secret")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/healthz")
            assert r.status_code == 200
    finally:
        await state.snowflake.stop(0.5)

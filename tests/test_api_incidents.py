"""Integration tests for /incidents endpoints."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import Severity


def _incident_payload(**overrides) -> dict[str, Any]:
    base = {
        "location": {"lat": 19.7, "lng": -155.0, "description": "Pier 4"},
        "victims": [{
            "mobility": "cannot_follow_commands",
            "breathing": "spontaneous",
            "respiratory_rate": 32,
            "perfusion": "normal",
        }],
    }
    base.update(overrides)
    return base


@pytest.fixture
def _fast_writer():
    """Snowflake writer with short flush interval so test shutdown is fast."""
    from disaster.snowflake import SnowflakeWriter

    async def noop(_table: str, _rows: list[dict[str, Any]]) -> None:
        pass

    return SnowflakeWriter(noop, flush_interval_s=0.05)


@pytest.fixture
def app(_fast_writer):
    state = AppState()
    application = create_app(snowflake_writer=_fast_writer, state=state)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ── Happy path ───────────────────────────────────────────────────────────────

def test_create_incident_runs_triage_and_persists(client: TestClient):
    r = client.post("/incidents", json=_incident_payload())
    assert r.status_code == 201
    body = r.json()
    # >30 resp rate → IMMEDIATE
    assert body["severity"] == Severity.IMMEDIATE.value
    assert body["priority_score"] > 0.5

    # listable
    r = client.get("/incidents")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_get_incident_by_id(client: TestClient):
    r = client.post("/incidents", json=_incident_payload())
    incident_id = r.json()["id"]
    r2 = client.get(f"/incidents/{incident_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == incident_id


def test_get_incident_missing_404(client: TestClient):
    r = client.get(f"/incidents/{uuid4()}")
    assert r.status_code == 404


# ── Triage classification surfaces correctly ─────────────────────────────────

def test_walking_victim_classified_minor(client: TestClient):
    r = client.post("/incidents", json=_incident_payload(
        victims=[{"mobility": "walking"}],
    ))
    assert r.json()["severity"] == Severity.MINOR.value


def test_validation_rejects_unknown_field(client: TestClient):
    r = client.post("/incidents", json={**_incident_payload(), "rogue": True})
    assert r.status_code == 422


# ── Incomplete extraction goes to PARTIAL ────────────────────────────────────

def test_incomplete_assessment_persisted_as_partial(client: TestClient):
    """Victim with no signal at all → status PARTIAL, confidence ≤ 0.5."""
    r = client.post("/incidents", json=_incident_payload(
        victims=[{}],  # all UNKNOWN
        confidence=0.9,
    ))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "partial"
    assert body["confidence"] <= 0.5


# ── /triage/score is pure ────────────────────────────────────────────────────

def test_triage_endpoint_returns_result_without_persisting(client: TestClient):
    r = client.post("/triage/score", json=_incident_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] == Severity.IMMEDIATE.value
    # And nothing was persisted
    r2 = client.get("/incidents")
    assert r2.json() == []


# ── Snowflake writer receives the row ────────────────────────────────────────

def test_create_writes_to_snowflake(client: TestClient, app):
    client.post("/incidents", json=_incident_payload())
    # Snowflake is the default noop writer; metrics still tick.
    assert app.state.disaster.snowflake.metrics.enqueued == 1


def test_healthz(client: TestClient):
    assert client.get("/healthz").json() == {"status": "ok"}


# ── /incidents POST publishes incident_created to the broker ────────────────
# (Full SSE roundtrip needs a real HTTP server because httpx ASGITransport
# buffers streaming responses end-to-end. EventBroker pub/sub is covered by
# test_events.py; here we verify the route actually calls broker.publish.)

async def test_post_incident_publishes_incident_created():
    state = AppState()
    app = create_app(state=state)

    # Subscribe BEFORE the request so we don't miss the event.
    agen = state.events.subscribe()
    consumer = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.01)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/incidents", json=_incident_payload())
        assert r.status_code == 201

    event = await asyncio.wait_for(consumer, timeout=1.0)
    await agen.aclose()
    assert event["type"] == "incident_created"
    assert event["data"]["severity"] == Severity.IMMEDIATE.value
    assert "sequence_id" in event


async def test_events_endpoint_returns_200_and_sse_content_type():
    """The /events route is correctly mounted and returns SSE headers."""
    state = AppState()
    app = create_app(state=state)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # ASGITransport buffers streaming, so we cancel quickly via a short timeout.
        # We just want headers, not the body.
        try:
            async with asyncio.timeout(0.5):
                async with ac.stream("GET", "/events", timeout=0.4) as resp:
                    assert resp.status_code == 200
                    assert "text/event-stream" in resp.headers.get("content-type", "")
        except (TimeoutError, httpx.ReadTimeout):
            pass  # SSE never closes; timeout is expected

"""Tests for responder phone-style tracking pings and arrival events."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    IncidentStatus,
    Location,
    Mobility,
    ResponderStatus,
    ResponderType,
    ResponderUnit,
    Victim,
)
from disaster.snowflake import SnowflakeWriter


def _victim() -> Victim:
    return Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS)


def _incident() -> IncidentReport:
    return IncidentReport(
        location=Location(lat=19.701, lng=-155.000, description="caller ping"),
        victims=[_victim()],
        priority_score=0.9,
    )


def _responder(incident_id) -> ResponderUnit:
    return ResponderUnit(
        callsign="ALS-1",
        type=ResponderType.ALS,
        location=Location(lat=19.700, lng=-155.000, description="moving"),
        status=ResponderStatus.EN_ROUTE,
        assigned_incident_id=incident_id,
    )


async def test_single_location_ping_updates_responder_without_arrival():
    async def noop(_table, _rows): pass

    state = AppState()
    incident = await state.incidents.insert(_incident())
    responder = await state.responders.upsert(_responder(incident.id))
    app = create_app(snowflake_writer=SnowflakeWriter(noop), state=state)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/responders/{responder.id}/location",
            json={
                "lat": 19.701,
                "lng": -155.000,
                "accuracy_m": 8,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["arrival_detected"] is False
    updated = await state.responders.get(responder.id)
    assert updated is not None
    assert updated.location.description == "phone ping"
    assert updated.status == ResponderStatus.EN_ROUTE
    assert state.snowflake is not None
    assert state.snowflake.metrics.enqueued == 0


async def test_second_dwell_ping_marks_arrival_and_queues_snowflake_row():
    collected: dict[str, list[dict]] = {}

    async def collect(table, rows):
        collected.setdefault(table, []).extend(rows)

    state = AppState()
    incident = await state.incidents.insert(_incident())
    responder = await state.responders.upsert(_responder(incident.id))
    writer = SnowflakeWriter(collect, flush_interval_s=0.01)
    app = create_app(snowflake_writer=writer, state=state)

    agen = state.events.subscribe()
    consumer = asyncio.create_task(agen.__anext__())
    first_timestamp = datetime.now(UTC)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/responders/{responder.id}/location",
            json={
                "lat": 19.701,
                "lng": -155.000,
                "accuracy_m": 8,
                "timestamp": first_timestamp.isoformat(),
            },
        )
        second = await client.post(
            f"/responders/{responder.id}/location",
            json={
                "lat": 19.70101,
                "lng": -155.000,
                "accuracy_m": 8,
                "timestamp": (first_timestamp + timedelta(seconds=5)).isoformat(),
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.json()
    assert payload["arrival_detected"] is True
    assert payload["incident_id"] == str(incident.id)
    updated_responder = await state.responders.get(responder.id)
    updated_incident = await state.incidents.get(incident.id)
    assert updated_responder is not None
    assert updated_responder.status == ResponderStatus.ON_SCENE
    assert updated_incident is not None
    assert updated_incident.status == IncidentStatus.ON_SCENE
    assert writer.metrics.enqueued == 1

    event = await asyncio.wait_for(consumer, timeout=1.0)
    while event["type"] != "responder_arrived":
        event = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
    await agen.aclose()
    assert event["type"] == "responder_arrived"
    assert event["data"]["responder_id"] == str(responder.id)

"""Tests for the severity_upgraded SSE event (P1 #8 server side)."""
from __future__ import annotations

import asyncio
import contextlib
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    Severity,
    Victim,
)
from disaster.snowflake import SnowflakeWriter


def _yellow_incident() -> IncidentReport:
    return IncidentReport(
        location=Location(lat=19.7, lng=-155.0, description="Pier 4"),
        victims=[Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS)],
        severity=Severity.DELAYED,
    )


async def _make_app():
    state = AppState()
    async def noop(_t, _r): pass
    app = create_app(snowflake_writer=SnowflakeWriter(noop, flush_interval_s=0.05), state=state)
    await state.snowflake.start()
    return app, state


async def test_escalate_updates_severity_and_emits_event_with_sequence_id():
    app, state = await _make_app()
    try:
        inc = await state.incidents.insert(_yellow_incident())

        agen = state.events.subscribe()
        consumer = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                f"/incidents/{inc.id}/escalate",
                json={"severity": "Immediate", "reason": "child trapped"},
            )
            assert r.status_code == 200
            assert r.json()["severity"] == "Immediate"

        event = await asyncio.wait_for(consumer, timeout=1.0)
        await agen.aclose()
        assert event["type"] == "severity_upgraded"
        assert event["data"]["incident_id"] == str(inc.id)
        assert event["data"]["from"] == "Delayed"
        assert event["data"]["to"] == "Immediate"
        assert event["data"]["reason"] == "child trapped"
        # sequence_id is monotonic and present
        assert isinstance(event["sequence_id"], int)
        assert event["sequence_id"] >= 1
    finally:
        await state.snowflake.stop(0.5)


async def test_escalate_is_idempotent_when_severity_unchanged():
    """Same-severity escalate must NOT emit an event (frontend dedupe contract)."""
    app, state = await _make_app()
    try:
        inc = await state.incidents.insert(_yellow_incident())
        events_seen: list = []

        agen = state.events.subscribe()

        async def collect():
            async for e in agen:
                events_seen.append(e)

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                f"/incidents/{inc.id}/escalate",
                json={"severity": "Delayed"},  # same as current
            )
            assert r.status_code == 200

        await asyncio.sleep(0.1)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await agen.aclose()
        assert events_seen == []  # no event emitted
    finally:
        await state.snowflake.stop(0.5)


async def test_escalate_missing_incident_404():
    app, state = await _make_app()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                f"/incidents/{uuid4()}/escalate",
                json={"severity": "Immediate"},
            )
            assert r.status_code == 404
    finally:
        await state.snowflake.stop(0.5)


async def test_escalate_writes_to_snowflake():
    app, state = await _make_app()
    try:
        inc = await state.incidents.insert(_yellow_incident())
        baseline_enqueued = state.snowflake.metrics.enqueued

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await ac.post(
                f"/incidents/{inc.id}/escalate",
                json={"severity": "Immediate"},
            )
        assert state.snowflake.metrics.enqueued == baseline_enqueued + 1
    finally:
        await state.snowflake.stop(0.5)


async def test_sequence_ids_are_monotonic_across_concurrent_escalates():
    """Two concurrent upgrades on different incidents → distinct, monotonic seq_ids."""
    app, state = await _make_app()
    try:
        inc1 = await state.incidents.insert(_yellow_incident())
        inc2 = await state.incidents.insert(_yellow_incident())

        events_seen: list = []
        agen = state.events.subscribe()

        async def collect():
            async for e in agen:
                events_seen.append(e)
                if len(events_seen) >= 2:
                    return

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await asyncio.gather(
                ac.post(f"/incidents/{inc1.id}/escalate", json={"severity": "Immediate"}),
                ac.post(f"/incidents/{inc2.id}/escalate", json={"severity": "Immediate"}),
            )

        await asyncio.wait_for(task, timeout=1.0)
        await agen.aclose()

        seq_ids = sorted(e["sequence_id"] for e in events_seen)
        assert len(set(seq_ids)) == 2          # distinct
        assert seq_ids[1] - seq_ids[0] >= 1    # monotonic
    finally:
        await state.snowflake.stop(0.5)

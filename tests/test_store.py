"""Tests for IncidentStore + ResponderStore."""
from __future__ import annotations

import pytest

from disaster.models import (
    Breathing,
    IncidentReport,
    IncidentSource,
    Location,
    Mobility,
    ResponderStatus,
    ResponderType,
    ResponderUnit,
    Victim,
)
from disaster.store import IncidentStore, ResponderStore


def _incident(*, sim_run_id: str | None = None) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=19.7, lng=-155.0, description="test"),
        victims=[Victim(mobility=Mobility.WALKING, breathing=Breathing.SPONTANEOUS)],
        source=IncidentSource.SIMULATED if sim_run_id else IncidentSource.VOICE,
        sim_run_id=sim_run_id,
    )


def _responder() -> ResponderUnit:
    return ResponderUnit(
        callsign="ALS-1",
        type=ResponderType.ALS,
        location=Location(lat=19.71, lng=-155.0, description="HQ"),
    )


# ── IncidentStore ────────────────────────────────────────────────────────────

async def test_insert_then_get():
    s = IncidentStore()
    inc = await s.insert(_incident())
    fetched = await s.get(inc.id)
    assert fetched == inc


async def test_list_returns_all():
    s = IncidentStore()
    a = await s.insert(_incident())
    b = await s.insert(_incident())
    items = await s.list()
    assert {a.id, b.id} == {i.id for i in items}


async def test_update_existing():
    s = IncidentStore()
    inc = await s.insert(_incident())
    updated = inc.model_copy(update={"call_transcript": "modified"})
    result = await s.update(updated)
    assert result.call_transcript == "modified"
    assert (await s.get(inc.id)).call_transcript == "modified"


async def test_update_missing_raises():
    s = IncidentStore()
    with pytest.raises(KeyError):
        await s.update(_incident())


# ── Simulator idempotency ────────────────────────────────────────────────────

async def test_sim_replay_is_idempotent():
    """Same (sim_run_id, external_id) inserted twice → second insert returns first."""
    s = IncidentStore()
    a = await s.insert(_incident(sim_run_id="run-1"), external_id="ext-42")
    b = await s.insert(_incident(sim_run_id="run-1"), external_id="ext-42")
    assert a.id == b.id
    assert await s.count() == 1


async def test_sim_different_external_ids_create_distinct():
    s = IncidentStore()
    a = await s.insert(_incident(sim_run_id="run-1"), external_id="ext-1")
    b = await s.insert(_incident(sim_run_id="run-1"), external_id="ext-2")
    assert a.id != b.id
    assert await s.count() == 2


async def test_sim_different_runs_create_distinct():
    s = IncidentStore()
    a = await s.insert(_incident(sim_run_id="run-1"), external_id="ext-1")
    b = await s.insert(_incident(sim_run_id="run-2"), external_id="ext-1")
    assert a.id != b.id


async def test_voice_call_not_subject_to_sim_dedupe():
    """Voice calls (no sim_run_id) always create new records."""
    s = IncidentStore()
    a = await s.insert(_incident())
    b = await s.insert(_incident())
    assert a.id != b.id


# ── ResponderStore ───────────────────────────────────────────────────────────

async def test_responder_upsert_and_get():
    s = ResponderStore()
    r = await s.upsert(_responder())
    assert (await s.get(r.id)) == r


async def test_responder_set_status_returns_updated():
    s = ResponderStore()
    r = await s.upsert(_responder())
    updated = await s.set_status(r.id, ResponderStatus.EN_ROUTE)
    assert updated.status == ResponderStatus.EN_ROUTE
    assert (await s.get(r.id)).status == ResponderStatus.EN_ROUTE


async def test_responder_set_status_missing_raises():
    s = ResponderStore()
    r = _responder()
    with pytest.raises(KeyError):
        await s.set_status(r.id, ResponderStatus.EN_ROUTE)

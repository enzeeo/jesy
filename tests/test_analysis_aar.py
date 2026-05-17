"""Tests for analysis.aar — orchestrator, cache, active-run gate."""
from __future__ import annotations

import asyncio

import pytest

from disaster.analysis.aar import AARNotFound, clear_cache, get_or_compute_aar
from disaster.app.deps import AppState
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    ResponderType,
    ResponderUnit,
    Victim,
)


def _inc(*, sim_run_id: str | None, lat: float = 19.7, lng: float = -155.0,
         priority: float = 0.5, vulns: list[str] | None = None) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=lat, lng=lng, description=f"{lat},{lng}"),
        victims=[Victim(
            mobility=Mobility.WALKING,
            breathing=Breathing.SPONTANEOUS,
            vulnerabilities=vulns or [],
        )],
        priority_score=priority,
        sim_run_id=sim_run_id,
    )


def _responder(callsign: str, lat: float = 19.7, lng: float = -155.0) -> ResponderUnit:
    return ResponderUnit(
        callsign=callsign,
        type=ResponderType.ALS,
        location=Location(lat=lat, lng=lng, description=f"{callsign} base"),
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


# ── basic shape ─────────────────────────────────────────────────────────────

async def test_get_or_compute_aar_returns_complete_response():
    state = AppState()
    for i in range(3):
        await state.incidents.insert(_inc(sim_run_id="r1", lat=19.7 + 0.01 * i))
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("r1", state)
    assert aar.sim_run_id == "r1"
    assert aar.scorecard.incident_count == 3
    assert aar.counterfactual is not None
    assert len(aar.counterfactual.policies) == 3
    assert len(aar.incidents_geo) == 3
    assert aar.data_source == "in_memory"


async def test_get_or_compute_aar_not_found_raises():
    state = AppState()
    with pytest.raises(AARNotFound):
        await get_or_compute_aar("nonexistent", state)


# ── active-run gating ──────────────────────────────────────────────────────

async def test_active_run_returns_is_live_without_counterfactual():
    state = AppState()
    state.active_sim_run_id = "live-run"
    await state.incidents.insert(_inc(sim_run_id="live-run"))
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("live-run", state)
    assert aar.is_live is True
    assert aar.badge is not None
    assert aar.counterfactual is None


async def test_past_run_includes_counterfactual():
    state = AppState()
    state.active_sim_run_id = None  # past run
    await state.incidents.insert(_inc(sim_run_id="ended-run"))
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("ended-run", state)
    assert aar.is_live is False
    assert aar.badge is None
    assert aar.counterfactual is not None


# ── cache ──────────────────────────────────────────────────────────────────

async def test_cache_hits_skip_recomputation():
    state = AppState()
    await state.incidents.insert(_inc(sim_run_id="r1"))
    await state.responders.upsert(_responder("A"))

    first = await get_or_compute_aar("r1", state)
    second = await get_or_compute_aar("r1", state)
    # Same object reference proves cache hit
    assert first is second


async def test_concurrent_requests_single_flight():
    """Two simultaneous requests for the same sim_run_id → only ONE _compute_aar runs."""
    state = AppState()
    for i in range(20):
        await state.incidents.insert(_inc(sim_run_id="r-concurrent", lat=19.7 + 0.001 * i))
    # VRP needs total capacity >= n_incidents (no disjunction penalties configured).
    # With 5 responders × capacity 5 = 25, the 20-incident problem is feasible.
    for cs in ("A", "B", "C", "D", "E"):
        await state.responders.upsert(_responder(cs))

    results = await asyncio.gather(
        get_or_compute_aar("r-concurrent", state),
        get_or_compute_aar("r-concurrent", state),
    )
    assert results[0] is results[1]  # same cached object


# ── filtering ──────────────────────────────────────────────────────────────

async def test_only_incidents_with_matching_sim_run_id_included():
    state = AppState()
    await state.incidents.insert(_inc(sim_run_id="r1", lat=19.71))
    await state.incidents.insert(_inc(sim_run_id="r2", lat=19.72))
    await state.incidents.insert(_inc(sim_run_id=None, lat=19.73))  # unattached
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("r1", state)
    assert aar.scorecard.incident_count == 1


# ── incidents_geo ──────────────────────────────────────────────────────────

async def test_incidents_geo_ordered_by_timestamp():
    state = AppState()
    incs = [_inc(sim_run_id="r1") for _ in range(3)]
    for i in incs:
        await state.incidents.insert(i)
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("r1", state)
    timestamps = [g.timestamp for g in aar.incidents_geo]
    assert timestamps == sorted(timestamps)


async def test_incidents_geo_marks_vulnerable():
    state = AppState()
    await state.incidents.insert(_inc(sim_run_id="r1", vulns=["elderly"]))
    await state.incidents.insert(_inc(sim_run_id="r1", vulns=[]))
    await state.responders.upsert(_responder("A"))

    aar = await get_or_compute_aar("r1", state)
    vuln_flags = sorted(g.has_vulnerable for g in aar.incidents_geo)
    assert vuln_flags == [False, True]

"""
Demo control endpoints. Used by the dashboard's top-bar buttons to seed state
and trigger pre-recorded voice calls without going through ElevenLabs.

  POST /demo/seed-responders     stage ALS-1, ALS-2, BLS-1 in Asheville, NC
  POST /demo/trigger-call        run a recorded transcript through /intake/voice
  POST /demo/reset               wipe in-memory state
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from disaster.errors import (
    EmptyExtraction,
    IncompleteAssessment,
    MalformedLLMResponse,
    UpstreamUnavailable,
)
from disaster.llm.extract import extract_incident
from disaster.models import (
    Breathing,
    IncidentSource,
    IncidentStatus,
    Location,
    Mobility,
    Perfusion,
    ResponderType,
    ResponderUnit,
    Victim,
)
from disaster.road_access import demo_road_access
from disaster.routing.weighted import summarize_road_access
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])

# Asheville Fire Station 1, downtown Asheville, NC
_ASHEVILLE_HQ = Location(lat=35.5951, lng=-82.5515, description="Asheville Fire Station 1")


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/seed-responders")
async def seed_responders(request: Request) -> dict[str, Any]:
    state = _state(request)
    units = [
        ResponderUnit(callsign="ALS-1", type=ResponderType.ALS, location=_ASHEVILLE_HQ),
        ResponderUnit(callsign="ALS-2", type=ResponderType.ALS,
                      location=Location(lat=35.5790, lng=-82.5930, description="West Asheville station")),
        ResponderUnit(callsign="BLS-1", type=ResponderType.BLS,
                      location=Location(lat=35.5484, lng=-82.4810, description="Oteen station")),
        ResponderUnit(callsign="FIRE-1", type=ResponderType.FIRE,
                      location=Location(lat=35.5951, lng=-82.5515, description="Asheville Fire Station 1")),
    ]
    for u in units:
        await state.responders.upsert(u)
        if state.snowflake is not None:
            from disaster.snowflake import ingest
            ingest.emit_responder(state.snowflake, u.model_dump(mode="json"))
    await state.events.publish({
        "type": "responders_seeded",
        "data": {"count": len(units)},
        "sequence_id": state.events.next_sequence_id(),
    })
    await _publish_road_access_updated(state)
    return {"seeded": [u.callsign for u in units]}


@router.post("/reset")
async def reset_state(request: Request) -> dict[str, Any]:
    """Wipe incidents + responders. For rehearsals."""
    state = _state(request)
    # IncidentStore + ResponderStore are dict-backed; mutate directly.
    state.incidents._incidents.clear()
    state.incidents._sim_index.clear()
    state.responders._units.clear()
    await state.road_access.set(demo_road_access())
    await state.events.publish({
        "type": "state_reset",
        "data": {},
        "sequence_id": state.events.next_sequence_id(),
    })
    await _publish_road_access_updated(state)
    return {"status": "reset"}


async def _publish_road_access_updated(state: AppState) -> None:
    road_access = await state.road_access.get()
    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_road_access_snapshot(state.snowflake, road_access)
    await state.events.publish({
        "type": "road_access_updated",
        "data": summarize_road_access(road_access),
        "sequence_id": state.events.next_sequence_id(),
    })


# Pre-recorded transcripts. In a real demo these come from ElevenLabs voice flow;
# /demo/trigger-call lets the presenter fire one without the cloud round-trip.
_TRANSCRIPTS: dict[str, dict[str, Any]] = {
    "biltmore_immediate": {
        "transcript": (
            "I'm calling from Biltmore Village in Asheville. The water came up fast near "
            "the Swannanoa River and one person is trapped in a storefront. They're "
            "breathing but very shallow and there's a child with them."
        ),
        "location_hint": "Biltmore Village, Asheville, NC",
    },
    "river_arts_delayed": {
        "transcript": (
            "I'm near the River Arts District in Asheville. A neighbor was hit by debris "
            "while clearing mud from the road. It looks like a broken leg. She's alert, "
            "talking to me, and she takes blood thinners."
        ),
        "location_hint": "River Arts District, Asheville, NC",
    },
    "woodfin_minor": {
        "transcript": (
            "Hi, I'm calling from Woodfin north of Asheville. A shop worker cut his "
            "hand moving storm debris. It's bleeding but he's walking around fine. "
            "Just wanted to get someone to check on him."
        ),
        "location_hint": "Woodfin, NC",
    },
}

_SCENARIO_ALIASES = {
    "west_asheville_minor": "woodfin_minor",
}


@router.post("/trigger-call")
async def trigger_call(request: Request, scenario: str = "biltmore_immediate") -> dict[str, Any]:
    """
    Fire a pre-recorded transcript through the full /intake/voice pipeline.
    Demo control; uses the real LLM extractor if configured, else a deterministic stub.
    """
    state = _state(request)
    canonical_scenario = _SCENARIO_ALIASES.get(scenario, scenario)
    if canonical_scenario not in _TRANSCRIPTS:
        raise HTTPException(status_code=404, detail=f"unknown scenario; try {list(_TRANSCRIPTS)}")

    record = _TRANSCRIPTS[canonical_scenario]
    transcript = record["transcript"]

    if state.llm_client is None:
        # Stub: skip LLM, build a plausible incident inline so the demo still flows.
        incident = _stub_extraction(canonical_scenario, transcript)
    else:
        try:
            incident = await extract_incident(state.llm_client, transcript)
        except (EmptyExtraction, MalformedLLMResponse, UpstreamUnavailable) as e:
            log.warning("trigger-call: extraction failed (%s), falling back to stub", e)
            incident = _stub_extraction(canonical_scenario, transcript)

    # Stamp active sim_run_id so demo-triggered calls are AAR-visible.
    incident = incident.model_copy(update={
        "source": IncidentSource.VOICE,
        "sim_run_id": state.active_sim_run_id,
    })

    try:
        triage = score(incident, current_time=datetime.now(UTC))
        scored = incident.with_triage(triage)
    except IncompleteAssessment:
        scored = incident.model_copy(update={
            "status": IncidentStatus.PARTIAL, "confidence": min(incident.confidence, 0.5),
        })

    persisted = await state.incidents.insert(scored, external_id=str(scored.id))
    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_incident(state.snowflake, persisted.model_dump(mode="json"))
    await state.events.publish({
        "type": "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    return {"scenario": canonical_scenario, "incident_id": str(persisted.id)}


@router.get("/scenarios")
async def list_scenarios() -> dict[str, Any]:
    return {
        "scenarios": [
            {"key": k, "location_hint": v["location_hint"], "preview": v["transcript"][:80]}
            for k, v in _TRANSCRIPTS.items()
        ],
    }


def _stub_extraction(scenario: str, transcript: str):
    """Deterministic fallback when LLM is not configured."""
    from disaster.models import IncidentReport, Severity
    scenario = _SCENARIO_ALIASES.get(scenario, scenario)
    if scenario == "biltmore_immediate":
        return IncidentReport(
            location=Location(lat=35.5745, lng=-82.5290, description="Kenilworth near Biltmore Village, Asheville, NC"),
            victims=[Victim(
                age_estimate=10, injuries=["respiratory distress", "submersion"],
                breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.POOR,
                mobility=Mobility.CANNOT_FOLLOW_COMMANDS, respiratory_rate=34,
                vulnerabilities=["child"],
            )],
            severity=Severity.IMMEDIATE, confidence=0.92, call_transcript=transcript,
        )
    if scenario == "river_arts_delayed":
        return IncidentReport(
            location=Location(lat=35.5790, lng=-82.5930, description="West Asheville near River Arts District, Asheville, NC"),
            victims=[Victim(
                age_estimate=67, injuries=["fractured leg"],
                breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.NORMAL,
                mobility=Mobility.CAN_FOLLOW_COMMANDS, respiratory_rate=18,
                vulnerabilities=["elderly", "medical_dependency"],
            )],
            severity=Severity.DELAYED, confidence=0.95, call_transcript=transcript,
        )
    # woodfin_minor
    return IncidentReport(
        location=Location(lat=35.6472, lng=-82.5607, description="Woodfin, north Asheville, NC"),
        victims=[Victim(
            age_estimate=52, injuries=["laceration"],
            breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.NORMAL,
            mobility=Mobility.WALKING, respiratory_rate=16,
            vulnerabilities=[],
        )],
        severity=Severity.MINOR, confidence=0.95, call_transcript=transcript,
    )

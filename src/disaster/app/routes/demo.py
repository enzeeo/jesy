"""
Demo control endpoints. Used by the dashboard's top-bar buttons to seed state
and trigger pre-recorded voice calls without going through ElevenLabs.

  POST /demo/seed-responders     stage ALS-1, ALS-2, BLS-1 at Hilo HQ
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
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])

# Hilo Fire Station 1: 925 Aupuni St
_HILO_HQ = Location(lat=19.7257, lng=-155.0834, description="Hilo Fire Station 1")


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/seed-responders")
async def seed_responders(request: Request) -> dict[str, Any]:
    state = _state(request)
    units = [
        ResponderUnit(callsign="ALS-1", type=ResponderType.ALS, location=_HILO_HQ),
        ResponderUnit(callsign="ALS-2", type=ResponderType.ALS,
                      location=Location(lat=19.7203, lng=-155.0773, description="Station 2")),
        ResponderUnit(callsign="BLS-1", type=ResponderType.BLS,
                      location=Location(lat=19.7330, lng=-155.0950, description="Station 3 (waterfront)")),
        ResponderUnit(callsign="FIRE-1", type=ResponderType.FIRE,
                      location=Location(lat=19.7257, lng=-155.0834, description="Hilo Fire Station 1")),
    ]
    for u in units:
        await state.responders.upsert(u)
    await state.events.publish({
        "type": "responders_seeded",
        "data": {"count": len(units)},
        "sequence_id": state.events.next_sequence_id(),
    })
    return {"seeded": [u.callsign for u in units]}


@router.post("/reset")
async def reset_state(request: Request) -> dict[str, Any]:
    """Wipe incidents + responders. For rehearsals."""
    state = _state(request)
    # IncidentStore + ResponderStore are dict-backed; mutate directly.
    state.incidents._incidents.clear()
    state.incidents._sim_index.clear()
    state.responders._units.clear()
    await state.events.publish({
        "type": "state_reset",
        "data": {},
        "sequence_id": state.events.next_sequence_id(),
    })
    return {"status": "reset"}


# Pre-recorded transcripts. In a real demo these come from ElevenLabs voice flow;
# /demo/trigger-call lets the presenter fire one without the cloud round-trip.
_TRANSCRIPTS: dict[str, dict[str, Any]] = {
    "pier4_immediate": {
        "transcript": (
            "There's been a wave at the harbor. Pier 4. I see at least one person down, "
            "they're breathing but very shallow. There's blood on the dock. I think a "
            "child got pulled in, can someone come quickly?"
        ),
        "location_hint": "Pier 4, Hilo Bay",
    },
    "banyan_delayed": {
        "transcript": (
            "I'm at the Banyan Drive hotels. There's a guest who fell down the stairs, "
            "looks like she broke her leg. She's alert, talking to me. Her name's Margaret, "
            "she's 67 and she takes blood thinners."
        ),
        "location_hint": "Banyan Drive, Hilo",
    },
    "wailoa_minor": {
        "transcript": (
            "Hi, I'm calling from Wailoa Harbor. A fisherman cut his hand on a rope. "
            "It's bleeding but he's walking around fine. Just wanted to get someone "
            "to check on him."
        ),
        "location_hint": "Wailoa Harbor",
    },
}


@router.post("/trigger-call")
async def trigger_call(request: Request, scenario: str = "pier4_immediate") -> dict[str, Any]:
    """
    Fire a pre-recorded transcript through the full /intake/voice pipeline.
    Demo control; uses the real LLM extractor if configured, else a deterministic stub.
    """
    state = _state(request)
    if scenario not in _TRANSCRIPTS:
        raise HTTPException(status_code=404, detail=f"unknown scenario; try {list(_TRANSCRIPTS)}")

    record = _TRANSCRIPTS[scenario]
    transcript = record["transcript"]

    if state.llm_client is None:
        # Stub: skip LLM, build a plausible incident inline so the demo still flows.
        incident = _stub_extraction(scenario, transcript)
    else:
        try:
            incident = await extract_incident(state.llm_client, transcript)
        except (EmptyExtraction, MalformedLLMResponse, UpstreamUnavailable) as e:
            log.warning("trigger-call: extraction failed (%s), falling back to stub", e)
            incident = _stub_extraction(scenario, transcript)

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
        state.snowflake.write("incidents", persisted.model_dump(mode="json"))
    await state.events.publish({
        "type": "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    return {"scenario": scenario, "incident_id": str(persisted.id)}


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
    if scenario == "pier4_immediate":
        return IncidentReport(
            location=Location(lat=19.7320, lng=-155.0918, description="Pier 4, Hilo Bay"),
            victims=[Victim(
                age_estimate=10, injuries=["respiratory distress", "submersion"],
                breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.POOR,
                mobility=Mobility.CANNOT_FOLLOW_COMMANDS, respiratory_rate=34,
                vulnerabilities=["child"],
            )],
            severity=Severity.DELAYED, confidence=0.92, call_transcript=transcript,
        )
    if scenario == "banyan_delayed":
        return IncidentReport(
            location=Location(lat=19.7287, lng=-155.0732, description="Banyan Drive, Hilo"),
            victims=[Victim(
                age_estimate=67, injuries=["fractured leg"],
                breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.NORMAL,
                mobility=Mobility.CAN_FOLLOW_COMMANDS, respiratory_rate=18,
                vulnerabilities=["elderly", "medical_dependency"],
            )],
            severity=Severity.DELAYED, confidence=0.95, call_transcript=transcript,
        )
    # wailoa_minor
    return IncidentReport(
        location=Location(lat=19.7233, lng=-155.0728, description="Wailoa Harbor"),
        victims=[Victim(
            age_estimate=52, injuries=["laceration"],
            breathing=Breathing.SPONTANEOUS, perfusion=Perfusion.NORMAL,
            mobility=Mobility.WALKING, respiratory_rate=16,
            vulnerabilities=[],
        )],
        severity=Severity.MINOR, confidence=0.95, call_transcript=transcript,
    )

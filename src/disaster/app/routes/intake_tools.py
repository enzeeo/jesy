"""
ElevenLabs Conversational AI server-tool endpoints.

  ┌─ ElevenLabs cloud (agent LLM) ─┐
  │  picks a tool, builds JSON args │
  └──────────────│──────────────────┘
                 │ HTTPS POST + x-elevenlabs-signature (HMAC-SHA256)
                 ▼
  ┌──────────────────────── this router ────────────────────────────┐
  │                                                                  │
  │  /intake/voice/tool/create_incident_provisional                  │
  │     idempotent on conversation_id                                │
  │     builds IncidentReport(status=PARTIAL) with default Victim    │
  │     publishes incident_created SSE → dispatcher dot appears       │
  │                                                                  │
  │  /intake/voice/tool/update_assessment                            │
  │     patches victims[0] from agent-supplied fields                │
  │     re-runs triage; publishes severity_upgraded if Δ             │
  │                                                                  │
  │  /intake/voice/tool/query_nearby_resources                       │
  │     STUB: returns canned units + ETAs for hackathon demo         │
  │     real impl wraps snowflake/tiles.py + responders.list()       │
  │                                                                  │
  │  /intake/voice/finalize                                          │
  │     merges full transcript extraction into existing provisional  │
  │     fallback: create-new when provisional id missing             │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘

All endpoints inherit HMAC verification from app.middleware (path-prefix match).
Single-caller demo scope: no per-incident locking, no concurrent-update
defense. ResearchOps would add both.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from disaster.errors import (
    EmptyExtraction,
    IncompleteAssessment,
    MalformedLLMResponse,
    UpstreamUnavailable,
)
from disaster.llm.extract import extract_incident
from disaster.models import (
    Breathing,
    Caller,
    Consciousness,
    IncidentReport,
    IncidentSource,
    IncidentStatus,
    Location,
    Mobility,
    Perfusion,
    Severity,
    Victim,
)
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/intake/voice", tags=["intake-tools"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


# ── Request schemas ────────────────────────────────────────────────────────────
#
# ElevenLabs auto-camelCases multi-word property names in tool schemas, so the
# agent sends bodies like {"conversationId": ...}. We keep snake_case on the
# Python side and accept both via Field aliases + populate_by_name=True.
# Existing tests posting snake_case still pass; real webhook bodies in camelCase
# also pass.

class _ToolBody(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CreateProvisionalBody(_ToolBody):
    conversation_id: str = Field(min_length=1, max_length=128)
    lat: float
    lng: float
    description: str = Field(min_length=1, max_length=500)
    raw_summary: str = Field(default="", max_length=2000)
    phone_hash: str | None = Field(default=None, min_length=8, max_length=128)


class VictimPatch(_ToolBody):
    """All fields optional. Only provided fields are patched into victims[0].

    Uses the same enum types as Victim so Pydantic coerces incoming strings
    ("walking", "spontaneous", …) into the right enum values — otherwise the
    pure-enum comparisons in triage.score() silently miss.
    """
    age_estimate: int | None = Field(default=None, ge=0, le=120)
    injuries: list[str] | None = Field(default=None, max_length=20)
    consciousness: Consciousness | None = None
    breathing: Breathing | None = None
    respiratory_rate: int | None = Field(default=None, ge=0, le=80)
    perfusion: Perfusion | None = None
    mobility: Mobility | None = None
    vulnerabilities: list[str] | None = Field(default=None, max_length=20)


class UpdateAssessmentBody(_ToolBody):
    incident_id: UUID
    victim: VictimPatch
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class QueryNearbyBody(_ToolBody):
    lat: float
    lng: float
    radius_km: float = Field(default=5.0, ge=0.0, le=100.0)
    incident_id: UUID | None = None


class FinalizeBody(_ToolBody):
    transcript: str = Field(min_length=1)
    incident_id: UUID | None = None


# ── Tool endpoints ─────────────────────────────────────────────────────────────

@router.post("/tool/create_incident_provisional")
async def create_incident_provisional(
    body: CreateProvisionalBody,
    request: Request,
) -> dict[str, Any]:
    """
    Agent's first tool call. Creates a placeholder incident with default UNKNOWN
    victim fields so the dispatcher dot appears immediately on the map. Subsequent
    update_assessment calls fill in the real triage data.

    Idempotent on conversation_id — agent retries return the same incident_id.
    """
    state = _state(request)

    existing = state.voice_conversations.get(body.conversation_id)
    if existing is not None:
        incident = await state.incidents.get(existing)
        if incident is not None:
            return {
                "incident_id": str(incident.id),
                "ack": "Already tracking this call. Continue gathering details.",
                "idempotent_replay": True,
            }
        # Stored id missing from store (server restart?); fall through to recreate.

    caller = (
        Caller(phone_hash=body.phone_hash, callback_available=True)
        if body.phone_hash
        else None
    )

    report = IncidentReport(
        timestamp=datetime.now(UTC),
        source=IncidentSource.VOICE,
        status=IncidentStatus.PARTIAL,
        location=Location(lat=body.lat, lng=body.lng, description=body.description),
        caller=caller,
        victims=[Victim()],
        call_transcript=body.raw_summary,
        confidence=0.3,
    )
    persisted = await state.incidents.insert(report)
    state.voice_conversations[body.conversation_id] = persisted.id

    if state.snowflake is not None:
        state.snowflake.write("incidents", persisted.model_dump(mode="json"))

    await state.events.publish({
        "type": "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    log.info("voice_tool: provisional incident %s for conversation %s",
             persisted.id, body.conversation_id)

    return {
        "incident_id": str(persisted.id),
        "ack": "Incident recorded. Help is being coordinated. "
               "Continue gathering details about injuries and mobility.",
        "idempotent_replay": False,
    }


@router.post("/tool/update_assessment")
async def update_assessment(
    body: UpdateAssessmentBody,
    request: Request,
) -> dict[str, Any]:
    """
    Patch victims[0] with any agent-supplied fields, re-run triage, broadcast
    severity_upgraded if the severity changed. Server-authoritative triage —
    agent cannot set severity directly.
    """
    state = _state(request)

    incident = await state.incidents.get(body.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")

    patch = body.victim.model_dump(exclude_unset=True, exclude_none=True)
    if not patch and body.confidence is None:
        return {
            "severity": incident.severity.value,
            "priority_score": incident.priority_score,
            "ack": "No new information provided.",
        }

    prev_severity = incident.severity
    current_victim = incident.victims[0] if incident.victims else Victim()
    patched_victim = current_victim.model_copy(update=patch)
    updated_fields: dict[str, Any] = {"victims": [patched_victim, *incident.victims[1:]]}
    if body.confidence is not None:
        updated_fields["confidence"] = body.confidence

    patched = incident.model_copy(update=updated_fields)

    try:
        triage = score(patched, current_time=datetime.now(UTC))
        scored = patched.with_triage(triage)
        scored = scored.model_copy(update={"status": IncidentStatus.NEW})
    except IncompleteAssessment as e:
        log.info("voice_tool: update_assessment still incomplete: %s", e)
        scored = patched  # stays PARTIAL with previous severity

    persisted = await state.incidents.update(scored)

    if state.snowflake is not None:
        state.snowflake.write("incidents", persisted.model_dump(mode="json"))

    if persisted.severity != prev_severity:
        await state.events.publish({
            "type": "severity_upgraded",
            "data": {
                "incident_id": str(persisted.id),
                "previous_severity": prev_severity.value,
                "severity": persisted.severity.value,
                "priority_score": persisted.priority_score,
            },
            "sequence_id": state.events.next_sequence_id(),
        })
        log.info("voice_tool: severity %s → %s for %s",
                 prev_severity, persisted.severity, persisted.id)
    else:
        await state.events.publish({
            "type": "incident_updated",
            "data": persisted.model_dump(mode="json"),
            "sequence_id": state.events.next_sequence_id(),
        })

    return {
        "severity": persisted.severity.value,
        "priority_score": persisted.priority_score,
        "ack": _ack_for_severity(persisted.severity),
    }


# Canned response payloads for query_nearby_resources. Real implementation
# would wrap snowflake/tiles.py + state.responders.list() with haversine filtering.
# Stubbed because Snowflake is optional and hackathon-scope is one demo flow.
_STUB_NEARBY_UNITS = [
    {"type": "ALS", "callsign": "ALS-2", "eta_seconds": 240, "distance_km": 1.8},
    {"type": "Fire", "callsign": "ENG-7", "eta_seconds": 360, "distance_km": 2.6},
    {"type": "Rescue", "callsign": "RES-1", "eta_seconds": 480, "distance_km": 3.4},
]


@router.post("/tool/query_nearby_resources")
async def query_nearby_resources(
    body: QueryNearbyBody,
    request: Request,
) -> dict[str, Any]:
    _ = request  # reserved for future state access; HMAC consistency
    """
    STUB: returns canned nearby units so the agent can give the caller a
    plausible answer to "is help coming?" without blocking on a real query.

    Replace _STUB_NEARBY_UNITS with run_tile()/responders.list() when wiring
    live Snowflake.
    """
    units = [u for u in _STUB_NEARBY_UNITS if u["distance_km"] <= body.radius_km]
    closest_eta_s = min((u["eta_seconds"] for u in units), default=None)

    if closest_eta_s is None:
        summary = "No units within the requested radius. Stay where it is safe."
    else:
        minutes = closest_eta_s // 60
        summary = (
            f"Closest unit is approximately {minutes} minutes out. "
            f"{len(units)} unit(s) within {body.radius_km:.0f}km."
        )

    return {
        "units": units,
        "closest_eta_seconds": closest_eta_s,
        "summary": summary,
    }


@router.post("/finalize", response_model=IncidentReport)
async def finalize(body: FinalizeBody, request: Request) -> IncidentReport:
    """
    Call-end hook. If a provisional incident exists (id supplied and found),
    merge full-transcript extraction into it. Otherwise fall back to the
    legacy /intake/voice behaviour: create a fresh incident from transcript.

    Returns the authoritative IncidentReport with status=NEW (or PARTIAL if
    triage cannot classify).
    """
    state = _state(request)

    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="llm_client not configured")

    try:
        extracted = await extract_incident(state.llm_client, body.transcript)
    except EmptyExtraction as e:
        raise HTTPException(status_code=422, detail="extraction returned no data") from e
    except MalformedLLMResponse as e:
        log.error("voice_tool finalize: malformed LLM response: %s", e)
        raise HTTPException(status_code=502, detail="LLM extraction failed") from e
    except UpstreamUnavailable as e:
        log.error("voice_tool finalize: LLM upstream down: %s", e)
        raise HTTPException(status_code=503, detail="LLM service unavailable") from e

    extracted = extracted.model_copy(update={"source": IncidentSource.VOICE})

    try:
        triage = score(extracted, current_time=datetime.now(UTC))
        scored = extracted.with_triage(triage)
        status = IncidentStatus.NEW
    except IncompleteAssessment as e:
        log.info("voice_tool finalize: incomplete assessment, persisting as PARTIAL: %s", e)
        scored = extracted
        status = IncidentStatus.PARTIAL

    if body.incident_id is not None:
        existing = await state.incidents.get(body.incident_id)
        if existing is not None:
            # Merge: keep provisional id + caller + timestamp; overlay extracted data.
            merged = existing.model_copy(update={
                "location": scored.location,
                "victims": scored.victims,
                "severity": scored.severity,
                "priority_score": scored.priority_score,
                "call_transcript": body.transcript,
                "confidence": scored.confidence,
                "status": status,
            })
            persisted = await state.incidents.update(merged)
        else:
            log.warning("voice_tool finalize: incident_id %s not found, creating new",
                        body.incident_id)
            persisted = await state.incidents.insert(
                scored.model_copy(update={"status": status, "call_transcript": body.transcript}),
                external_id=str(scored.id),
            )
    else:
        persisted = await state.incidents.insert(
            scored.model_copy(update={"status": status, "call_transcript": body.transcript}),
            external_id=str(scored.id),
        )

    if state.snowflake is not None:
        state.snowflake.write("incidents", persisted.model_dump(mode="json"))
        state.snowflake.write("voice_calls", {
            "incident_id": str(persisted.id),
            "transcript_length": len(body.transcript),
            "model": state.llm_client.metrics.model,
            "tokens": state.llm_client.metrics.total_tokens,
        })

    await state.events.publish({
        "type": "incident_updated" if body.incident_id else "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    return persisted


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ack_for_severity(severity: Severity) -> str:
    if severity == Severity.IMMEDIATE:
        return ("Acknowledged. This is being flagged as immediate priority. "
                "Stay with me and tell me anything else you can see.")
    if severity == Severity.DELAYED:
        return ("Acknowledged. Help is being arranged. "
                "Tell me if anything changes.")
    if severity == Severity.MINOR:
        return "Acknowledged. You should be okay where you are. Stay calm."
    return "Acknowledged."

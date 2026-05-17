"""
POST /intake/voice — ElevenLabs webhook entry point.

  ┌─ webhook body ─┐    ┌─ extract ─┐    ┌─ triage ─┐    ┌─ persist + broadcast ─┐
  │ {transcript,   │    │ llm_router│    │ score()   │    │ store.insert          │
  │  call_state}   │ ─▶│ extract_ │ ─▶ │ + with_   │ ─▶│ snowflake.write        │
  │                │    │  incident │    │  triage   │    │ events.publish         │
  └────────────────┘    └───────────┘    └───────────┘    └────────────────────────┘

Partial-extraction path: if triage raises IncompleteAssessment, persist with
status=PARTIAL and confidence ≤ 0.5 (still broadcasts incident_created).
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
from disaster.models import IncidentReport, IncidentSource, IncidentStatus
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/voice", response_model=IncidentReport, status_code=201)
async def voice_intake(payload: dict[str, Any], request: Request) -> IncidentReport:
    """
    Body shape (from ElevenLabs Conversational AI agent tool call):
      {
        "transcript": "<full call transcript>",
        "call_state": {...optional partial extraction...}
      }
    """
    state = _state(request)
    transcript = payload.get("transcript", "")
    if not transcript:
        raise HTTPException(status_code=422, detail="missing transcript")

    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="llm_client not configured")

    call_state = payload.get("call_state") or {}

    try:
        extracted = await extract_incident(state.llm_client, transcript, call_state=call_state)
    except EmptyExtraction as e:
        # Persist a placeholder partial so the dispatcher sees the call happened.
        log.warning("voice_intake: empty extraction: %s", e)
        raise HTTPException(status_code=422, detail="extraction returned no data") from e
    except MalformedLLMResponse as e:
        log.error("voice_intake: malformed LLM response: %s", e)
        raise HTTPException(status_code=502, detail="LLM extraction failed") from e
    except UpstreamUnavailable as e:
        log.error("voice_intake: LLM upstream down: %s", e)
        raise HTTPException(status_code=503, detail="LLM service unavailable") from e

    # Force source=voice — the agent shouldn't override this even if it tries.
    # Stamp active sim_run_id so voice intake during a demo run is AAR-visible.
    extracted = extracted.model_copy(update={
        "source": IncidentSource.VOICE,
        "sim_run_id": state.active_sim_run_id,
    })

    try:
        triage = score(extracted, current_time=datetime.now(UTC))
        scored = extracted.with_triage(triage)
    except IncompleteAssessment as e:
        log.info("voice_intake: incomplete assessment, persisting as PARTIAL: %s", e)
        scored = extracted.model_copy(update={
            "status": IncidentStatus.PARTIAL,
            "confidence": min(extracted.confidence, 0.5),
        })

    persisted = await state.incidents.insert(scored, external_id=str(scored.id))

    if state.snowflake is not None:
        from disaster.snowflake import ingest
        report = persisted.model_dump(mode="json")
        ingest.emit_incident(state.snowflake, report)
        ingest.emit_voice_call(
            state.snowflake,
            call_id=str(persisted.id),
            incident_id=str(persisted.id),
            transcript=transcript,
            model=state.llm_client.metrics.model,
            tokens=state.llm_client.metrics.total_tokens,
            payload=report,
        )

    await state.events.publish({
        "type": "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    return persisted

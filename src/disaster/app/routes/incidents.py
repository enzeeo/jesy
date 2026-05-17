"""
/incidents endpoints.

  POST /incidents              create (validates, triages, persists, broadcasts)
  GET  /incidents              list all
  GET  /incidents/{id}         single
  POST /incidents/{id}/escalate emit severity_upgraded with sequence_id (P1 #8 server)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from disaster.errors import IncompleteAssessment
from disaster.models import IncidentReport, IncidentStatus, Severity
from disaster.triage import score

if TYPE_CHECKING:
    from disaster.app.deps import AppState

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("", response_model=IncidentReport, status_code=201)
async def create_incident(report: IncidentReport, request: Request) -> IncidentReport:
    """
    Create an incident. Always runs triage (overwriting any client-provided
    severity/priority — triage is server-authoritative). Broadcasts the
    incident_created SSE event and queues a Snowflake write.
    """
    state = _state(request)

    # Stamp the active sim_run_id if the client didn't already provide one.
    # This is what makes caller-ui submissions show up in the AAR scoped by run.
    if report.sim_run_id is None and state.active_sim_run_id is not None:
        report = report.model_copy(update={"sim_run_id": state.active_sim_run_id})

    try:
        triage = score(report, current_time=datetime.now(UTC))
        scored = report.with_triage(triage)
    except IncompleteAssessment:
        # Persist as partial, do not block ingestion.
        scored = report.model_copy(update={
            "status": IncidentStatus.PARTIAL,
            "confidence": min(report.confidence, 0.5),
        })

    # external_id key used for simulator idempotency. For voice we use the
    # report's own id which is unique per call.
    external_id = report.call_transcript[:64] if report.sim_run_id else str(report.id)
    persisted = await state.incidents.insert(scored, external_id=external_id)

    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_incident(state.snowflake, persisted.model_dump(mode="json"))

    await state.events.publish({
        "type": "incident_created",
        "data": persisted.model_dump(mode="json"),
        "sequence_id": state.events.next_sequence_id(),
    })
    return persisted


@router.get("", response_model=list[IncidentReport])
async def list_incidents(request: Request) -> list[IncidentReport]:
    return await _state(request).incidents.list()


@router.get("/{incident_id}", response_model=IncidentReport)
async def get_incident(incident_id: UUID, request: Request) -> IncidentReport:
    inc = await _state(request).incidents.get(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


class EscalatePayload(BaseModel):
    severity: Severity
    reason: str = ""


@router.post("/{incident_id}/escalate", response_model=IncidentReport)
async def escalate_incident(
    incident_id: UUID, payload: EscalatePayload, request: Request,
) -> IncidentReport:
    """
    Update an incident's severity and emit a `severity_upgraded` SSE event with
    a monotonic `sequence_id` so the frontend can dedupe concurrent upgrades.

    Idempotent: a no-op if the requested severity equals the current severity.
    """
    state = _state(request)
    inc = await state.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")

    if inc.severity == payload.severity:
        return inc  # no event, no update — idempotent

    old_sev = inc.severity
    updated = inc.model_copy(update={"severity": payload.severity})
    await state.incidents.update(updated)

    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_incident(state.snowflake, updated.model_dump(mode="json"))

    await state.events.publish({
        "type": "severity_upgraded",
        "data": {
            "incident_id": str(incident_id),
            "from": old_sev.value,
            "to": payload.severity.value,
            "reason": payload.reason,
        },
        "sequence_id": state.events.next_sequence_id(),
    })
    return updated

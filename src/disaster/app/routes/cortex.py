"""Cortex endpoints: cluster scan and per-incident reassessment.

POST /cortex/scan — pattern detection, emit cortex_alert SSE on hits.
POST /cortex/reassess/{incident_id} — read narrative via Snowflake Cortex AI,
  update severity + priority_score, broadcast severity_upgraded SSE.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from disaster.snowflake.cortex import detect_clusters, detect_clusters_snowflake
from disaster.snowflake.cortex_reassess import reassess_heuristic, reassess_via_snowflake

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/cortex", tags=["cortex"])

# Throttle: at most one alert emit per N seconds.
_THROTTLE_S = 30.0


def _state(req: Request) -> AppState:
    return req.app.state.disaster


@router.post("/scan")
async def cortex_scan(request: Request) -> dict[str, Any]:
    state = _state(request)
    runner = getattr(state, "_sf_query_runner", None)

    source = "in_memory"
    alerts: list[dict[str, Any]] = []
    if runner is not None:
        try:
            alerts = await detect_clusters_snowflake(runner)
            source = "snowflake"
        except TimeoutError:
            log.warning("cortex: snowflake cluster query timed out, falling back")
        except Exception as e:  # noqa: BLE001 — connector raises diverse types
            log.warning("cortex: snowflake cluster query failed (%s), falling back", e)
    if not alerts:
        incidents = await state.incidents.list()
        alerts = detect_clusters(incidents)
        if runner is None:
            source = "in_memory"

    last = getattr(state, "_cortex_last_emit", 0.0)
    now = time.monotonic()
    emitted = []
    for alert in alerts:
        if now - last < _THROTTLE_S:
            break
        await state.events.publish({
            "type": "cortex_alert",
            "data": alert,
            "sequence_id": state.events.next_sequence_id(),
        })
        if state.snowflake is not None:
            from disaster.snowflake import ingest
            ingest.emit_cortex_alert(state.snowflake, {
                **alert,
                "severity": "warning",
                "detected_at": datetime.now(UTC),
            })
        last = now
        state._cortex_last_emit = now
        emitted.append(alert)
    return {"alerts": alerts, "emitted_count": len(emitted), "source": source}


@router.post("/reassess/{incident_id}")
async def cortex_reassess(incident_id: UUID, request: Request) -> dict[str, Any]:
    """
    Use Snowflake Cortex to re-read the incident description and assign severity
    and priority_score. Updates the in-memory store and emits severity_upgraded
    when values change. Falls back to keyword heuristics if Cortex is unavailable.
    """
    state = _state(request)
    inc = await state.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")

    runner = getattr(state, "_sf_query_runner", None)
    source = "heuristic"
    try:
        if runner is not None:
            result = await reassess_via_snowflake(runner, inc)
            source = "snowflake"
        else:
            result = reassess_heuristic(inc)
    except Exception as e:  # noqa: BLE001
        log.warning("cortex reassess: snowflake path failed (%s), using heuristic", e)
        result = reassess_heuristic(inc)
        source = "heuristic"

    old_sev = inc.severity
    old_pri = inc.priority_score
    updated = inc.model_copy(update={
        "severity": result.severity,
        "priority_score": result.priority_score,
    })
    await state.incidents.update(updated)

    if state.snowflake is not None:
        from disaster.snowflake import ingest
        ingest.emit_incident(state.snowflake, updated.model_dump(mode="json"))

    changed = old_sev != result.severity or old_pri != result.priority_score
    if changed:
        await state.events.publish({
            "type": "severity_upgraded",
            "data": {
                "incident_id": str(incident_id),
                "from": old_sev.value,
                "to": result.severity.value,
                "from_priority": old_pri,
                "to_priority": result.priority_score,
                "reason": f"cortex ({source}): {result.reason}",
            },
            "sequence_id": state.events.next_sequence_id(),
        })

    return {
        "incident": updated.model_dump(mode="json"),
        "source": source,
        "reason": result.reason,
        "changed": changed,
        "previous": {
            "severity": old_sev.value,
            "priority_score": old_pri,
        },
    }

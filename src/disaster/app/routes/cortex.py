"""POST /cortex/scan — run pattern detection, emit cortex_alert SSE on hits.

Tries the real Snowflake SQL cluster query first (when a query runner is
configured). On any failure (Snowflake down, query error), falls back to the
in-memory pattern matcher so the demo never breaks.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

from disaster.snowflake.cortex import detect_clusters, detect_clusters_snowflake

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
            state.snowflake.write("cortex_alerts", {
                "alert_type": alert["type"],
                "severity": "warning",
                "message": alert["message"],
                "detected_at": datetime.now(UTC),
            })
        last = now
        state._cortex_last_emit = now
        emitted.append(alert)
    return {"alerts": alerts, "emitted_count": len(emitted), "source": source}

"""Live Snowflake ops monitors backed by dynamic tables, with in-memory fallback."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from disaster.models import IncidentReport, ResponderUnit
from disaster.snowflake.ingest import emit_agent_run
from disaster.snowflake.tables import SCHEMA_AGENT, SCHEMA_FEATURES, SCHEMA_SERVING, database_name
from disaster.snowflake.writer import SnowflakeWriter

log = logging.getLogger(__name__)

QueryRunner = Callable[[str, tuple[Any, ...]], Awaitable[list[dict[str, Any]]]]

LIVE_OPS_AGENT_NAMES = ("Cluster Monitor", "Resource Gap Monitor", "Supervisor Agent")
LIVE_OPS_REFRESH_SECONDS = 60.0


def _table(schema: str, table: str) -> str:
    return f"{database_name()}.{schema}.{table}"


LIVE_CLUSTER_MONITOR_SQL = f"""
    SELECT
        CLUSTER_WINDOW_ID,
        H3_RES8,
        SECTOR_ID,
        WINDOW_START,
        WINDOW_END,
        OPEN_INCIDENTS,
        ACTIVE_INCIDENTS,
        IMMEDIATE_COUNT,
        DELAYED_COUNT,
        MINOR_COUNT,
        MAX_PRIORITY_SCORE,
        AVG_PRIORITY_SCORE,
        INCIDENT_IDS
    FROM {_table(SCHEMA_FEATURES, "LIVE_H3_CLUSTER_WINDOWS")}
    ORDER BY IMMEDIATE_COUNT DESC, ACTIVE_INCIDENTS DESC, MAX_PRIORITY_SCORE DESC, WINDOW_END DESC
    LIMIT 10
"""

LIVE_RESOURCE_GAP_SQL = f"""
    SELECT
        GAP_ID,
        H3_RES8,
        SECTOR_ID,
        COMPUTED_AT,
        OPEN_INCIDENTS,
        IMMEDIATE_COUNT,
        DELAYED_COUNT,
        AVAILABLE_RESPONDERS,
        GAP_SCORE,
        MAX_PRIORITY_SCORE,
        RECOMMENDATION
    FROM {_table(SCHEMA_SERVING, "LIVE_RESOURCE_GAPS")}
    ORDER BY GAP_SCORE DESC, IMMEDIATE_COUNT DESC, MAX_PRIORITY_SCORE DESC, COMPUTED_AT DESC
    LIMIT 10
"""

LATEST_AGENT_RUNS_SQL = f"""
    SELECT
        RUN_ID,
        AGENT_NAME,
        OUTPUT_PAYLOAD,
        STARTED_AT,
        ENDED_AT
    FROM {_table(SCHEMA_AGENT, "AGENT_RUNS")}
    WHERE AGENT_NAME IN ('Cluster Monitor', 'Resource Gap Monitor', 'Supervisor Agent')
    ORDER BY STARTED_AT DESC
    LIMIT 12
"""


@dataclass(frozen=True)
class OpsAgentCard:
    run_id: str
    agent_name: str
    severity: str
    title: str
    summary: str
    recommendation: str
    evidence: list[dict[str, Any]]
    timestamp: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "source": self.source,
        }


def _now_text() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append({
            (key.lower() if isinstance(key, str) else key): value
            for key, value in row.items()
        })
    return normalized_rows


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _float_value(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(row: dict[str, Any], key: str, default: int = 0) -> int:
    return int(_float_value(row, key, float(default)))


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def _sector_label(sector_id: Any) -> str:
    text = str(sector_id or "unknown").replace("_", " ").strip()
    if not text or text.lower() == "unknown":
        return "Unknown sector"
    return f"{text.title()} sector"


def _sector_from_card(card: OpsAgentCard) -> str:
    for row in card.evidence:
        sector_id = row.get("sector_id")
        if sector_id:
            return _sector_label(sector_id)
    return "Live Ops"


def _status_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _severity_rank(severity: str) -> int:
    order = {"info": 0, "warning": 1, "critical": 2}
    return order.get(severity, 0)


def _worst_severity(cards: list[OpsAgentCard]) -> str:
    if not cards:
        return "info"
    return max((card.severity for card in cards), key=_severity_rank)


def _new_run_id(agent_name: str, cycle_id: str | None = None) -> str:
    slug = agent_name.lower().replace(" ", "_")
    prefix = cycle_id or f"ops-{uuid.uuid4().hex[:12]}"
    return f"{prefix}-{slug}"[:64]


def _evidence_rows(rows: list[dict[str, Any]], keys: tuple[str, ...], limit: int = 3) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for row in rows[:limit]:
        evidence.append({key: _json_ready(row.get(key)) for key in keys if key in row})
    return evidence


def _selected_row_first(rows: list[dict[str, Any]], selected_row: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_rows = [selected_row]
    ordered_rows.extend(row for row in rows if row is not selected_row)
    return ordered_rows


def _compose_cluster_card(
    cluster_rows: list[dict[str, Any]],
    *,
    run_id: str,
    timestamp: str,
    source: str,
) -> OpsAgentCard:
    if not cluster_rows:
        return OpsAgentCard(
            run_id=run_id,
            agent_name="Cluster Monitor",
            severity="info",
            title="Cluster Monitor",
            summary="No active incident clusters need supervisor attention.",
            recommendation="Continue monitoring live incident intake.",
            evidence=[],
            timestamp=timestamp,
            source=source,
        )

    top_cluster = max(
        cluster_rows,
        key=lambda row: (
            _int_value(row, "immediate_count"),
            _int_value(row, "active_incidents"),
            _float_value(row, "max_priority_score"),
        ),
    )
    immediate_count = _int_value(top_cluster, "immediate_count")
    active_incidents = _int_value(top_cluster, "active_incidents")
    delayed_count = _int_value(top_cluster, "delayed_count")
    sector_id = top_cluster.get("sector_id") or "UNKNOWN"
    sector_label = _sector_label(sector_id)

    if immediate_count >= 3 or active_incidents >= 5:
        severity = "critical"
    elif immediate_count >= 1 or active_incidents >= 3:
        severity = "warning"
    else:
        severity = "info"

    summary = (
        f"{sector_label} has {_count_phrase(active_incidents, 'open incident')}, "
        f"including {_count_phrase(immediate_count, 'immediate incident')}"
    )
    if delayed_count:
        summary += f" and {_count_phrase(delayed_count, 'delayed incident')}"
    summary += "."

    return OpsAgentCard(
        run_id=run_id,
        agent_name="Cluster Monitor",
        severity=severity,
        title=f"Cluster Monitor: {sector_label}",
        summary=summary,
        recommendation="Review this sector before rerunning route optimization.",
        evidence=_evidence_rows(
            _selected_row_first(cluster_rows, top_cluster),
            (
                "cluster_window_id",
                "h3_res8",
                "sector_id",
                "window_end",
                "active_incidents",
                "immediate_count",
                "max_priority_score",
                "incident_ids",
            ),
        ),
        timestamp=timestamp,
        source=source,
    )


def _compose_resource_gap_card(
    gap_rows: list[dict[str, Any]],
    *,
    run_id: str,
    timestamp: str,
    source: str,
) -> OpsAgentCard:
    if not gap_rows:
        return OpsAgentCard(
            run_id=run_id,
            agent_name="Resource Gap Monitor",
            severity="info",
            title="Resource Gap Monitor",
            summary="No live sectors are reporting responder shortfalls.",
            recommendation="Keep responder coverage unchanged.",
            evidence=[],
            timestamp=timestamp,
            source=source,
        )

    top_gap = max(
        gap_rows,
        key=lambda row: (
            _float_value(row, "gap_score"),
            _int_value(row, "immediate_count"),
            _float_value(row, "max_priority_score"),
        ),
    )
    gap_score = _float_value(top_gap, "gap_score")
    immediate_count = _int_value(top_gap, "immediate_count")
    delayed_count = _int_value(top_gap, "delayed_count")
    available = _int_value(top_gap, "available_responders")
    open_incidents = _int_value(top_gap, "open_incidents")
    sector_id = top_gap.get("sector_id") or "UNKNOWN"
    sector_label = _sector_label(sector_id)

    if gap_score >= 3:
        severity = "critical"
    elif gap_score >= 1:
        severity = "warning"
    else:
        severity = "info"

    shortage_count = max(int(round(gap_score)), 0)
    if shortage_count:
        immediate_text = _count_phrase(immediate_count, "immediate incident")
        idle_text = _count_phrase(available, "idle unit")
        if delayed_count:
            demand_text = (
                f"{immediate_text}, {_count_phrase(delayed_count, 'delayed incident')}, "
                f"and {idle_text} nearby"
            )
        else:
            demand_text = f"{immediate_text} and {idle_text} nearby"
        summary = (
            f"{sector_label} is short {_count_phrase(shortage_count, 'responder')}: "
            f"{demand_text}."
        )
        recommendation = "Move available units toward this sector, then rerun route optimization."
    else:
        summary = (
            f"{sector_label} has enough idle coverage for "
            f"{_count_phrase(open_incidents, 'open incident')}."
        )
        recommendation = "Keep responder coverage unchanged."

    return OpsAgentCard(
        run_id=run_id,
        agent_name="Resource Gap Monitor",
        severity=severity,
        title=f"Resource Gap: {sector_label}",
        summary=summary,
        recommendation=recommendation,
        evidence=_evidence_rows(
            _selected_row_first(gap_rows, top_gap),
            (
                "gap_id",
                "h3_res8",
                "sector_id",
                "computed_at",
                "open_incidents",
                "immediate_count",
                "delayed_count",
                "available_responders",
                "gap_score",
            ),
        ),
        timestamp=timestamp,
        source=source,
    )


def _compose_supervisor_card(
    cluster_card: OpsAgentCard,
    gap_card: OpsAgentCard,
    *,
    run_id: str,
    timestamp: str,
    source: str,
) -> OpsAgentCard:
    severity = _worst_severity([cluster_card, gap_card])
    if severity == "critical":
        recommendation = "Prioritize supervisor review of cluster and resource-gap cards before accepting new route plans."
    elif severity == "warning":
        recommendation = "Keep the live ops strip open and rerun route optimization after any responder status change."
    else:
        recommendation = "Continue normal monitoring."

    cluster_sector = _sector_from_card(cluster_card)
    gap_sector = _sector_from_card(gap_card)
    focus_sector = gap_sector if gap_card.severity != "info" else cluster_sector
    if cluster_card.severity != "info" and gap_card.severity != "info":
        if cluster_sector == gap_sector:
            summary = f"{focus_sector} needs review: incidents are clustering and responder coverage is short."
        else:
            summary = f"{cluster_sector} has the active cluster; {gap_sector} has the responder shortfall."
    elif gap_card.severity != "info":
        summary = f"{focus_sector} needs more responder coverage."
    elif cluster_card.severity != "info":
        summary = f"{focus_sector} has the highest incident concentration."
    else:
        summary = "Live Ops is stable: no active clusters or responder gaps need supervisor attention."

    return OpsAgentCard(
        run_id=run_id,
        agent_name="Supervisor Agent",
        severity=severity,
        title="Supervisor Agent",
        summary=summary,
        recommendation=recommendation,
        evidence=[
            {
                "agent_name": cluster_card.agent_name,
                "severity": cluster_card.severity,
                "run_id": cluster_card.run_id,
            },
            {
                "agent_name": gap_card.agent_name,
                "severity": gap_card.severity,
                "run_id": gap_card.run_id,
            },
        ],
        timestamp=timestamp,
        source=source,
    )


async def build_live_ops_cards_from_snowflake(
    runner: QueryRunner,
    *,
    cycle_id: str | None = None,
) -> list[OpsAgentCard]:
    timestamp = _now_text()
    cluster_rows = _normalize_rows(await runner(LIVE_CLUSTER_MONITOR_SQL, ()))
    gap_rows = _normalize_rows(await runner(LIVE_RESOURCE_GAP_SQL, ()))
    cluster_card = _compose_cluster_card(
        cluster_rows,
        run_id=_new_run_id("Cluster Monitor", cycle_id),
        timestamp=timestamp,
        source="snowflake_dynamic",
    )
    gap_card = _compose_resource_gap_card(
        gap_rows,
        run_id=_new_run_id("Resource Gap Monitor", cycle_id),
        timestamp=timestamp,
        source="snowflake_dynamic",
    )
    supervisor_card = _compose_supervisor_card(
        cluster_card,
        gap_card,
        run_id=_new_run_id("Supervisor Agent", cycle_id),
        timestamp=timestamp,
        source="snowflake_dynamic",
    )
    return [cluster_card, gap_card, supervisor_card]


def _cards_from_agent_rows(rows: list[dict[str, Any]]) -> list[OpsAgentCard]:
    timestamp = _now_text()
    latest_by_agent: dict[str, dict[str, Any]] = {}
    for row in _normalize_rows(rows):
        agent_name = str(row.get("agent_name") or "")
        if agent_name in LIVE_OPS_AGENT_NAMES and agent_name not in latest_by_agent:
            latest_by_agent[agent_name] = row

    cards: list[OpsAgentCard] = []
    for agent_name in LIVE_OPS_AGENT_NAMES:
        row = latest_by_agent.get(agent_name)
        if not row:
            continue
        payload = _json_dict(row.get("output_payload"))
        if not payload:
            continue
        summary = str(payload.get("summary") or "")
        recommendation = str(payload.get("recommendation") or "")
        visible_copy = f"{summary} {recommendation}".lower()
        if "h3 cell" in visible_copy or "gap score" in visible_copy:
            continue
        evidence_value = payload.get("evidence")
        evidence = evidence_value if isinstance(evidence_value, list) else []
        cards.append(OpsAgentCard(
            run_id=str(row.get("run_id") or _new_run_id(agent_name)),
            agent_name=agent_name,
            severity=str(payload.get("severity") or "info"),
            title=str(payload.get("title") or agent_name),
            summary=summary,
            recommendation=recommendation,
            evidence=[item for item in evidence if isinstance(item, dict)],
            timestamp=_timestamp_text(row.get("ended_at") or row.get("started_at"), timestamp),
            source="snowflake",
        ))
    return cards


def _sector_for_lat(lat: float) -> str:
    if lat > 35.61:
        return "NORTH"
    if lat < 35.57:
        return "SOUTH"
    return "CENTRAL"


def build_fallback_live_ops_cards(
    *,
    incidents: list[IncidentReport],
    responders: list[ResponderUnit],
) -> list[OpsAgentCard]:
    timestamp = _now_text()
    cycle_id = f"ops-{uuid.uuid4().hex[:12]}"
    open_statuses = {"new", "dispatched", "en_route", "partial"}
    open_incidents = [
        incident
        for incident in incidents
        if _status_value(incident.status) in open_statuses
    ]

    incidents_by_sector: dict[str, list[IncidentReport]] = defaultdict(list)
    for incident in open_incidents:
        incidents_by_sector[_sector_for_lat(incident.location.lat)].append(incident)

    cluster_rows: list[dict[str, Any]] = []
    for sector_id, sector_incidents in incidents_by_sector.items():
        immediate_count = sum(1 for incident in sector_incidents if _status_value(incident.severity) == "Immediate")
        cluster_rows.append({
            "cluster_window_id": f"in_memory:{sector_id}",
            "h3_res8": "in_memory",
            "sector_id": sector_id,
            "window_end": timestamp,
            "active_incidents": len(sector_incidents),
            "immediate_count": immediate_count,
            "max_priority_score": max((incident.priority_score for incident in sector_incidents), default=0.0),
            "incident_ids": ",".join(str(incident.id) for incident in sector_incidents[:5]),
        })

    idle_responders_by_sector: dict[str, int] = defaultdict(int)
    for responder in responders:
        if _status_value(responder.status) == "idle":
            idle_responders_by_sector[_sector_for_lat(responder.location.lat)] += 1

    gap_rows: list[dict[str, Any]] = []
    for sector_id, sector_incidents in incidents_by_sector.items():
        immediate_count = sum(1 for incident in sector_incidents if _status_value(incident.severity) == "Immediate")
        delayed_count = sum(1 for incident in sector_incidents if _status_value(incident.severity) == "Delayed")
        available = idle_responders_by_sector.get(sector_id, 0)
        gap_score = max((immediate_count + delayed_count) - available, 0)
        gap_rows.append({
            "gap_id": f"in_memory:{sector_id}",
            "h3_res8": "in_memory",
            "sector_id": sector_id,
            "computed_at": timestamp,
            "open_incidents": len(sector_incidents),
            "immediate_count": immediate_count,
            "delayed_count": delayed_count,
            "available_responders": available,
            "gap_score": gap_score,
            "max_priority_score": max((incident.priority_score for incident in sector_incidents), default=0.0),
            "recommendation": "Review nearby idle units and rerun route optimization." if gap_score else "Coverage acceptable.",
        })

    cluster_card = _compose_cluster_card(
        cluster_rows,
        run_id=_new_run_id("Cluster Monitor", cycle_id),
        timestamp=timestamp,
        source="in_memory",
    )
    gap_card = _compose_resource_gap_card(
        gap_rows,
        run_id=_new_run_id("Resource Gap Monitor", cycle_id),
        timestamp=timestamp,
        source="in_memory",
    )
    supervisor_card = _compose_supervisor_card(
        cluster_card,
        gap_card,
        run_id=_new_run_id("Supervisor Agent", cycle_id),
        timestamp=timestamp,
        source="in_memory",
    )
    return [cluster_card, gap_card, supervisor_card]


async def latest_ops_cards(
    *,
    runner: QueryRunner | None,
    fallback_incidents: list[IncidentReport],
    fallback_responders: list[ResponderUnit],
) -> dict[str, Any]:
    generated_at = _now_text()
    if runner is not None:
        try:
            cards = await build_live_ops_cards_from_snowflake(runner)
            return {
                "source": "snowflake_dynamic",
                "generated_at": generated_at,
                "cards": [card.to_dict() for card in cards],
            }
        except Exception as error:  # noqa: BLE001
            log.warning("live_ops: dynamic table query failed (%s)", error)

        try:
            rows = await runner(LATEST_AGENT_RUNS_SQL, ())
            cards = _cards_from_agent_rows(rows)
            if cards:
                return {
                    "source": "snowflake",
                    "generated_at": generated_at,
                    "cards": [card.to_dict() for card in cards],
                }
        except Exception as error:  # noqa: BLE001
            log.warning("live_ops: latest AGENT_RUNS query failed (%s), using in-memory fallback", error)

    fallback_cards = build_fallback_live_ops_cards(
        incidents=fallback_incidents,
        responders=fallback_responders,
    )
    return {
        "source": "in_memory",
        "generated_at": generated_at,
        "cards": [card.to_dict() for card in fallback_cards],
    }


async def run_live_ops_agents(
    *,
    runner: QueryRunner,
    writer: SnowflakeWriter,
) -> list[OpsAgentCard]:
    started_at = datetime.now(UTC)
    cycle_id = f"ops-{uuid.uuid4().hex[:12]}"
    try:
        cards = await build_live_ops_cards_from_snowflake(runner, cycle_id=cycle_id)
    except Exception as error:  # noqa: BLE001
        log.warning("live_ops: scheduler skipped run (%s)", error)
        return []

    ended_at = datetime.now(UTC)
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)
    for card in cards:
        emit_agent_run(
            writer,
            run_id=card.run_id,
            agent_name=card.agent_name,
            input_payload={
                "source": "snowflake_dynamic_tables",
                "target_lag": "1 minute",
            },
            output_payload={
                "severity": card.severity,
                "title": card.title,
                "summary": card.summary,
                "recommendation": card.recommendation,
                "evidence": card.evidence,
                "source": card.source,
            },
            started_at=started_at,
            ended_at=ended_at,
            latency_ms=latency_ms,
        )
    return cards


class LiveOpsScheduler:
    """Minute loop for app-managed ops agents."""

    def __init__(
        self,
        *,
        runner: QueryRunner,
        writer: SnowflakeWriter,
        interval_seconds: float = LIVE_OPS_REFRESH_SECONDS,
    ) -> None:
        self._runner = runner
        self._writer = writer
        self._interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._run_in_progress = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="live-ops-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> list[OpsAgentCard]:
        if self._run_in_progress:
            return []
        self._run_in_progress = True
        try:
            return await run_live_ops_agents(runner=self._runner, writer=self._writer)
        finally:
            self._run_in_progress = False

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue

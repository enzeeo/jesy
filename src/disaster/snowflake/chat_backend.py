"""
Cortex-style dispatch chat backends.

SqlGroundedCortexChatBackend runs read-only warehouse queries (see chat_queries.py)
and composes answers from result rows. InMemoryCortexChatBackend degrades when
Snowflake is unavailable.

TODO: add native Snowflake Cortex Agent path (CORTEX.COMPLETE / Agent API) that
orchestrates tool calls instead of fixed query plans.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from disaster.models import IncidentReport, IncidentStatus, ResponderUnit
from disaster.snowflake.chat_queries import build_chat_query_plan, query_params, wants_head_injury_stats
from disaster.snowflake.tables import SCHEMA_CLEAN, database_name

log = logging.getLogger(__name__)

QueryRunner = Callable[[str, tuple[Any, ...]], Awaitable[list[dict[str, Any]]]]

_CLINICAL_PATTERN = re.compile(
    r"\b(diagnos(e|is|ing)?|treat(ment)?|prescri(be|ption)?|dosage|"
    r"medication\s+advice|what\s+drug|surgery\s+plan)\b",
    re.IGNORECASE,
)

_GUARDRAIL_REFUSAL = (
    "I can only support responder dispatch operations — triage priority, unit status, "
    "sector workload, and routing. I cannot provide diagnosis, treatment plans, or "
    "clinical advice to victims or callers."
)


@dataclass(frozen=True)
class ChatContext:
    incident_id: str | None = None
    sector: str | None = None
    cluster_id: str | None = None


@dataclass(frozen=True)
class ChatSource:
    query_id: str
    tables: list[str]
    row_count: int


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class ChatReply:
    content: str
    sources: list[ChatSource] = field(default_factory=list)
    warehouse_backed: bool = True


class CortexChatBackend(Protocol):
    async def reply(
        self,
        message: str,
        *,
        context: ChatContext,
        history: list[ChatTurn],
    ) -> ChatReply: ...


def check_guardrails(message: str) -> str | None:
    """Return refusal text if message requests clinical advice; else None."""
    if _CLINICAL_PATTERN.search(message):
        return _GUARDRAIL_REFUSAL
    return None


def _norm_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for k, v in row.items():
            key = k.lower() if isinstance(k, str) else k
            if hasattr(v, "isoformat"):
                normalized[key] = v.isoformat()
            else:
                normalized[key] = v
        out.append(normalized)
    return out


_OPEN_STATUSES = frozenset({
    IncidentStatus.NEW,
    IncidentStatus.DISPATCHED,
    IncidentStatus.EN_ROUTE,
    IncidentStatus.PARTIAL,
})

_HEAD_INJURY_TERMS = ("head", "cranial", "skull")


def _victim_has_head_injury(victim: Any) -> bool:
    injuries = getattr(victim, "injuries", None) or []
    for inj in injuries:
        lower = str(inj).lower()
        if any(term in lower for term in _HEAD_INJURY_TERMS):
            return True
    return False


def _incident_has_head_injury(incident: IncidentReport) -> bool:
    return any(_victim_has_head_injury(v) for v in incident.victims)


def _compose_from_warehouse(
    message: str,
    results: dict[str, list[dict[str, Any]]],
    *,
    context: ChatContext,
) -> str:
    ctx_bits: list[str] = []
    if context.incident_id:
        ctx_bits.append(f"incident {context.incident_id[:8]}…")
    if context.sector:
        ctx_bits.append(f"sector {context.sector.upper()}")
    if context.cluster_id:
        ctx_bits.append(f"cluster {context.cluster_id[:12]}…")
    ctx_prefix = f"Context: {', '.join(ctx_bits)}. " if ctx_bits else ""

    if wants_head_injury_stats(message):
        head_rows = results.get("head_injury_open_incidents") or []
        n = int((head_rows[0].get("n") if head_rows else 0) or 0)
        scope = f" in {context.sector.upper()}" if context.sector else ""
        noun = "incident" if n == 1 else "incidents"
        return (
            f"{ctx_prefix}{n} open {noun} with head-related injuries in the last 6 hours{scope}."
        ).strip()

    parts: list[str] = []
    if ctx_bits:
        parts.append(f"Context: {', '.join(ctx_bits)}.")

    sev = results.get("open_incidents_by_severity") or []
    if sev:
        counts = ", ".join(f"{r.get('severity', r.get('SEVERITY'))}: {r.get('n', r.get('N'))}" for r in sev)
        parts.append(f"Open incidents by severity (last 6h): {counts}.")

    recent = results.get("recent_incidents") or []
    if recent:
        top = recent[0]
        parts.append(
            f"Highest-priority recent incident: {top.get('severity')} "
            f"(score {float(top.get('priority_score', 0)):.2f}) — "
            f"{str(top.get('incident_description', ''))[:120]}."
        )
        if len(recent) > 1:
            parts.append(f"{len(recent)} incidents in the last 2 hours.")

    detail = results.get("incident_detail") or []
    if detail:
        d = detail[0]
        parts.append(
            f"Focused incident {d.get('incident_id')}: {d.get('severity')} / {d.get('status')} "
            f"priority {float(d.get('priority_score', 0)):.2f}. "
            f"{d.get('incident_description')}."
        )
        inj = d.get("injuries") or d.get("INJURIES")
        if inj:
            parts.append(f"Victim injuries: {inj}.")

    sector_rows = results.get("sector_open_incidents") or []
    if sector_rows:
        parts.append(f"{len(sector_rows)} open incidents in sector {context.sector}.")

    dispatches = results.get("active_dispatches") or []
    if dispatches:
        parts.append(f"{len(dispatches)} active responder dispatches.")

    gaps = results.get("resource_gap_by_sector") or []
    if gaps:
        g = gaps[0]
        parts.append(
            f"Top resource gap: sector {g.get('sector_id')} gap_score {g.get('gap_score')} "
            f"({g.get('open_immediate')} immediate open, {g.get('available_responders')} units)."
        )

    alerts = results.get("recent_cortex_alerts") or []
    if alerts:
        a = alerts[0]
        parts.append(f"Latest Cortex alert: {a.get('message', '')[:160]}")

    cluster = results.get("cluster_row") or []
    if cluster:
        c = cluster[0]
        parts.append(
            f"Cluster {c.get('cluster_id')}: demand {c.get('demand_count')}, "
            f"priority {c.get('priority_score')}."
        )

    if not parts:
        parts.append("No matching data for the current filters.")

    lower = message.lower()
    if "eta" in lower or "dispatch" in lower:
        if dispatches:
            etas = [r.get("eta_seconds") for r in dispatches if r.get("eta_seconds") is not None]
            if etas:
                parts.append(f"Dispatch ETAs (seconds): min {min(etas):.0f}, max {max(etas):.0f}.")
        else:
            parts.append("No active dispatch ETAs in the last 6 hours.")

    return " ".join(parts)


class SqlGroundedCortexChatBackend:
    """Answers grounded on live Snowflake query results."""

    def __init__(self, runner: QueryRunner) -> None:
        self._runner = runner

    async def reply(
        self,
        message: str,
        *,
        context: ChatContext,
        history: list[ChatTurn],
    ) -> ChatReply:
        refusal = check_guardrails(message)
        if refusal:
            return ChatReply(content=refusal, sources=[], warehouse_backed=True)

        plan = build_chat_query_plan(
            incident_id=context.incident_id,
            sector=context.sector,
            cluster_id=context.cluster_id,
            message=message,
        )
        results: dict[str, list[dict[str, Any]]] = {}
        sources: list[ChatSource] = []

        for spec in plan:
            params = query_params(
                spec,
                incident_id=context.incident_id,
                sector=context.sector,
                cluster_id=context.cluster_id,
            )
            try:
                rows = await self._runner(spec.sql, params)
                results[spec.query_id] = _norm_rows(rows)
                sources.append(ChatSource(
                    query_id=spec.query_id,
                    tables=list(spec.tables),
                    row_count=len(rows),
                ))
            except Exception as e:  # noqa: BLE001
                log.warning("chat: query %s failed: %s", spec.query_id, e)
                results[spec.query_id] = []
                sources.append(ChatSource(
                    query_id=spec.query_id,
                    tables=list(spec.tables),
                    row_count=0,
                ))

        content = _compose_from_warehouse(message, results, context=context)
        if history:
            last_user = next((t.content for t in reversed(history) if t.role == "user"), "")
            if last_user and last_user != message:
                content = f"Follow-up to prior question. {content}"

        return ChatReply(content=content, sources=sources, warehouse_backed=True)


class InMemoryCortexChatBackend:
    """Fallback when Snowflake query runner is unavailable."""

    def __init__(
        self,
        *,
        incidents: list[IncidentReport],
        responders: list[ResponderUnit],
    ) -> None:
        self._incidents = incidents
        self._responders = responders

    def _sector(self, lat: float) -> str:
        if lat > 29.31:
            return "NORTH"
        if lat < 29.29:
            return "SOUTH"
        return "CENTRAL"

    async def reply(
        self,
        message: str,
        *,
        context: ChatContext,
        history: list[ChatTurn],
    ) -> ChatReply:
        refusal = check_guardrails(message)
        if refusal:
            return ChatReply(content=refusal, sources=[], warehouse_backed=False)

        incidents = list(self._incidents)
        if context.incident_id:
            incidents = [i for i in incidents if str(i.id) == context.incident_id]
        if context.sector:
            sec = context.sector.strip().upper()
            incidents = [i for i in incidents if self._sector(i.location.lat) == sec]

        open_incidents = [i for i in incidents if i.status in _OPEN_STATUSES]

        ctx_bits: list[str] = []
        if context.incident_id:
            ctx_bits.append(f"incident {context.incident_id[:8]}…")
        if context.sector:
            ctx_bits.append(f"sector {context.sector.upper()}")
        if context.cluster_id:
            ctx_bits.append(f"cluster {context.cluster_id[:12]}…")
        ctx_prefix = f"Context: {', '.join(ctx_bits)}. " if ctx_bits else ""

        if wants_head_injury_stats(message):
            n = sum(1 for i in open_incidents if _incident_has_head_injury(i))
            scope = f" in {context.sector.upper()}" if context.sector else ""
            noun = "incident" if n == 1 else "incidents"
            return ChatReply(
                content=(
                    f"{ctx_prefix}{n} open {noun} with head-related injuries{scope}."
                ).strip(),
                sources=[ChatSource(query_id="in_memory_incidents", tables=["in_memory"], row_count=n)],
                warehouse_backed=False,
            )

        by_sev: dict[str, int] = {}
        for inc in open_incidents:
            by_sev[inc.severity.value] = by_sev.get(inc.severity.value, 0) + 1

        parts: list[str] = []
        if ctx_bits:
            parts.append(f"Context: {', '.join(ctx_bits)}.")

        if by_sev:
            parts.append(
                "Open incidents by severity: "
                + ", ".join(f"{k}: {v}" for k, v in sorted(by_sev.items())),
            )
        else:
            parts.append("No matching open incidents.")

        if open_incidents:
            top = max(open_incidents, key=lambda i: i.priority_score)
            parts.append(
                f"Top priority: {top.severity.value} ({top.priority_score:.2f}) — "
                f"{top.location.description[:100]}."
            )

        idle = sum(1 for r in self._responders if r.status == "idle")
        parts.append(f"Responders: {len(self._responders)} total, {idle} idle.")

        if context.cluster_id:
            parts.append("Cluster detail is not available without Snowflake.")

        return ChatReply(
            content=" ".join(parts),
            sources=[ChatSource(query_id="in_memory_incidents", tables=["in_memory"], row_count=len(incidents))],
            warehouse_backed=False,
        )


async def build_chat_backend(
    runner: QueryRunner | None,
    *,
    get_incidents: Callable[[], Awaitable[list[IncidentReport]]],
    get_responders: Callable[[], Awaitable[list[ResponderUnit]]],
) -> CortexChatBackend:
    """
    Prefer SQL-grounded backend when runner is present; verify with a lightweight probe.
    """
    if runner is None:
        incidents = await get_incidents()
        responders = await get_responders()
        return InMemoryCortexChatBackend(incidents=incidents, responders=responders)

    try:
        probe = _t_probe_sql()
        await runner(probe, ())
        return SqlGroundedCortexChatBackend(runner)
    except Exception as e:  # noqa: BLE001
        log.warning("chat: snowflake probe failed (%s), using in-memory backend", e)
        incidents = await get_incidents()
        responders = await get_responders()
        return InMemoryCortexChatBackend(incidents=incidents, responders=responders)


def _t_probe_sql() -> str:
    incidents = f"{database_name()}.{SCHEMA_CLEAN}.INCIDENTS"
    return f"SELECT COUNT(*) AS N FROM {incidents} WHERE TIMESTAMP > DATEADD(day, -7, CURRENT_TIMESTAMP())"



"""
Read-only Snowflake queries for dispatch-console chat.

Each entry is a named, auditable SQL fragment against DISASTER_DB layered schemas
(RAW / CLEAN / FEATURES / SERVING). Context filters are applied via bind params.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from disaster.snowflake.tables import SCHEMA_CLEAN, SCHEMA_FEATURES, SCHEMA_SERVING


def _db() -> str:
    return os.environ.get("SNOWFLAKE_DATABASE", "DISASTER_DB")


def _t(schema: str, table: str) -> str:
    return f"{_db()}.{schema}.{table}"


@dataclass(frozen=True)
class ChatQuerySpec:
    query_id: str
    tables: tuple[str, ...]
    sql: str
  # params filled by caller


def _sector_case(lat_col: str = "LAT") -> str:
    return f"""CASE
        WHEN {lat_col} > 29.31 THEN 'NORTH'
        WHEN {lat_col} < 29.29 THEN 'SOUTH'
        ELSE 'CENTRAL'
    END"""


def wants_head_injury_stats(message: str) -> bool:
    lower = message.lower()
    if any(k in lower for k in ("head injur", "head trauma", "head wound", "cranial", "skull")):
        return True
    return "head" in lower and any(k in lower for k in ("injur", "trauma", "wound", "how many"))


def build_chat_query_plan(
    *,
    incident_id: str | None = None,
    sector: str | None = None,
    cluster_id: str | None = None,
    sim_run_id: str | None = None,
    message: str | None = None,
) -> list[ChatQuerySpec]:
    """Select read-only queries for the current chat context.

    When sim_run_id is provided, queries on CLEAN.INCIDENTS scope to that
    run so chat numbers track the live demo instead of accumulated test
    data from prior sim runs. Pass None to query across all runs (the
    historical behavior) — useful when no sim is active or for ad-hoc
    cross-run analysis.
    """
    incidents = _t(SCHEMA_CLEAN, "INCIDENTS")
    victims = _t(SCHEMA_CLEAN, "VICTIMS")
    dispatches = _t(SCHEMA_SERVING, "RESPONDER_DISPATCHES")
    alerts = _t(SCHEMA_SERVING, "CORTEX_ALERTS")
    resource_gap = _t(SCHEMA_FEATURES, "RESOURCE_GAP")
    clusters = _t(SCHEMA_CLEAN, "CLUSTERS")

    # SIM_RUN_ID lives on CLEAN.INCIDENTS only. For queries on that table,
    # append the filter directly; for joined queries, filter via the joined
    # incidents alias.
    sim_filter_incidents = " AND SIM_RUN_ID = %s" if sim_run_id else ""
    sim_filter_i_alias = " AND i.SIM_RUN_ID = %s" if sim_run_id else ""

    plan: list[ChatQuerySpec] = [
        ChatQuerySpec(
            query_id="open_incidents_by_severity",
            tables=(f"{SCHEMA_CLEAN}.INCIDENTS",),
            sql=f"""
                SELECT SEVERITY, COUNT(*) AS N
                FROM {incidents}
                WHERE STATUS IN ('new', 'dispatched', 'en_route', 'partial')
                  AND TIMESTAMP > DATEADD(hour, -6, CURRENT_TIMESTAMP())
                  {sim_filter_incidents}
                GROUP BY SEVERITY
                ORDER BY N DESC
            """,
        ),
        ChatQuerySpec(
            query_id="recent_incidents",
            tables=(f"{SCHEMA_CLEAN}.INCIDENTS",),
            sql=f"""
                SELECT INCIDENT_ID, SEVERITY, PRIORITY_SCORE, STATUS,
                       INCIDENT_DESCRIPTION, TIMESTAMP
                FROM {incidents}
                WHERE TIMESTAMP > DATEADD(hour, -2, CURRENT_TIMESTAMP())
                  {sim_filter_incidents}
                ORDER BY PRIORITY_SCORE DESC
                LIMIT 15
            """,
        ),
        ChatQuerySpec(
            query_id="active_dispatches",
            tables=(f"{SCHEMA_SERVING}.RESPONDER_DISPATCHES", f"{SCHEMA_CLEAN}.INCIDENTS"),
            sql=f"""
                SELECT d.RESPONDER_ID, d.INCIDENT_ID, d.STATUS, d.ETA_SECONDS,
                       d.DISTANCE_KM, i.SEVERITY, i.INCIDENT_DESCRIPTION
                FROM {dispatches} d
                LEFT JOIN {incidents} i ON d.INCIDENT_ID = i.INCIDENT_ID
                WHERE d.STARTED_AT > DATEADD(hour, -6, CURRENT_TIMESTAMP())
                  {sim_filter_i_alias}
                ORDER BY d.STARTED_AT DESC
                LIMIT 20
            """,
        ),
        ChatQuerySpec(
            query_id="resource_gap_by_sector",
            tables=(f"{SCHEMA_FEATURES}.RESOURCE_GAP",),
            sql=f"""
                SELECT SECTOR_ID, OPEN_IMMEDIATE, OPEN_DELAYED,
                       AVAILABLE_RESPONDERS, GAP_SCORE, COMPUTED_AT
                FROM {resource_gap}
                WHERE COMPUTED_AT > DATEADD(hour, -2, CURRENT_TIMESTAMP())
                ORDER BY GAP_SCORE DESC
                LIMIT 10
            """,
        ),
        ChatQuerySpec(
            query_id="recent_cortex_alerts",
            tables=(f"{SCHEMA_SERVING}.CORTEX_ALERTS",),
            sql=f"""
                SELECT ALERT_TYPE, SEVERITY, SECTOR_ID, MESSAGE, DETECTED_AT
                FROM {alerts}
                WHERE DETECTED_AT > DATEADD(hour, -6, CURRENT_TIMESTAMP())
                ORDER BY DETECTED_AT DESC
                LIMIT 10
            """,
        ),
    ]

    if incident_id:
        plan.append(ChatQuerySpec(
            query_id="incident_detail",
            tables=(f"{SCHEMA_CLEAN}.INCIDENTS", f"{SCHEMA_CLEAN}.VICTIMS"),
            sql=f"""
                SELECT i.INCIDENT_ID, i.SEVERITY, i.PRIORITY_SCORE, i.STATUS,
                       i.INCIDENT_DESCRIPTION, i.TIMESTAMP, i.LAT, i.LNG,
                       v.VICTIM_ORDINAL, v.INJURIES, v.VULNERABILITIES, v.CONSCIOUSNESS
                FROM {incidents} i
                LEFT JOIN {victims} v
                  ON i.INCIDENT_ID = v.INCIDENT_ID AND v.VICTIM_ORDINAL = 1
                WHERE i.INCIDENT_ID = %s
            """,
        ))

    if sector:
        plan.append(ChatQuerySpec(
            query_id="sector_open_incidents",
            tables=(f"{SCHEMA_CLEAN}.INCIDENTS",),
            sql=f"""
                SELECT INCIDENT_ID, SEVERITY, PRIORITY_SCORE, STATUS,
                       INCIDENT_DESCRIPTION, TIMESTAMP
                FROM {incidents}
                WHERE {_sector_case()} = %s
                  AND STATUS IN ('new', 'dispatched', 'en_route', 'partial')
                  AND TIMESTAMP > DATEADD(hour, -6, CURRENT_TIMESTAMP())
                  {sim_filter_incidents}
                ORDER BY PRIORITY_SCORE DESC
                LIMIT 20
            """,
        ))

    if cluster_id:
        plan.append(ChatQuerySpec(
            query_id="cluster_row",
            tables=(f"{SCHEMA_CLEAN}.CLUSTERS",),
            sql=f"""
                SELECT CLUSTER_ID, LAT, LNG, LOCATION_DESCRIPTION, PRIORITY_SCORE,
                       DEMAND_COUNT, MEMBER_INCIDENT_IDS, CLUSTER_METHOD, CREATED_AT
                FROM {clusters}
                WHERE CLUSTER_ID = %s
                LIMIT 1
            """,
        ))

    if message and wants_head_injury_stats(message):
        injury_filter = """
              AND (
                ARRAY_TO_STRING(v.INJURIES, ',') ILIKE '%head%'
                OR ARRAY_TO_STRING(v.INJURIES, ',') ILIKE '%cranial%'
                OR ARRAY_TO_STRING(v.INJURIES, ',') ILIKE '%skull%'
              )
        """
        sector_filter = ""
        if sector:
            sector_filter = f" AND {_sector_case('i.LAT')} = %s"
        plan.append(ChatQuerySpec(
            query_id="head_injury_open_incidents",
            tables=(f"{SCHEMA_CLEAN}.VICTIMS", f"{SCHEMA_CLEAN}.INCIDENTS"),
            sql=f"""
                SELECT COUNT(DISTINCT i.INCIDENT_ID) AS N
                FROM {incidents} i
                INNER JOIN {victims} v ON i.INCIDENT_ID = v.INCIDENT_ID
                WHERE i.STATUS IN ('new', 'dispatched', 'en_route', 'partial')
                  AND i.TIMESTAMP > DATEADD(hour, -6, CURRENT_TIMESTAMP())
                  {injury_filter}
                  {sector_filter}
                  {sim_filter_i_alias}
            """,
        ))

    return plan


def query_params(spec: ChatQuerySpec, *, incident_id: str | None, sector: str | None,
                 cluster_id: str | None, sim_run_id: str | None = None) -> tuple[Any, ...]:
    """Bind params for each spec. sim_run_id is appended only for queries
    whose SQL was built with the SIM_RUN_ID filter — keep this aligned
    with build_chat_query_plan's `sim_filter_*` insertion points.

    Lookups by primary key (incident_detail, cluster_row) don't take the
    filter — a specific row ID already narrows the result.
    """
    if spec.query_id == "incident_detail":
        return (incident_id,)
    if spec.query_id == "cluster_row":
        return (cluster_id,)

    if spec.query_id == "sector_open_incidents":
        params: tuple[Any, ...] = (sector.strip().upper(),) if sector else ()
        if sim_run_id:
            params = params + (sim_run_id,)
        return params
    if spec.query_id == "head_injury_open_incidents":
        params = (sector.strip().upper(),) if sector else ()
        if sim_run_id:
            params = params + (sim_run_id,)
        return params

    # open_incidents_by_severity, recent_incidents, active_dispatches:
    # plan adds a sim filter when sim_run_id is set.
    if spec.query_id in ("open_incidents_by_severity", "recent_incidents", "active_dispatches"):
        return (sim_run_id,) if sim_run_id else ()

    return ()

"""
Snowflake tile queries — 5 live tiles for the dashboard.

Queries read from layered schemas (CLEAN / SERVING / FEATURES).
In-memory fallbacks use IncidentStore when Snowflake is not configured.
"""
from __future__ import annotations

import logging
import os
import statistics
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from disaster.models import IncidentReport, Severity
from disaster.snowflake.tables import SCHEMA_CLEAN, SCHEMA_FEATURES, SCHEMA_SERVING

log = logging.getLogger(__name__)


def _db() -> str:
    return os.environ.get("SNOWFLAKE_DATABASE", "DISASTER_DB")


def _t(schema: str, table: str) -> str:
    return f"{_db()}.{schema}.{table}"


def _tile_queries() -> dict[str, str]:
    incidents = _t(SCHEMA_CLEAN, "INCIDENTS")
    victims = _t(SCHEMA_CLEAN, "VICTIMS")
    dispatches = _t(SCHEMA_SERVING, "RESPONDER_DISPATCHES")
    minute_counts = _t(SCHEMA_FEATURES, "INCIDENT_MINUTE_COUNTS")

    return {
        "severity_distribution": f"""
            SELECT SEVERITY, COUNT(*) AS N
            FROM {incidents}
            WHERE TIMESTAMP > DATEADD(minute, -10, CURRENT_TIMESTAMP())
            GROUP BY SEVERITY
        """,
        "incident_rate": f"""
            SELECT MINUTE, SUM(N) AS N
            FROM {minute_counts}
            WHERE MINUTE > DATEADD(minute, -10, CURRENT_TIMESTAMP())
            GROUP BY MINUTE
            ORDER BY MINUTE
        """,
        "incident_rate_fallback": f"""
            SELECT DATE_TRUNC('minute', TIMESTAMP) AS MINUTE, COUNT(*) AS N
            FROM {incidents}
            WHERE TIMESTAMP > DATEADD(minute, -10, CURRENT_TIMESTAMP())
            GROUP BY MINUTE
            ORDER BY MINUTE
        """,
        "response_time_percentiles": f"""
            SELECT
                i.SEVERITY,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY d.ETA_SECONDS) AS P50,
                PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY d.ETA_SECONDS) AS P90,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY d.ETA_SECONDS) AS P99
            FROM {dispatches} d
            JOIN {incidents} i ON d.INCIDENT_ID = i.INCIDENT_ID
            WHERE d.STARTED_AT > DATEADD(minute, -30, CURRENT_TIMESTAMP())
            GROUP BY i.SEVERITY
        """,
        "geographic_equity": f"""
            SELECT
                CASE
                    WHEN i.LAT > 29.31 THEN 'NORTH'
                    WHEN i.LAT < 29.29 THEN 'SOUTH'
                    ELSE 'CENTRAL'
                END AS SECTOR,
                AVG(d.ETA_SECONDS) AS AVG_ETA
            FROM {dispatches} d
            JOIN {incidents} i ON d.INCIDENT_ID = i.INCIDENT_ID
            WHERE d.STARTED_AT > DATEADD(minute, -30, CURRENT_TIMESTAMP())
            GROUP BY SECTOR
        """,
        "extraction_confidence": f"""
            SELECT
                CASE
                    WHEN CONFIDENCE >= 0.9 THEN 'high'
                    WHEN CONFIDENCE >= 0.7 THEN 'medium'
                    ELSE 'low'
                END AS BUCKET,
                COUNT(*) AS N
            FROM {incidents}
            WHERE SOURCE = 'voice'
                AND TIMESTAMP > DATEADD(minute, -10, CURRENT_TIMESTAMP())
            GROUP BY BUCKET
        """,
        "victims_for_cortex": f"""
            SELECT INCIDENT_ID, INJURIES, VULNERABILITIES
            FROM {victims}
        """,
    }


# Public map: tile name → primary SQL (incident_rate tries FEATURES first in run_tile).
_q = _tile_queries()
TILE_QUERIES: dict[str, str] = {
    "severity_distribution": _q["severity_distribution"],
    "incident_rate": _q["incident_rate"],
    "response_time_percentiles": _q["response_time_percentiles"],
    "geographic_equity": _q["geographic_equity"],
    "extraction_confidence": _q["extraction_confidence"],
}


def _ensure_tile_queries() -> None:
    return


# Cortex anomaly detection — staged; requires FEATURES.INCIDENT_MINUTE_COUNTS population.
def _cortex_anomaly_query() -> str:
    db = _db()
    return f"""
    SELECT
        injury_cluster_type,
        sector,
        observed_count,
        baseline_count,
        z_score
    FROM TABLE(
        DETECT_ANOMALIES(
            INPUT_DATA => 'SELECT * FROM {db}.FEATURES.INCIDENT_MINUTE_COUNTS',
            TIMESTAMP_COLNAME => 'MINUTE',
            TARGET_COLNAME => 'N',
            CONFIG_OBJECT => OBJECT_CONSTRUCT('prediction_interval', 0.95)
        )
    )
    WHERE is_anomaly = TRUE
"""


CORTEX_ANOMALY_QUERY = _cortex_anomaly_query()


async def run_tile(
    tile_name: str,
    *,
    runner: Callable[[str, tuple], Awaitable[list[dict[str, Any]]]] | None,
    fallback_incidents: list[IncidentReport] | None = None,
) -> dict[str, Any]:
    """
    Run a tile query. If runner is None (no Snowflake configured), compute the
    same shape from the in-memory store so the dashboard tile renders identically.
    """
    _ensure_tile_queries()
    if tile_name not in TILE_QUERIES:
        return {"tile": tile_name, "error": "unknown_tile"}

    if runner is not None:
        try:
            sql = TILE_QUERIES[tile_name]
            rows = await runner(sql, ())
            if tile_name == "incident_rate" and not rows:
                q = _tile_queries()
                rows = await runner(q["incident_rate_fallback"], ())
            return {"tile": tile_name, "source": "snowflake", "rows": _normalize_rows(rows)}
        except Exception as e:  # noqa: BLE001
            log.warning("tile %s: snowflake failed (%s), using in-memory fallback", tile_name, e)

    incidents = fallback_incidents or []
    rows = _synthetic_tile(tile_name, incidents)
    return {"tile": tile_name, "source": "in_memory", "rows": rows}


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lowercase keys for frontend compatibility."""
    out = []
    for row in rows:
        out.append({(k.lower() if isinstance(k, str) else k): v for k, v in row.items()})
    return out


def _synthetic_tile(tile_name: str, incidents: list[IncidentReport]) -> list[dict[str, Any]]:
    """In-memory equivalents that match the SQL shape."""
    now = datetime.now(UTC)
    if tile_name == "severity_distribution":
        recent = [i for i in incidents if (now - i.timestamp) < timedelta(minutes=10)]
        counts: dict[str, int] = defaultdict(int)
        for i in recent:
            counts[i.severity.value] += 1
        return [{"severity": s.value, "n": counts.get(s.value, 0)} for s in Severity]

    if tile_name == "incident_rate":
        recent = [i for i in incidents if (now - i.timestamp) < timedelta(minutes=10)]
        per_min: dict[str, int] = defaultdict(int)
        for i in recent:
            key = i.timestamp.replace(second=0, microsecond=0).isoformat()
            per_min[key] += 1
        return [{"minute": k, "n": v} for k, v in sorted(per_min.items())]

    if tile_name == "response_time_percentiles":
        by_sev: dict[str, list[float]] = defaultdict(list)
        for i in incidents:
            est_eta = 600.0 * (1.0 - i.priority_score)
            by_sev[i.severity.value].append(est_eta)
        out = []
        for sev, etas in by_sev.items():
            if not etas:
                continue
            etas_sorted = sorted(etas)
            n = len(etas_sorted)
            out.append({
                "severity": sev,
                "p50": etas_sorted[n // 2],
                "p90": etas_sorted[min(n - 1, int(n * 0.9))],
                "p99": etas_sorted[-1],
            })
        return out

    if tile_name == "geographic_equity":
        by_sector: dict[str, list[float]] = defaultdict(list)
        for i in incidents:
            sector = "NORTH" if i.location.lat > 29.31 else ("SOUTH" if i.location.lat < 29.29 else "CENTRAL")
            by_sector[sector].append(600.0 * (1.0 - i.priority_score))
        return [{"sector": s, "avg_eta": statistics.mean(v) if v else 0.0} for s, v in by_sector.items()]

    if tile_name == "extraction_confidence":
        voice = [i for i in incidents if i.source.value == "voice"]
        buckets: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for i in voice:
            if i.confidence >= 0.9:
                buckets["high"] += 1
            elif i.confidence >= 0.7:
                buckets["medium"] += 1
            else:
                buckets["low"] += 1
        return [{"bucket": k, "n": v} for k, v in buckets.items()]

    return []

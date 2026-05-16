"""
Snowflake tile queries — 5 live tiles for the dashboard.

  hero  : severity distribution (donut shape)
  peer 1: incident rate per minute, last 10 minutes
  peer 2: response time percentiles by severity
  peer 3: geographic equity score (variance across neighborhoods)
  peer 4: voice extraction confidence distribution

In demo mode without a Snowflake connection, these return synthetic data
computed from the in-memory IncidentStore so the dashboard never looks broken.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from disaster.models import IncidentReport, Severity

log = logging.getLogger(__name__)


# Tile name → SQL template (use named params via ?)
TILE_QUERIES: dict[str, str] = {
    "severity_distribution": """
        SELECT severity, COUNT(*) AS n
        FROM incidents
        WHERE timestamp > DATEADD(minute, -10, CURRENT_TIMESTAMP())
        GROUP BY severity
    """,
    "incident_rate": """
        SELECT DATE_TRUNC('minute', timestamp) AS minute, COUNT(*) AS n
        FROM incidents
        WHERE timestamp > DATEADD(minute, -10, CURRENT_TIMESTAMP())
        GROUP BY minute
        ORDER BY minute
    """,
    "response_time_percentiles": """
        SELECT
            severity,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY eta_seconds) AS p50,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY eta_seconds) AS p90,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY eta_seconds) AS p99
        FROM responder_dispatches d JOIN incidents i ON d.incident_id = i.id
        WHERE d.dispatched_at > DATEADD(minute, -30, CURRENT_TIMESTAMP())
        GROUP BY severity
    """,
    "geographic_equity": """
        SELECT
            CASE
                WHEN lat > 19.73 THEN 'NORTH'
                WHEN lat < 19.71 THEN 'SOUTH'
                ELSE 'CENTRAL'
            END AS sector,
            AVG(eta_seconds) AS avg_eta
        FROM responder_dispatches d JOIN incidents i ON d.incident_id = i.id
        WHERE d.dispatched_at > DATEADD(minute, -30, CURRENT_TIMESTAMP())
        GROUP BY sector
    """,
    "extraction_confidence": """
        SELECT
            CASE
                WHEN confidence >= 0.9 THEN 'high'
                WHEN confidence >= 0.7 THEN 'medium'
                ELSE 'low'
            END AS bucket,
            COUNT(*) AS n
        FROM incidents
        WHERE source = 'voice'
            AND timestamp > DATEADD(minute, -10, CURRENT_TIMESTAMP())
        GROUP BY bucket
    """,
}

# Cortex anomaly detection — staged for demo, run separately.
CORTEX_ANOMALY_QUERY = """
    SELECT
        injury_cluster_type,
        sector,
        observed_count,
        baseline_count,
        z_score
    FROM TABLE(
        DETECT_ANOMALIES(
            INPUT_DATA => 'SELECT * FROM incident_minute_counts',
            TIMESTAMP_COLNAME => 'minute',
            TARGET_COLNAME => 'count',
            CONFIG_OBJECT => OBJECT_CONSTRUCT('prediction_interval', 0.95)
        )
    )
    WHERE is_anomaly = TRUE
"""


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
    if tile_name not in TILE_QUERIES:
        return {"tile": tile_name, "error": "unknown_tile"}

    if runner is not None:
        try:
            rows = await runner(TILE_QUERIES[tile_name], ())
            return {"tile": tile_name, "source": "snowflake", "rows": rows}
        except Exception as e:  # noqa: BLE001 — Snowflake connector raises diverse types
            log.warning("tile %s: snowflake failed (%s), using in-memory fallback", tile_name, e)

    # Fallback: in-memory synthetic
    incidents = fallback_incidents or []
    rows = _synthetic_tile(tile_name, incidents)
    return {"tile": tile_name, "source": "in_memory", "rows": rows}


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
        # We don't have dispatch records in-memory; synthesize from priority_score
        # (higher priority → faster response in our fictional metric).
        by_sev: dict[str, list[float]] = defaultdict(list)
        for i in incidents:
            est_eta = 600.0 * (1.0 - i.priority_score)   # 0-600s
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
            sector = "NORTH" if i.location.lat > 19.73 else ("SOUTH" if i.location.lat < 19.71 else "CENTRAL")
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

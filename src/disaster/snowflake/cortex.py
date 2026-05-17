"""
Cortex pattern detection.

Two modes:
  (1) Snowflake-backed (CORTEX_CLUSTER_SQL): groups recent CLEAN incidents + victims.
  (2) In-memory (detect_clusters): pure Python fallback.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from disaster.models import IncidentReport
from disaster.snowflake.tables import SCHEMA_CLEAN

log = logging.getLogger(__name__)

# Same connection-wedge risk as tiles + aar — a sick shared Snowflake session
# can hang this query until the request times out at the proxy layer.
_CORTEX_QUERY_TIMEOUT_S = 4.0


def _db() -> str:
    return os.environ.get("SNOWFLAKE_DATABASE", "DISASTER_DB")


def _cortex_cluster_sql() -> str:
    incidents = f"{_db()}.{SCHEMA_CLEAN}.INCIDENTS"
    victims = f"{_db()}.{SCHEMA_CLEAN}.VICTIMS"
    return f"""
WITH recent AS (
    SELECT
        i.INCIDENT_ID,
        CASE
            WHEN i.LAT > 29.31 THEN 'NORTH'
            WHEN i.LAT < 29.29 THEN 'SOUTH'
            ELSE 'CENTRAL'
        END AS SECTOR,
        CASE
            WHEN POSITION('respir' IN LOWER(COALESCE(TO_VARCHAR(v.INJURIES), ''))) > 0
              OR i.SEVERITY = 'Immediate'
                THEN 'respiratory'
            WHEN POSITION('burn' IN LOWER(COALESCE(TO_VARCHAR(v.INJURIES), ''))) > 0
                THEN 'burn'
            WHEN POSITION('crush' IN LOWER(COALESCE(TO_VARCHAR(v.INJURIES), ''))) > 0
              OR POSITION('trauma' IN LOWER(COALESCE(TO_VARCHAR(v.INJURIES), ''))) > 0
                THEN 'trauma'
            ELSE 'other'
        END AS INJURY_BUCKET
    FROM {incidents} i
    LEFT JOIN {victims} v ON i.INCIDENT_ID = v.INCIDENT_ID AND v.VICTIM_ORDINAL = 1
    WHERE i.TIMESTAMP > DATEADD(minute, -5, CURRENT_TIMESTAMP())
)
SELECT INJURY_BUCKET, SECTOR, COUNT(*) AS N
FROM recent
WHERE INJURY_BUCKET != 'other'
GROUP BY INJURY_BUCKET, SECTOR
HAVING COUNT(*) >= 3
ORDER BY N DESC
"""


CORTEX_CLUSTER_SQL = _cortex_cluster_sql()


async def detect_clusters_snowflake(
    runner: Callable[[str, tuple], Awaitable[list[dict[str, Any]]]],
    *,
    window_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Run the real SQL cluster query, return alert dicts."""
    rows = await asyncio.wait_for(runner(CORTEX_CLUSTER_SQL, ()), timeout=_CORTEX_QUERY_TIMEOUT_S)
    return [_row_to_alert(r, window_minutes) for r in rows]


def _row_to_alert(row: dict[str, Any], window_minutes: int) -> dict[str, Any]:
    bucket = row.get("INJURY_BUCKET") or row.get("injury_bucket")
    sector = row.get("SECTOR") or row.get("sector")
    n = row.get("N") or row.get("n") or 0
    return {
        "type": "cluster",
        "injury_bucket": bucket,
        "sector": sector,
        "count": int(n),
        "window_minutes": window_minutes,
        "message": f"{str(bucket).title()} complaints clustering in {sector} sector — possible secondary incident",
    }


def detect_clusters(
    incidents: list[IncidentReport],
    *,
    window_minutes: int = 5,
    min_cluster: int = 3,
    radius_km: float = 0.5,
) -> list[dict[str, Any]]:
    """In-memory clustering used when no Snowflake runner is configured."""
    _ = radius_km
    now = datetime.now(UTC)
    recent = [i for i in incidents if (now - i.timestamp) <= timedelta(minutes=window_minutes)]
    if len(recent) < min_cluster:
        return []

    def _sector(i: IncidentReport) -> str:
        if i.location.lat > 29.31:
            return "NORTH"
        if i.location.lat < 29.29:
            return "SOUTH"
        return "CENTRAL"

    def _injury_bucket(i: IncidentReport) -> str:
        injuries = [inj.lower() for v in i.victims for inj in v.injuries]
        if any("respir" in inj or "breath" in inj or "lung" in inj for inj in injuries):
            return "respiratory"
        if any("burn" in inj for inj in injuries):
            return "burn"
        if any("crush" in inj or "trauma" in inj or "fracture" in inj for inj in injuries):
            return "trauma"
        return "other"

    alerts: list[dict[str, Any]] = []
    by_key = Counter((_injury_bucket(i), _sector(i)) for i in recent)
    for (bucket, sector), n in by_key.items():
        if bucket == "other":
            continue
        if n >= min_cluster:
            alerts.append({
                "type": "cluster",
                "injury_bucket": bucket,
                "sector": sector,
                "count": n,
                "window_minutes": window_minutes,
                "message": f"{bucket.title()} complaints clustering in {sector} sector — possible secondary incident",
            })
    return alerts

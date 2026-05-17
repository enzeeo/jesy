"""
Cortex pattern detection.

Two modes:
  (1) Snowflake-backed (CORTEX_CLUSTER_SQL): groups recent incidents by injury
      bucket + geographic sector, returns clusters above threshold.
  (2) In-memory (detect_clusters): pure Python fallback used when no Snowflake
      runner is configured, or when the SQL path fails.

Both produce identical alert dict shapes so /cortex/scan can swap between them
transparently.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from disaster.models import IncidentReport

log = logging.getLogger(__name__)


# ── Snowflake path ───────────────────────────────────────────────────────────
# Real-Snowflake cluster query. Avoids Cortex DETECT_ANOMALIES because that
# requires a pre-trained ML model (CREATE SNOWFLAKE.ML.ANOMALY_DETECTION) and
# training data we don't have at hackathon scale. Instead this groups recent
# incidents by injury-bucket-derived-from-vulnerabilities-and-status + sector
# and returns clusters above the min_cluster threshold.
#
# The output columns must match what _row_to_alert expects below.
CORTEX_CLUSTER_SQL = """
WITH recent AS (
    SELECT
        CASE
            WHEN lat > 29.31 THEN 'NORTH'
            WHEN lat < 29.29 THEN 'SOUTH'
            ELSE 'CENTRAL'
        END                                AS sector,
        CASE
            WHEN POSITION('respir' IN LOWER(COALESCE(vulnerabilities, ''))) > 0
              OR severity = 'Immediate' AND POSITION('respir' IN LOWER(location_description)) > 0
                THEN 'respiratory'
            WHEN POSITION('burn' IN LOWER(COALESCE(vulnerabilities, ''))) > 0
                THEN 'burn'
            WHEN POSITION('crush' IN LOWER(COALESCE(vulnerabilities, ''))) > 0
              OR POSITION('trauma' IN LOWER(COALESCE(vulnerabilities, ''))) > 0
              OR POSITION('fracture' IN LOWER(COALESCE(vulnerabilities, ''))) > 0
                THEN 'trauma'
            ELSE 'other'
        END                                AS injury_bucket
    FROM incidents
    WHERE timestamp > DATEADD(minute, -5, CURRENT_TIMESTAMP())
)
SELECT injury_bucket, sector, COUNT(*) AS n
FROM recent
WHERE injury_bucket != 'other'
GROUP BY injury_bucket, sector
HAVING COUNT(*) >= 3
ORDER BY n DESC
"""


async def detect_clusters_snowflake(
    runner: Callable[[str, tuple], Awaitable[list[dict[str, Any]]]],
    *,
    window_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Run the real SQL cluster query, return alert dicts."""
    rows = await runner(CORTEX_CLUSTER_SQL, ())
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


# ── In-memory fallback ───────────────────────────────────────────────────────
def detect_clusters(
    incidents: list[IncidentReport],
    *,
    window_minutes: int = 5,
    min_cluster: int = 3,
    radius_km: float = 0.5,
) -> list[dict[str, Any]]:
    """In-memory clustering used when no Snowflake runner is configured."""
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

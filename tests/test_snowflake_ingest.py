"""Tests for layered Snowflake ingest fan-out."""
from __future__ import annotations

from disaster.snowflake.ingest import emit_incident
from disaster.snowflake.tables import SCHEMA_CLEAN, SCHEMA_RAW
from disaster.snowflake.writer import SnowflakeWriter


async def test_emit_incident_writes_raw_and_clean():
    collected: dict[str, list] = {}

    async def collect(table, rows):
        collected.setdefault(table, []).extend(rows)

    writer = SnowflakeWriter(collect, flush_interval_s=0.05, batch_size=1)
    await writer.start()
    report = {
        "id": "11111111-1111-1111-1111-111111111111",
        "timestamp": "2026-05-17T12:00:00+00:00",
        "source": "simulated",
        "status": "new",
        "location": {"lat": 19.73, "lng": -155.09, "description": "Pier 4"},
        "severity": "Immediate",
        "priority_score": 0.9,
        "confidence": 1.0,
        "victims": [{
            "age_estimate": 8,
            "injuries": ["crush injury"],
            "vulnerabilities": ["child"],
            "consciousness": "alert",
        }],
    }
    emit_incident(writer, report)
    await writer.stop(0.5)

    assert f"{SCHEMA_RAW}.RAW_INCIDENT_SUBMISSIONS" in collected
    assert f"{SCHEMA_CLEAN}.INCIDENTS" in collected
    assert f"{SCHEMA_CLEAN}.VICTIMS" in collected
    assert collected[f"{SCHEMA_CLEAN}.INCIDENTS"][0]["INCIDENT_ID"] == report["id"]

"""Tests for layered Snowflake ingest fan-out."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import disaster.snowflake.ingest as ingest
from disaster.road_access import demo_road_access
from disaster.snowflake.ingest import emit_cortex_alert, emit_incident
from disaster.snowflake.tables import SCHEMA_CLEAN, SCHEMA_RAW, SCHEMA_SERVING
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
        "location": {"lat": 35.5951, "lng": -82.5515, "description": "Downtown Asheville"},
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
    row = collected[f"{SCHEMA_CLEAN}.INCIDENTS"][0]
    assert row["INCIDENT_ID"] == report["id"]
    assert row["INCIDENT_DESCRIPTION"] == "Downtown Asheville"
    assert "SOURCE" not in row
    assert "VICTIM_COUNT" not in row
    assert "CONFIDENCE" not in row


async def test_emit_road_access_snapshot_writes_snapshot_and_features():
    collected: dict[str, list] = {}

    async def collect(table, rows):
        collected.setdefault(table, []).extend(rows)

    writer = SnowflakeWriter(collect, flush_interval_s=0.05, batch_size=1)
    await writer.start()
    assert hasattr(ingest, "emit_road_access_snapshot")
    road_access = demo_road_access()
    road_access_id = ingest.emit_road_access_snapshot(writer, road_access)
    await writer.stop(0.5)

    snapshots = collected[f"{SCHEMA_CLEAN}.ROAD_ACCESS_SNAPSHOTS"]
    features = collected[f"{SCHEMA_CLEAN}.ROAD_ACCESS_FEATURES"]
    assert snapshots[0]["ROAD_ACCESS_ID"] == road_access_id
    assert snapshots[0]["SOURCE"] == "helene_curated_asheville"
    assert len(features) == len(road_access["features"])


async def test_emit_cortex_alert_serializes_datetime_in_payload():
    collected: dict[str, list] = {}

    async def collect(table, rows):
        collected.setdefault(table, []).extend(rows)

    writer = SnowflakeWriter(collect, flush_interval_s=0.05, batch_size=1)
    await writer.start()
    detected = datetime.now(UTC)
    emit_cortex_alert(writer, {
        "type": "cluster",
        "sector": "NORTH",
        "message": "test",
        "detected_at": detected,
    })
    await writer.stop(0.5)

    row = collected[f"{SCHEMA_SERVING}.CORTEX_ALERTS"][0]
    payload = json.loads(row["PAYLOAD"])
    assert payload["detected_at"] == detected.isoformat()

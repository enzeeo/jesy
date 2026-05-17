"""Live ops Snowflake agent card tests."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from disaster.app.deps import AppState
from disaster.app.main import create_app
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    Perfusion,
    ResponderType,
    ResponderUnit,
    Severity,
    Victim,
)
from disaster.snowflake.live_ops import (
    LATEST_AGENT_RUNS_SQL,
    LIVE_CLUSTER_MONITOR_SQL,
    LIVE_RESOURCE_GAP_SQL,
    latest_ops_cards,
    run_live_ops_agents,
)
from disaster.snowflake.tables import SCHEMA_AGENT
from disaster.snowflake.writer import SnowflakeWriter


async def _noop_flush(_table: str, _rows: list[dict]) -> None:
    return None


def _incident() -> IncidentReport:
    return IncidentReport(
        timestamp=datetime.now(UTC),
        location=Location(lat=35.62, lng=-82.55, description="North sector"),
        victims=[Victim(
            mobility=Mobility.WALKING,
            breathing=Breathing.SPONTANEOUS,
            perfusion=Perfusion.NORMAL,
        )],
        severity=Severity.IMMEDIATE,
        priority_score=0.9,
    )


def _responder() -> ResponderUnit:
    return ResponderUnit(
        callsign="ALS-1",
        type=ResponderType.ALS,
        location=Location(lat=35.62, lng=-82.56, description="North staging"),
    )


async def test_ops_endpoint_returns_in_memory_cards_without_snowflake():
    state = AppState()
    await state.incidents.insert(_incident())
    await state.responders.upsert(_responder())
    app = create_app(snowflake_writer=SnowflakeWriter(_noop_flush), state=state)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/snowflake/ops")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "in_memory"
    assert {card["agent_name"] for card in body["cards"]} == {
        "Cluster Monitor",
        "Resource Gap Monitor",
        "Supervisor Agent",
    }
    assert all({"severity", "summary", "recommendation", "run_id", "timestamp"} <= set(card) for card in body["cards"])


async def test_latest_ops_cards_uses_dynamic_tables_before_saved_agent_runs():
    calls: list[str] = []

    async def fake_runner(sql: str, _params: tuple):
        calls.append(sql)
        if sql == LIVE_CLUSTER_MONITOR_SQL:
            return [{
                "CLUSTER_WINDOW_ID": "cluster-1",
                "H3_RES8": "8844",
                "SECTOR_ID": "NORTH",
                "WINDOW_END": "2026-05-17T12:00:00+00:00",
                "ACTIVE_INCIDENTS": 2,
                "IMMEDIATE_COUNT": 1,
                "DELAYED_COUNT": 0,
                "MAX_PRIORITY_SCORE": 0.9,
                "INCIDENT_IDS": "incident-1",
            }]
        if sql == LIVE_RESOURCE_GAP_SQL:
            return [{
                "GAP_ID": "gap-1",
                "H3_RES8": "8844",
                "SECTOR_ID": "NORTH",
                "COMPUTED_AT": "2026-05-17T12:00:00+00:00",
                "OPEN_INCIDENTS": 2,
                "IMMEDIATE_COUNT": 1,
                "DELAYED_COUNT": 0,
                "AVAILABLE_RESPONDERS": 0,
                "GAP_SCORE": 1,
                "MAX_PRIORITY_SCORE": 0.9,
                "RECOMMENDATION": "Review nearby idle units.",
            }]
        if sql == LATEST_AGENT_RUNS_SQL:
            return [{
                "RUN_ID": "run-cluster",
                "AGENT_NAME": "Cluster Monitor",
                "OUTPUT_PAYLOAD": json.dumps({
                    "severity": "warning",
                    "title": "Cluster Monitor: NORTH",
                    "summary": "H3 cell 8844 has 1 active incident(s), including 1 immediate.",
                    "recommendation": "Review the cluster.",
                    "evidence": [{"sector_id": "NORTH"}],
                }),
                "STARTED_AT": "2026-05-17T12:00:00+00:00",
                "ENDED_AT": "2026-05-17T12:00:01+00:00",
            }]
        raise AssertionError(sql)

    body = await latest_ops_cards(
        runner=fake_runner,
        fallback_incidents=[],
        fallback_responders=[],
    )

    assert body["source"] == "snowflake_dynamic"
    assert body["cards"][0]["severity"] == "warning"
    assert body["cards"][0]["summary"] == "North sector has 2 open incidents, including 1 immediate incident."
    assert LATEST_AGENT_RUNS_SQL not in calls


def test_live_ops_dynamic_queries_rank_urgency_before_recency():
    assert (
        "ORDER BY IMMEDIATE_COUNT DESC, ACTIVE_INCIDENTS DESC, "
        "MAX_PRIORITY_SCORE DESC, WINDOW_END DESC"
    ) in LIVE_CLUSTER_MONITOR_SQL
    assert (
        "ORDER BY GAP_SCORE DESC, IMMEDIATE_COUNT DESC, "
        "MAX_PRIORITY_SCORE DESC, COMPUTED_AT DESC"
    ) in LIVE_RESOURCE_GAP_SQL


async def test_dynamic_cards_surface_highest_priority_row_in_summary_and_evidence():
    async def fake_runner(sql: str, _params: tuple):
        if sql == LIVE_CLUSTER_MONITOR_SQL:
            return [
                {
                    "CLUSTER_WINDOW_ID": "cluster-central",
                    "H3_RES8": "central-cell",
                    "SECTOR_ID": "CENTRAL",
                    "WINDOW_END": "2026-05-17T12:00:00+00:00",
                    "ACTIVE_INCIDENTS": 1,
                    "IMMEDIATE_COUNT": 0,
                    "DELAYED_COUNT": 1,
                    "MAX_PRIORITY_SCORE": 0.5,
                    "INCIDENT_IDS": "incident-central",
                },
                {
                    "CLUSTER_WINDOW_ID": "cluster-south",
                    "H3_RES8": "south-cell",
                    "SECTOR_ID": "SOUTH",
                    "WINDOW_END": "2026-05-17T11:59:00+00:00",
                    "ACTIVE_INCIDENTS": 3,
                    "IMMEDIATE_COUNT": 2,
                    "DELAYED_COUNT": 0,
                    "MAX_PRIORITY_SCORE": 0.9,
                    "INCIDENT_IDS": "incident-south-1,incident-south-2",
                },
            ]
        if sql == LIVE_RESOURCE_GAP_SQL:
            return [
                {
                    "GAP_ID": "gap-central",
                    "H3_RES8": "central-cell",
                    "SECTOR_ID": "CENTRAL",
                    "COMPUTED_AT": "2026-05-17T12:00:00+00:00",
                    "OPEN_INCIDENTS": 1,
                    "IMMEDIATE_COUNT": 0,
                    "DELAYED_COUNT": 1,
                    "AVAILABLE_RESPONDERS": 0,
                    "GAP_SCORE": 1,
                    "MAX_PRIORITY_SCORE": 0.5,
                    "RECOMMENDATION": "Review nearby idle units.",
                },
                {
                    "GAP_ID": "gap-south",
                    "H3_RES8": "south-cell",
                    "SECTOR_ID": "SOUTH",
                    "COMPUTED_AT": "2026-05-17T11:59:00+00:00",
                    "OPEN_INCIDENTS": 3,
                    "IMMEDIATE_COUNT": 2,
                    "DELAYED_COUNT": 1,
                    "AVAILABLE_RESPONDERS": 0,
                    "GAP_SCORE": 3,
                    "MAX_PRIORITY_SCORE": 0.9,
                    "RECOMMENDATION": "Review nearby idle units.",
                },
            ]
        raise AssertionError(sql)

    body = await latest_ops_cards(
        runner=fake_runner,
        fallback_incidents=[],
        fallback_responders=[],
    )
    cards = {card["agent_name"]: card for card in body["cards"]}

    cluster_card = cards["Cluster Monitor"]
    gap_card = cards["Resource Gap Monitor"]
    supervisor_card = cards["Supervisor Agent"]

    assert cluster_card["title"] == "Cluster Monitor: South sector"
    assert cluster_card["summary"] == "South sector has 3 open incidents, including 2 immediate incidents."
    assert cluster_card["evidence"][0]["sector_id"] == "SOUTH"
    assert cluster_card["evidence"][0]["h3_res8"] == "south-cell"
    assert gap_card["title"] == "Resource Gap: South sector"
    assert gap_card["summary"] == (
        "South sector is short 3 responders: 2 immediate incidents, "
        "1 delayed incident, and 0 idle units nearby."
    )
    assert gap_card["evidence"][0]["sector_id"] == "SOUTH"
    assert gap_card["evidence"][0]["h3_res8"] == "south-cell"
    assert supervisor_card["summary"] == (
        "South sector needs review: incidents are clustering and responder coverage is short."
    )


async def test_supervisor_summary_separates_different_cluster_and_gap_sectors():
    async def fake_runner(sql: str, _params: tuple):
        if sql == LIVE_CLUSTER_MONITOR_SQL:
            return [{
                "CLUSTER_WINDOW_ID": "cluster-central",
                "H3_RES8": "central-cell",
                "SECTOR_ID": "CENTRAL",
                "WINDOW_END": "2026-05-17T12:00:00+00:00",
                "ACTIVE_INCIDENTS": 1,
                "IMMEDIATE_COUNT": 1,
                "DELAYED_COUNT": 0,
                "MAX_PRIORITY_SCORE": 0.9,
                "INCIDENT_IDS": "incident-central",
            }]
        if sql == LIVE_RESOURCE_GAP_SQL:
            return [{
                "GAP_ID": "gap-south",
                "H3_RES8": "south-cell",
                "SECTOR_ID": "SOUTH",
                "COMPUTED_AT": "2026-05-17T12:00:00+00:00",
                "OPEN_INCIDENTS": 1,
                "IMMEDIATE_COUNT": 1,
                "DELAYED_COUNT": 0,
                "AVAILABLE_RESPONDERS": 0,
                "GAP_SCORE": 1,
                "MAX_PRIORITY_SCORE": 0.9,
                "RECOMMENDATION": "Review nearby idle units.",
            }]
        raise AssertionError(sql)

    body = await latest_ops_cards(
        runner=fake_runner,
        fallback_incidents=[],
        fallback_responders=[],
    )
    cards = {card["agent_name"]: card for card in body["cards"]}

    assert cards["Supervisor Agent"]["summary"] == (
        "Central sector has the active cluster; South sector has the responder shortfall."
    )


async def test_latest_ops_cards_skips_legacy_saved_agent_copy_when_dynamic_tables_fail():
    async def fake_runner(sql: str, _params: tuple):
        if sql in {LIVE_CLUSTER_MONITOR_SQL, LIVE_RESOURCE_GAP_SQL}:
            raise RuntimeError("dynamic table unavailable")
        if sql == LATEST_AGENT_RUNS_SQL:
            return [{
                "RUN_ID": "run-cluster",
                "AGENT_NAME": "Cluster Monitor",
                "OUTPUT_PAYLOAD": json.dumps({
                    "severity": "warning",
                    "title": "Cluster Monitor: NORTH",
                    "summary": "H3 cell 8844 has 1 active incident(s), including 1 immediate.",
                    "recommendation": "Review gap score 1.",
                    "evidence": [{"sector_id": "NORTH"}],
                }),
                "STARTED_AT": "2026-05-17T12:00:00+00:00",
                "ENDED_AT": "2026-05-17T12:00:01+00:00",
            }]
        raise AssertionError(sql)

    body = await latest_ops_cards(
        runner=fake_runner,
        fallback_incidents=[_incident()],
        fallback_responders=[_responder()],
    )

    assert body["source"] == "in_memory"
    visible_copy = " ".join(card["summary"] for card in body["cards"])
    assert "H3 cell" not in visible_copy
    assert "gap score" not in visible_copy


async def test_latest_ops_cards_falls_back_when_snowflake_queries_fail():
    async def failing_runner(_sql: str, _params: tuple):
        raise RuntimeError("dynamic table unavailable")

    body = await latest_ops_cards(
        runner=failing_runner,
        fallback_incidents=[_incident()],
        fallback_responders=[_responder()],
    )

    assert body["source"] == "in_memory"
    assert len(body["cards"]) == 3


async def test_run_live_ops_agents_writes_agent_runs():
    written: list[tuple[str, dict]] = []

    class CaptureWriter:
        def write(self, table: str, row: dict) -> None:
            written.append((table, row))

    async def fake_runner(sql: str, _params: tuple):
        if sql == LIVE_CLUSTER_MONITOR_SQL:
            return [{
                "CLUSTER_WINDOW_ID": "cluster-1",
                "H3_RES8": "8844",
                "SECTOR_ID": "NORTH",
                "WINDOW_END": "2026-05-17T12:00:00+00:00",
                "ACTIVE_INCIDENTS": 4,
                "IMMEDIATE_COUNT": 2,
                "DELAYED_COUNT": 1,
                "MAX_PRIORITY_SCORE": 0.9,
                "INCIDENT_IDS": "incident-1,incident-2",
            }]
        if sql == LIVE_RESOURCE_GAP_SQL:
            return [{
                "GAP_ID": "gap-1",
                "H3_RES8": "8844",
                "SECTOR_ID": "NORTH",
                "COMPUTED_AT": "2026-05-17T12:00:00+00:00",
                "OPEN_INCIDENTS": 4,
                "IMMEDIATE_COUNT": 2,
                "DELAYED_COUNT": 1,
                "AVAILABLE_RESPONDERS": 1,
                "GAP_SCORE": 2,
                "MAX_PRIORITY_SCORE": 0.9,
                "RECOMMENDATION": "Review nearby idle units.",
            }]
        raise AssertionError(sql)

    cards = await run_live_ops_agents(runner=fake_runner, writer=CaptureWriter())  # type: ignore[arg-type]

    assert {card.agent_name for card in cards} == {
        "Cluster Monitor",
        "Resource Gap Monitor",
        "Supervisor Agent",
    }
    assert len(written) == 3
    assert {table for table, _row in written} == {f"{SCHEMA_AGENT}.AGENT_RUNS"}
    payloads = [json.loads(row["OUTPUT_PAYLOAD"]) for _table, row in written]
    assert any(payload["severity"] == "warning" for payload in payloads)
    cards_by_agent = {card.agent_name: card for card in cards}
    cluster_card = cards_by_agent["Cluster Monitor"]
    gap_card = cards_by_agent["Resource Gap Monitor"]
    supervisor_card = cards_by_agent["Supervisor Agent"]

    assert cluster_card.summary == (
        "North sector has 4 open incidents, including 2 immediate incidents "
        "and 1 delayed incident."
    )
    assert gap_card.summary == (
        "North sector is short 2 responders: 2 immediate incidents, "
        "1 delayed incident, and 1 idle unit nearby."
    )
    assert supervisor_card.summary == (
        "North sector needs review: incidents are clustering and responder coverage is short."
    )

    visible_copy = " ".join(card.summary for card in cards)
    assert "H3 cell" not in visible_copy
    assert "gap score" not in visible_copy
    assert cluster_card.evidence[0]["h3_res8"] == "8844"

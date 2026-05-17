"""Tests for live Snowflake DDL and smoke graceful fallback helpers."""
from __future__ import annotations

from pathlib import Path

from scripts.snowflake_smoke import (
    is_dynamic_table_statement,
    is_graceful_dynamic_error,
    render_init_sql,
    run_init_sql,
)

SQL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "snowflake_init.sql"


def _section_between(sql_text: str, start: str, end: str) -> str:
    start_index = sql_text.index(start)
    end_index = sql_text.index(end, start_index)
    return sql_text[start_index:end_index]


def test_live_dynamic_table_ddl_contains_expected_objects_and_options():
    sql_text = SQL_PATH.read_text()

    assert "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_INCIDENT_H3" in sql_text
    assert "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_H3_CLUSTER_WINDOWS" in sql_text
    assert "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_ROUTE_STATUS" in sql_text
    assert "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_RESOURCE_GAPS" in sql_text
    assert "TARGET_LAG = '1 minute'" in sql_text
    assert "H3_LATLNG_TO_CELL(LAT, LNG, 8)" in sql_text
    assert sql_text.count("CLUSTER BY") >= 4


def test_live_dynamic_table_init_rebuilds_changed_derived_tables_in_order():
    sql_text = SQL_PATH.read_text()
    drop_gap = "DROP DYNAMIC TABLE IF EXISTS DISASTER_DB.SERVING.LIVE_RESOURCE_GAPS"
    drop_cluster = "DROP DYNAMIC TABLE IF EXISTS DISASTER_DB.FEATURES.LIVE_H3_CLUSTER_WINDOWS"
    create_cluster = "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_H3_CLUSTER_WINDOWS"
    create_gap = "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_RESOURCE_GAPS"

    assert drop_gap in sql_text
    assert drop_cluster in sql_text
    assert sql_text.index(drop_gap) < sql_text.index(drop_cluster)
    assert sql_text.index(drop_cluster) < sql_text.index(create_cluster)
    assert sql_text.index(create_cluster) < sql_text.index(create_gap)


def test_live_cluster_windows_are_open_area_clusters_not_minute_buckets():
    sql_text = SQL_PATH.read_text()
    cluster_sql = _section_between(
        sql_text,
        "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_H3_CLUSTER_WINDOWS",
        "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_ROUTE_STATUS",
    )

    assert "CONCAT(H3_RES8, ':', SECTOR_ID) AS CLUSTER_WINDOW_ID" in cluster_sql
    assert "MIN(INCIDENT_MINUTE) AS WINDOW_START" in cluster_sql
    assert "MAX(INCIDENT_MINUTE) AS WINDOW_END" in cluster_sql
    assert "GROUP BY H3_RES8, SECTOR_ID;" in cluster_sql
    assert "GROUP BY H3_RES8, SECTOR_ID, INCIDENT_MINUTE" not in cluster_sql


def test_live_resource_gaps_use_aggregated_open_area_clusters():
    sql_text = SQL_PATH.read_text()
    gap_sql = _section_between(
        sql_text,
        "CREATE DYNAMIC TABLE IF NOT EXISTS LIVE_RESOURCE_GAPS",
        "-- ═══════════════════════════════════════════════════════════════════════════\n-- AGENT",
    )

    assert "open_area_clusters AS" in gap_sql
    assert "FROM DISASTER_DB.FEATURES.LIVE_H3_CLUSTER_WINDOWS" in gap_sql
    assert "FROM open_area_clusters" in gap_sql
    assert "QUALIFY ROW_NUMBER()" not in gap_sql


def test_render_init_sql_uses_configured_warehouse(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "OPS_WH")

    rendered = render_init_sql("WAREHOUSE = {{SNOWFLAKE_WAREHOUSE}}")

    assert rendered == "WAREHOUSE = OPS_WH"


def test_dynamic_table_statement_detection_and_graceful_errors():
    assert is_dynamic_table_statement("CREATE DYNAMIC TABLE IF NOT EXISTS X AS SELECT 1")
    assert is_dynamic_table_statement("DROP DYNAMIC TABLE IF EXISTS DISASTER_DB.FEATURES.X")
    assert is_dynamic_table_statement("SHOW DYNAMIC TABLES IN SCHEMA DISASTER_DB.GEO")
    assert is_graceful_dynamic_error(RuntimeError("insufficient privileges to create dynamic table"))
    assert not is_graceful_dynamic_error(RuntimeError("syntax error near SELECT"))


def test_run_init_sql_skips_dynamic_table_failures_and_continues():
    executed: list[str] = []

    class FakeCursor:
        def execute(self, statement: str) -> None:
            executed.append(statement)
            if "CREATE DYNAMIC TABLE" in statement:
                raise RuntimeError("insufficient privileges to create dynamic table")

        def close(self) -> None:
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    skipped = run_init_sql(
        FakeConnection(),
        """
        CREATE TABLE IF NOT EXISTS A (ID NUMBER);
        CREATE DYNAMIC TABLE IF NOT EXISTS B TARGET_LAG = '1 minute' WAREHOUSE = {{SNOWFLAKE_WAREHOUSE}} AS SELECT 1 AS ID;
        CREATE TABLE IF NOT EXISTS C (ID NUMBER);
        """,
    )

    assert len(skipped) == 1
    assert any("CREATE TABLE IF NOT EXISTS C" in statement for statement in executed)

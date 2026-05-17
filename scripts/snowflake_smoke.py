"""
Snowflake smoke test.

  uv run python scripts/snowflake_smoke.py            # connect + verify schema + run tiles
  uv run python scripts/snowflake_smoke.py --init     # also run DDL
  uv run python scripts/snowflake_smoke.py --seed     # also insert one synthetic incident

Exits 0 on green, 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from disaster.snowflake.connection import _connect_params, env_configured
from disaster.snowflake.tables import (
    REQUIRED_TABLES_BY_SCHEMA,
    SCHEMA_RAW,
    SCHEMA_CLEAN,
    SCHEMA_SERVING,
    database_name,
    qualified_table,
)
from disaster.snowflake.tiles import TILE_QUERIES

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def migrate_incidents_schema(cur, db: str) -> None:
    """Align CLEAN.INCIDENTS with current schema (INCIDENT_DESCRIPTION; no SOURCE/CONFIDENCE/VICTIM_COUNT)."""
    cur.execute(f"USE SCHEMA {SCHEMA_CLEAN}")
    cur.execute(
        f"""
        SELECT COLUMN_NAME
        FROM {db}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'INCIDENTS'
        """,
        (SCHEMA_CLEAN,),
    )
    cols = {row[0].upper() for row in cur.fetchall()}

    if "LOCATION_DESCRIPTION" in cols and "INCIDENT_DESCRIPTION" not in cols:
        cur.execute(
            "ALTER TABLE INCIDENTS RENAME COLUMN LOCATION_DESCRIPTION TO INCIDENT_DESCRIPTION"
        )
        cols.remove("LOCATION_DESCRIPTION")
        cols.add("INCIDENT_DESCRIPTION")
    elif "LOCATION_DESCRIPTION" in cols and "INCIDENT_DESCRIPTION" in cols:
        cur.execute(
            "UPDATE INCIDENTS SET INCIDENT_DESCRIPTION = LOCATION_DESCRIPTION "
            "WHERE INCIDENT_DESCRIPTION IS NULL"
        )
        cur.execute("ALTER TABLE INCIDENTS DROP COLUMN LOCATION_DESCRIPTION")
        cols.discard("LOCATION_DESCRIPTION")

    for col in ("SOURCE", "VICTIM_COUNT", "CONFIDENCE"):
        if col in cols:
            cur.execute(f"ALTER TABLE INCIDENTS DROP COLUMN {col}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Snowflake smoke test")
    parser.add_argument("--init", action="store_true", help="Run scripts/snowflake_init.sql before checks")
    parser.add_argument("--seed", action="store_true", help="Insert one synthetic incident + cortex alert")
    args = parser.parse_args()

    print("Snowflake smoke test")
    print("=" * 60)

    if not env_configured():
        fail("SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER + (PRIVATE_KEY_PATH or PASSWORD) not set")
        print("\nSet them in .env and re-run. See .env.example.")
        return 1
    ok("env vars present")

    auth_method = "key-pair" if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") else "password"
    ok(f"auth method: {auth_method}")

    try:
        import snowflake.connector
    except ImportError:
        fail("snowflake-connector-python not installed — run `make install`")
        return 1
    ok("snowflake-connector-python importable")

    try:
        conn = snowflake.connector.connect(**_connect_params())
    except Exception as e:  # noqa: BLE001
        fail(f"connect failed: {e}")
        return 1
    ok(f"connected to {os.environ['SNOWFLAKE_ACCOUNT']}")

    db = database_name()

    if args.init:
        sql_path = Path(__file__).resolve().parent / "snowflake_init.sql"
        sql_text = sql_path.read_text()
        cur = conn.cursor()
        try:
            for stmt in (s.strip() for s in sql_text.split(";") if s.strip()):
                cur.execute(stmt)
            ok("ran snowflake_init.sql")
            migrate_incidents_schema(cur, db)
            ok("migrated CLEAN.INCIDENTS location schema")
        except Exception as e:  # noqa: BLE001
            fail(f"DDL failed: {e}")
            return 1
        finally:
            cur.close()

    cur = conn.cursor()
    missing_all: list[str] = []
    try:
        for schema, tables in REQUIRED_TABLES_BY_SCHEMA.items():
            cur.execute(f"SHOW TABLES IN SCHEMA {db}.{schema}")
            existing = {row[1].upper() for row in cur.fetchall()}
            missing = [t for t in tables if t.upper() not in existing]
            if missing:
                missing_all.extend(f"{schema}.{t}" for t in missing)
            else:
                ok(f"schema {schema}: {len(tables)} required tables present")
    finally:
        cur.close()

    if missing_all:
        fail(f"missing tables: {missing_all}. Run with --init to create them.")
        return 1

    if args.seed:
        cur = conn.cursor()
        try:
            now = datetime.now(UTC)
            inc_id = str(uuid.uuid4())
            raw_fqn = qualified_table(f"{SCHEMA_RAW}.RAW_INCIDENT_SUBMISSIONS")
            payload = json.dumps({
                "id": inc_id,
                "timestamp": now.isoformat(),
                "source": "voice",
                "status": "new",
                "severity": "Immediate",
                "priority_score": 0.95,
                "confidence": 0.92,
                "location": {
                    "lat": 19.7320,
                    "lng": -155.0918,
                    "description": "Smoke test, Pier 4",
                },
                "victims": [{
                    "injuries": ["respiratory distress"],
                    "vulnerabilities": ["child"],
                    "consciousness": "alert",
                }],
            })
            cur.execute(
                f"""INSERT INTO {raw_fqn}
                (RAW_ID, SUBMISSION_ID, SOURCE, RECEIVED_AT, PAYLOAD, _SOURCE_SYSTEM)
                SELECT %s, %s, %s, %s, PARSE_JSON(%s), %s""",
                (str(uuid.uuid4()), inc_id, "voice", now, payload, "smoke_test"),
            )
            ok(f"inserted seed RAW incident submission id={inc_id[:8]}…")

            alerts_fqn = qualified_table(f"{SCHEMA_SERVING}.CORTEX_ALERTS")

            alert_payload = json.dumps({"source": "smoke"})
            cur.execute(
                f"""INSERT INTO {alerts_fqn}
                (ALERT_ID, ALERT_TYPE, SEVERITY, SECTOR_ID, PAYLOAD, MESSAGE, DETECTED_AT)
                SELECT %s, %s, %s, %s, PARSE_JSON(%s), %s, %s""",
                (str(uuid.uuid4()), "cluster", "warning", "CENTRAL",
                 alert_payload, "Smoke test cortex alert", now),
            )
            ok("inserted seed CORTEX_ALERTS row")
        except Exception as e:  # noqa: BLE001
            fail(f"seed insert failed: {e}")
            return 1
        finally:
            cur.close()

    print("\nRunning tile queries:")
    failures = 0
    for tile_name, sql in TILE_QUERIES.items():
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(sql)
            rows = cur.fetchall() or []
            ok(f"{tile_name}: {len(rows)} rows")
            if rows:
                preview = json.dumps(rows[0], default=str)[:80]
                print(f"      first row: {preview}")
        except Exception as e:  # noqa: BLE001
            fail(f"{tile_name}: {e}")
            failures += 1
        finally:
            cur.close()

    print("\nRunning Cortex SQL cluster query:")
    try:
        from disaster.snowflake.cortex import CORTEX_CLUSTER_SQL
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(CORTEX_CLUSTER_SQL)
            rows = cur.fetchall() or []
            ok(f"cluster query: {len(rows)} cluster(s) found in last 5 minutes")
        finally:
            cur.close()
    except Exception as e:  # noqa: BLE001
        fail(f"cluster query: {e}")
        failures += 1

    conn.close()
    print()
    if failures:
        fail(f"{failures} failure(s)")
        return 1
    ok("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

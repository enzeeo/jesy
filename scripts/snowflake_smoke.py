"""
Snowflake smoke test.

  uv run python scripts/snowflake_smoke.py            # connect + verify schema + run tiles
  uv run python scripts/snowflake_smoke.py --init     # also run DDL
  uv run python scripts/snowflake_smoke.py --seed     # also insert one synthetic incident

Exits 0 on green, 1 on any failure. Prints a checklist so you see exactly
what was verified.

Required env vars (same as the app):
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
Optional (with defaults):
  SNOWFLAKE_WAREHOUSE=DISASTER_WH
  SNOWFLAKE_DATABASE=DISASTER_DB
  SNOWFLAKE_SCHEMA=OPERATIONAL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Allow running from project root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from disaster.snowflake.connection import _connect_params, env_configured
from disaster.snowflake.tiles import TILE_QUERIES

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Snowflake smoke test")
    parser.add_argument("--init", action="store_true", help="Run scripts/snowflake_init.sql before checks")
    parser.add_argument("--seed", action="store_true", help="Insert one synthetic incident + one cortex_alert row")
    args = parser.parse_args()

    print("Snowflake smoke test")
    print("=" * 60)

    if not env_configured():
        fail("SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER + (PRIVATE_KEY_PATH or PASSWORD) not set")
        print("\nSet them in .env and re-run. See .env.example.")
        print("For key-pair auth: uv run python scripts/snowflake_keypair_setup.py")
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

    # Connect
    try:
        conn = snowflake.connector.connect(**_connect_params())
    except Exception as e:  # noqa: BLE001
        fail(f"connect failed: {e}")
        return 1
    ok(f"connected to {os.environ['SNOWFLAKE_ACCOUNT']}")

    # Optional: run DDL
    if args.init:
        sql_path = Path(__file__).resolve().parent / "snowflake_init.sql"
        sql_text = sql_path.read_text()
        cur = conn.cursor()
        try:
            # Snowflake connector executes multiple statements via execute_string
            for stmt in (s.strip() for s in sql_text.split(";") if s.strip()):
                cur.execute(stmt)
            ok("ran snowflake_init.sql")
        except Exception as e:  # noqa: BLE001
            fail(f"DDL failed: {e}")
            return 1
        finally:
            cur.close()

    # Verify each required table exists
    required_tables = ["incidents", "voice_calls", "responder_dispatches", "cortex_alerts"]
    cur = conn.cursor()
    try:
        cur.execute("SHOW TABLES")
        existing = {row[1].lower() for row in cur.fetchall()}
        missing = [t for t in required_tables if t not in existing]
        if missing:
            fail(f"missing tables: {missing}. Run with --init to create them.")
            return 1
        ok(f"all 4 tables present: {required_tables}")
    finally:
        cur.close()

    # Optional: seed one row in each
    if args.seed:
        cur = conn.cursor()
        try:
            now = datetime.now(UTC)
            inc_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO incidents
                (id, timestamp, source, status, lat, lng, location_description,
                 severity, priority_score, victim_count, vulnerabilities,
                 confidence, sim_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (inc_id, now, "voice", "new", 19.7320, -155.0918, "Smoke test, Pier 4",
                 "Immediate", 0.95, 1, "child,trapped", 0.92, None),
            )
            ok(f"inserted seed incident id={inc_id[:8]}…")

            cur.execute(
                """INSERT INTO cortex_alerts
                (alert_type, severity, message, detected_at)
                VALUES (%s, %s, %s, %s)""",
                ("cluster", "warning", "Smoke test cortex alert", now),
            )
            ok("inserted seed cortex_alert")
        except Exception as e:  # noqa: BLE001
            fail(f"seed insert failed: {e}")
            return 1
        finally:
            cur.close()

    # Run each tile query
    print("\nRunning tile queries:")
    failures = 0
    for tile_name, sql in TILE_QUERIES.items():
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(sql)
            rows = cur.fetchall() or []
            ok(f"{tile_name}: {len(rows)} rows")
            if rows:
                # First row preview (truncated)
                preview = json.dumps(rows[0], default=str)[:80]
                print(f"      first row: {preview}")
        except Exception as e:  # noqa: BLE001
            fail(f"{tile_name}: {e}")
            failures += 1
        finally:
            cur.close()

    # Run the Cortex SQL cluster query (used by /cortex/scan when configured)
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

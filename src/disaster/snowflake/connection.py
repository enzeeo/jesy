"""
Snowflake connection helpers.

The connector is sync; we wrap it in run_in_executor so the writer worker
can await without blocking the event loop. Connection params come from env:

  SNOWFLAKE_ACCOUNT             e.g. abcd-xy12345
  SNOWFLAKE_USER
  SNOWFLAKE_WAREHOUSE           default DISASTER_WH
  SNOWFLAKE_DATABASE            default DISASTER_DB
  SNOWFLAKE_SCHEMA              default OPERATIONAL

Pick ONE auth method:
  SNOWFLAKE_PRIVATE_KEY_PATH    path to PKCS#8 .p8 file (recommended for teams)
  SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  optional, if the key is encrypted
  OR
  SNOWFLAKE_PASSWORD            legacy password auth

Key-pair beats passwords for teams: each developer has their own private key
on their own machine, never shared, never committed. To set up your key:

  uv run python scripts/snowflake_keypair_setup.py

When the required env vars are missing, callers get a no-op flush instead.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from disaster.errors import SnowflakeWriteError

log = logging.getLogger(__name__)


# Column order per table — used for executemany INSERT.
_SCHEMAS: dict[str, list[str]] = {
    "incidents": [
        "id", "timestamp", "source", "status",
        "lat", "lng", "location_description",
        "severity", "priority_score",
        "victim_count", "vulnerabilities",
        "confidence", "sim_run_id",
    ],
    "voice_calls": [
        "incident_id", "transcript_length", "model", "tokens",
    ],
    "responder_dispatches": [
        "responder_id", "incident_id", "dispatched_at",
        "distance_km", "eta_seconds", "solver", "sim_run_id",
    ],
    "cortex_alerts": [
        "alert_type", "severity", "message", "detected_at",
    ],
}


def _row_to_columns(table: str, row: dict[str, Any]) -> list[Any]:
    """
    Flatten the IncidentReport dict shape to ordered columns for the table.
    Idempotent across multiple writes of the same incident.
    """
    cols = _SCHEMAS[table]
    if table == "incidents":
        loc = row.get("location") or {}
        victims = row.get("victims") or []
        vulns = sorted({v for vt in victims for v in (vt.get("vulnerabilities") or [])})
        return [
            row.get("id"),
            row.get("timestamp"),
            row.get("source"),
            row.get("status"),
            loc.get("lat"),
            loc.get("lng"),
            loc.get("description"),
            row.get("severity"),
            row.get("priority_score"),
            len(victims),
            ",".join(vulns),
            row.get("confidence"),
            row.get("sim_run_id"),
        ]
    return [row.get(c) for c in cols]


def env_configured() -> bool:
    """True iff ACCOUNT + USER are set AND at least one auth method is configured."""
    if not (os.environ.get("SNOWFLAKE_ACCOUNT") and os.environ.get("SNOWFLAKE_USER")):
        return False
    return bool(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") or os.environ.get("SNOWFLAKE_PASSWORD"))


def _load_private_key_bytes() -> bytes:
    """Load a PKCS#8 private key from disk, return DER bytes for snowflake-connector."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", "").encode() or None
    with open(path, "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=passphrase, backend=default_backend(),
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _connect_params() -> dict[str, Any]:
    """Assemble snowflake.connector.connect() kwargs from env. Picks key-pair over password."""
    params: dict[str, Any] = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "DISASTER_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "DISASTER_DB"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "OPERATIONAL"),
    }
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        params["private_key"] = _load_private_key_bytes()
        log.info("snowflake: using key-pair auth")
    else:
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        log.warning("snowflake: using password auth (consider key-pair instead)")
    return params


def build_snowflake_flush() -> Callable[[str, list[dict[str, Any]]], Awaitable[None]]:
    """
    Returns a flush function suitable for SnowflakeWriter(flush_fn=...).
    Lazily imports snowflake-connector to keep startup fast for non-Snowflake demos.
    """
    if not env_configured():
        raise RuntimeError("Snowflake env vars not set — call env_configured() first")

    import snowflake.connector

    params = _connect_params()
    conn = snowflake.connector.connect(**params)
    log.info("snowflake: connected account=%s db=%s schema=%s",
             params["account"], params["database"], params["schema"])

    def _sync_flush(table: str, rows: list[dict[str, Any]]) -> None:
        if not rows or table not in _SCHEMAS:
            return
        cols = _SCHEMAS[table]
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({placeholders})'
        params_list = [_row_to_columns(table, r) for r in rows]
        cur = conn.cursor()
        try:
            cur.executemany(sql, params_list)
        finally:
            cur.close()

    async def flush(table: str, rows: list[dict[str, Any]]) -> None:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _sync_flush, table, rows)
        except Exception as e:
            raise SnowflakeWriteError(f"{table} batch flush failed: {e}") from e

    return flush


def get_query_runner() -> Callable[[str, tuple], Awaitable[list[dict[str, Any]]]] | None:
    """
    Returns an async function that runs read-only queries against the same connection.
    None when Snowflake env not configured.
    """
    if not env_configured():
        return None

    import snowflake.connector

    conn = snowflake.connector.connect(**_connect_params())

    def _sync_query(sql: str, params: tuple) -> list[dict[str, Any]]:
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(sql, params)
            return cur.fetchall() or []
        finally:
            cur.close()

    async def runner(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_query, sql, params)

    return runner

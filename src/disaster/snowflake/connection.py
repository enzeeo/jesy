"""
Snowflake connection helpers.

The connector is sync; we wrap it in run_in_executor so the writer worker
can await without blocking the event loop. Connection params come from env:

  SNOWFLAKE_ACCOUNT             e.g. abcd-xy12345
  SNOWFLAKE_USER
  SNOWFLAKE_WAREHOUSE           default DISASTER_WH
  SNOWFLAKE_DATABASE            default DISASTER_DB
  SNOWFLAKE_SCHEMA              default CLEAN (session default; writes use FQN)
  SNOWFLAKE_ROLE                optional, e.g. TRAINING_ROLE

Pick ONE auth method:
  SNOWFLAKE_PASSWORD            password or programmatic access token (PAT)
  SNOWFLAKE_PRIVATE_KEY_PATH    path to PKCS#8 .p8 file (recommended for teams)
  SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  optional, if the key is encrypted
  OR
  SNOWFLAKE_PASSWORD            legacy password auth

Table keys are ``{SCHEMA}.{TABLE}`` — see disaster.snowflake.tables.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from disaster.errors import SnowflakeWriteError
from disaster.snowflake.tables import (
    SCHEMA_CLEAN,
    SCHEMA_RAW,
    TABLE_COLUMNS,
    WRITABLE_TABLES,
    qualified_table,
)

_RAW_INCIDENTS_KEY = f"{SCHEMA_RAW}.RAW_INCIDENT_SUBMISSIONS"
_VICTIMS_KEY = f"{SCHEMA_CLEAN}.VICTIMS"

log = logging.getLogger(__name__)

# Re-export for tests and smoke scripts.
_SCHEMAS = TABLE_COLUMNS


# VARIANT via JSON string (executemany cannot bind Python dict for PAYLOAD).
_VARIANT_JSON_COLUMNS = frozenset({
    "PAYLOAD", "OVERRIDE_PAYLOAD", "FEATURE_COLLECTION", "STATUS_COUNTS", "GEOMETRY",
    "PROPERTIES", "POLYGON", "ROUTE_GEOM", "H3_CELLS_RES8",
    "RESPONDERS", "INCIDENTS", "CLUSTERS", "ROAD_ACCESS", "ACCEPTED_ASSIGNMENTS",
    "INPUT_INCIDENT_IDS", "INPUT_CLUSTER_IDS", "INPUT_RESPONDER_IDS",
    "MEMBER_INCIDENT_IDS",
    "ROAD_ACCESS_SUMMARY", "UNASSIGNED", "ALTERNATIVES", "LEG", "ROUTE_GEOMETRY",
    "WARNINGS", "TOOL_CALLS", "CITATIONS", "INPUT_PAYLOAD", "OUTPUT_PAYLOAD",
    "CORTEX_SEARCH_HITS",
})

# Snowflake ARRAY columns — bind Python list, not comma-separated VARCHAR.
_ARRAY_COLUMNS = frozenset({
    "VULNERABILITIES", "INJURIES",
})


def _coerce_value(col: str, value: Any) -> Any:
    """Coerce Python values to Snowflake bind types."""
    if value is None:
        return None
    if col in _ARRAY_COLUMNS:
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return []
    if col in _VARIANT_JSON_COLUMNS:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _insert_placeholders(cols: list[str]) -> str:
    """Snowflake executemany cannot bind dict/list into VARIANT — use PARSE_JSON on JSON text."""
    return ", ".join(
        "PARSE_JSON(%s)" if col in _VARIANT_JSON_COLUMNS else "%s"
        for col in cols
    )


def _row_to_columns(table_key: str, row: dict[str, Any]) -> list[Any]:
    """
    Map a logical row dict (snake_case or UPPER keys) to ordered INSERT values.
    """
    cols = TABLE_COLUMNS[table_key]
    out: list[Any] = []
    for col in cols:
        # Accept UPPER (canonical) or lower_snake aliases.
        key_upper = col
        key_lower = col.lower()
        val = row.get(key_upper)
        if val is None and key_lower in row:
            val = row[key_lower]
        out.append(_coerce_value(col, val))
    return out


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
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", SCHEMA_CLEAN),
    }
    if role := os.environ.get("SNOWFLAKE_ROLE"):
        params["role"] = role
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        params["private_key"] = _load_private_key_bytes()
        log.info("snowflake: using key-pair auth")
    else:
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        log.info("snowflake: using password/PAT auth")
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
    log.info(
        "snowflake: connected account=%s db=%s default_schema=%s",
        params["account"],
        params["database"],
        params["schema"],
    )

    def _json_param(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def _flush_raw_incidents(cur: Any, fqn: str, rows: list[dict[str, Any]]) -> None:
        sql = f"""
            INSERT INTO {fqn}
            (RAW_ID, SUBMISSION_ID, SOURCE, RECEIVED_AT, PAYLOAD, _SOURCE_SYSTEM)
            SELECT %s, %s, %s, %s, PARSE_JSON(%s), %s
        """
        params_list = [
            [
                r.get("RAW_ID"),
                r.get("SUBMISSION_ID"),
                r.get("SOURCE"),
                r.get("RECEIVED_AT"),
                _json_param(r.get("PAYLOAD")),
                r.get("_SOURCE_SYSTEM"),
            ]
            for r in rows
        ]
        for params in params_list:
            cur.execute(sql, params)

    def _flush_victims(cur: Any, fqn: str, rows: list[dict[str, Any]]) -> None:
        sql = f"""
            INSERT INTO {fqn}
            (INCIDENT_ID, VICTIM_ORDINAL, AGE_BAND, VULNERABILITIES, INJURIES,
             CONSCIOUSNESS, EXTRACTED_AT)
            SELECT %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, %s
        """
        params_list = []
        for r in rows:
            vulns = r.get("VULNERABILITIES", [])
            injuries = r.get("INJURIES", [])
            if isinstance(vulns, str):
                vulns = [v.strip() for v in vulns.split(",") if v.strip()]
            if isinstance(injuries, str):
                injuries = [v.strip() for v in injuries.split(",") if v.strip()]
            params_list.append([
                r.get("INCIDENT_ID"),
                r.get("VICTIM_ORDINAL"),
                r.get("AGE_BAND"),
                _json_param(vulns if isinstance(vulns, list) else []),
                _json_param(injuries if isinstance(injuries, list) else []),
                r.get("CONSCIOUSNESS"),
                r.get("EXTRACTED_AT"),
            ])
        for params in params_list:
            cur.execute(sql, params)

    def _sync_flush(table_key: str, rows: list[dict[str, Any]]) -> None:
        if not rows or table_key not in TABLE_COLUMNS:
            return
        if table_key not in WRITABLE_TABLES:
            log.warning("snowflake: skip non-writable table %s", table_key)
            return
        fqn = qualified_table(table_key)
        cur = conn.cursor()
        try:
            if table_key == _RAW_INCIDENTS_KEY:
                _flush_raw_incidents(cur, fqn, rows)
            elif table_key == _VICTIMS_KEY:
                _flush_victims(cur, fqn, rows)
            else:
                cols = TABLE_COLUMNS[table_key]
                sql = (
                    f'INSERT INTO {fqn} ({", ".join(cols)}) '
                    f"VALUES ({_insert_placeholders(cols)})"
                )
                params_list = [_row_to_columns(table_key, r) for r in rows]
                cur.executemany(sql, params_list)
        finally:
            cur.close()

    async def flush(table_key: str, rows: list[dict[str, Any]]) -> None:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _sync_flush, table_key, rows)
        except Exception as e:
            raise SnowflakeWriteError(f"{table_key} batch flush failed: {e}") from e

    return flush


_POOL_SIZE = 4               # parallel connections; tune up if dashboard polling is heavy
_POOL_ACQUIRE_TIMEOUT_S = 3  # bail rather than block forever if every conn is sick


class SnowflakeQueryPool:
    """
    Pool of N independent Snowflake connections, served by a sized
    ThreadPoolExecutor. Replaces the previous single shared connection that
    deadlocked the entire query path whenever Snowflake half-closed a session
    (CLOSE_WAIT accumulation -> next cursor blocks forever -> /healthz dies
    once asyncio's executor pool fills up).

    Behavior:
      - Each query acquires one connection from a thread-safe queue, runs to
        completion in its dedicated executor thread, returns the conn on
        success.
      - On exception (timeout from upstream asyncio.wait_for, query error,
        socket reset) the conn is closed and a fresh one is put back in its
        place. One bad query costs 1/N capacity for ~1 query duration, not
        the whole pool.
      - If a brand-new connection can't be opened (network down, auth flake),
        the slot stays empty until the next successful refill. ``acquire``
        times out rather than blocking forever so callers can fall back.

    Threading model:
      - Connections live in worker threads via a queue.Queue (thread-safe).
      - Async callers schedule work onto the executor with run_in_executor;
        if the asyncio coroutine is cancelled, the thread runs to completion
        and the conn is returned, so cancellation doesn't leak conns.
    """

    def __init__(self, connect_fn: Callable[[], Any], size: int = _POOL_SIZE) -> None:
        import queue as _queue
        from concurrent.futures import ThreadPoolExecutor

        self._connect = connect_fn
        self._size = size
        self._executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="sf-query")
        self._conns: _queue.Queue = _queue.Queue(maxsize=size)
        opened = 0
        for _ in range(size):
            try:
                self._conns.put_nowait(connect_fn())
                opened += 1
            except Exception as e:  # noqa: BLE001
                log.warning("snowflake: pool warm-up conn failed (%s)", e)
        log.info("snowflake: query pool ready (size=%d, opened=%d)", size, opened)

    def _sync_execute(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        import queue as _queue

        import snowflake.connector

        try:
            conn = self._conns.get(timeout=_POOL_ACQUIRE_TIMEOUT_S)
        except _queue.Empty as e:
            raise TimeoutError("snowflake pool exhausted") from e

        try:
            cur = conn.cursor(snowflake.connector.DictCursor)
            try:
                cur.execute(sql, params)
                rows = cur.fetchall() or []
            finally:
                cur.close()
        except Exception:
            # Treat any failure as "this conn is suspect"; close it, try to
            # replace with a fresh one. If reconnect fails, the slot shrinks
            # until backend restart.
            with contextlib.suppress(Exception):
                conn.close()
            try:
                self._conns.put_nowait(self._connect())
            except Exception as connect_err:  # noqa: BLE001
                log.warning("snowflake: pool refill failed (%s) — capacity reduced", connect_err)
            raise
        else:
            self._conns.put_nowait(conn)
            return rows

    async def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._sync_execute, sql, params)


def get_query_runner() -> Callable[[str, tuple], Awaitable[list[dict[str, Any]]]] | None:
    """
    Returns an async function backed by a connection pool. None when Snowflake
    env not configured.

    The returned callable closes over the pool, so the pool stays alive for
    the lifetime of the app. AAR + tile + cortex endpoints all share the same
    pool but no single bad query can wedge the others.
    """
    if not env_configured():
        return None

    import snowflake.connector

    def _connect() -> Any:
        return snowflake.connector.connect(**_connect_params())

    pool = SnowflakeQueryPool(_connect)
    return pool.query

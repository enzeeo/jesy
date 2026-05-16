"""Tests for snowflake_writer async queue (P1 #2)."""
from __future__ import annotations

import asyncio
from typing import Any

from disaster.errors import SnowflakeWriteError
from disaster.snowflake import SnowflakeWriter


def _collecting_flush():
    """Returns (flush_fn, collected_dict[table -> list[rows]])."""
    collected: dict[str, list[dict[str, Any]]] = {}

    async def fn(table: str, rows: list[dict[str, Any]]) -> None:
        collected.setdefault(table, []).extend(rows)

    return fn, collected


def _failing_flush(err: Exception):
    async def fn(_table: str, _rows: list[dict[str, Any]]) -> None:
        raise err

    return fn


# ── write() is non-blocking ──────────────────────────────────────────────────

async def test_write_does_not_await():
    """write() must NOT be a coroutine — it's called from sync request paths."""
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush)
    # Should NOT raise TypeError about un-awaited coroutine
    w.write("incidents", {"id": 1})
    assert w.metrics.enqueued == 1


# ── Happy path: batch flush ──────────────────────────────────────────────────

async def test_batch_flushes_on_size():
    flush, collected = _collecting_flush()
    w = SnowflakeWriter(flush, batch_size=3, flush_interval_s=60.0)
    await w.start()
    try:
        for i in range(3):
            w.write("incidents", {"id": i})
        # Let the worker process at least one tick
        await asyncio.sleep(0.1)
        assert len(collected.get("incidents", [])) == 3
        assert w.metrics.flushed == 3
    finally:
        await w.stop()


async def test_batch_flushes_on_interval_even_below_size():
    flush, collected = _collecting_flush()
    w = SnowflakeWriter(flush, batch_size=100, flush_interval_s=0.1)
    await w.start()
    try:
        w.write("incidents", {"id": 1})
        w.write("incidents", {"id": 2})
        await asyncio.sleep(0.25)   # > flush_interval_s
        assert len(collected.get("incidents", [])) == 2
    finally:
        await w.stop()


# ── Queue full drops with counter ────────────────────────────────────────────

async def test_queue_full_drops_and_increments_counter():
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush, max_queue=3, batch_size=100, flush_interval_s=60.0)
    # Don't start the worker → queue fills up
    w.write("incidents", {"id": 1})
    w.write("incidents", {"id": 2})
    w.write("incidents", {"id": 3})
    assert w.metrics.dropped_count == 0
    # 4th overflows
    w.write("incidents", {"id": 4})
    w.write("voice_calls", {"id": 100})
    assert w.metrics.dropped_count == 2
    assert w.metrics.per_table_dropped["incidents"] == 1
    assert w.metrics.per_table_dropped["voice_calls"] == 1


async def test_write_never_blocks_under_load():
    """100 writes in sequence — should all return synchronously, never await."""
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush, max_queue=10, batch_size=100, flush_interval_s=60.0)
    # Don't start the worker. 90 writes get dropped, but ALL return immediately.
    for i in range(100):
        w.write("incidents", {"id": i})
    assert w.metrics.enqueued == 10
    assert w.metrics.dropped_count == 90


# ── Multi-table batching ─────────────────────────────────────────────────────

async def test_per_table_batching_is_independent():
    flush, collected = _collecting_flush()
    w = SnowflakeWriter(flush, batch_size=2, flush_interval_s=60.0)
    await w.start()
    try:
        w.write("incidents", {"id": 1})
        w.write("voice_calls", {"id": 100})
        w.write("incidents", {"id": 2})
        w.write("voice_calls", {"id": 101})
        await asyncio.sleep(0.1)
        assert len(collected.get("incidents", [])) == 2
        assert len(collected.get("voice_calls", [])) == 2
    finally:
        await w.stop()


# ── Worker lifecycle ─────────────────────────────────────────────────────────

async def test_stop_drains_pending_rows():
    flush, collected = _collecting_flush()
    w = SnowflakeWriter(flush, batch_size=100, flush_interval_s=60.0)
    await w.start()
    w.write("incidents", {"id": 1})
    w.write("incidents", {"id": 2})
    await w.stop()
    # Drained on shutdown
    assert len(collected.get("incidents", [])) == 2


async def test_start_is_idempotent():
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush)
    await w.start()
    await w.start()   # second call must not spawn a duplicate task
    await w.stop()


async def test_stop_when_not_started_is_safe():
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush)
    await w.stop()  # no-op


# ── Flush errors don't kill the worker ───────────────────────────────────────

async def test_flush_error_increments_counter_and_keeps_running():
    flush = _failing_flush(SnowflakeWriteError("warehouse offline"))
    w = SnowflakeWriter(flush, batch_size=2, flush_interval_s=60.0)
    await w.start()
    try:
        w.write("incidents", {"id": 1})
        w.write("incidents", {"id": 2})   # triggers batch flush, which fails
        await asyncio.sleep(0.1)
        assert w.metrics.flush_errors == 1
        # Worker is still alive
        w.write("incidents", {"id": 3})
        w.write("incidents", {"id": 4})   # another batch → another failure
        await asyncio.sleep(0.1)
        assert w.metrics.flush_errors == 2
    finally:
        await w.stop()


# ── Metrics snapshot ─────────────────────────────────────────────────────────

async def test_metrics_snapshot_serializable():
    flush, _ = _collecting_flush()
    w = SnowflakeWriter(flush)
    w.write("incidents", {"id": 1})
    snap = w.metrics.snapshot()
    assert snap["enqueued"] == 1
    assert snap["dropped_count"] == 0
    assert "per_table_dropped" in snap


# ── Backpressure does not propagate ──────────────────────────────────────────

async def test_slow_flush_does_not_block_writes():
    """
    Even if the flush function hangs, write() still returns immediately.
    This is the core invariant: Snowflake stalls never reach the request path.
    """
    block = asyncio.Event()

    async def slow_flush(_t: str, _r: list[dict[str, Any]]) -> None:
        await block.wait()

    w = SnowflakeWriter(slow_flush, max_queue=100, batch_size=2, flush_interval_s=60.0)
    await w.start()
    try:
        # 50 writes while the worker is stuck on flush — all sync, all succeed
        for i in range(50):
            w.write("incidents", {"id": i})
        assert w.metrics.enqueued == 50
        # Let the test finish by unblocking
        block.set()
        await asyncio.sleep(0.05)
    finally:
        block.set()
        await w.stop(drain_timeout_s=0.5)

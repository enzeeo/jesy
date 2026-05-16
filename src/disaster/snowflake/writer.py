"""
Snowflake async writer.

  /incidents handler          ┌──── BoundedQueue (maxsize=10k) ────┐
       │                      │                                    │
       │ put_nowait(...)  ───▶│  (table, row) (table, row) ...     │──▶ worker
       │ never awaits          │                                    │     │
       │                      └────────────────────────────────────┘     │
       │                                                                  │
       ▼                                                                  ▼
   QueueFull → drop + counter                              batch flush every 5s
                                                           or when batch hits 50

Operational invariants:
  - put() NEVER blocks the calling coroutine (no `await q.put`)
  - On QueueFull, row is dropped and dropped_count incremented
  - Worker runs as an asyncio.Task in the FastAPI lifespan
  - Stop() drains the queue with a deadline, never hangs shutdown forever
  - Per-table batching; flushes interleaved tables independently
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from disaster.errors import SnowflakeWriteError

log = logging.getLogger(__name__)


@dataclass
class WriterMetrics:
    enqueued: int = 0
    flushed: int = 0
    dropped_count: int = 0
    flush_errors: int = 0
    last_flush_ts: float | None = None
    queue_depth: int = 0
    per_table_dropped: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def snapshot(self) -> dict[str, Any]:
        return {
            "enqueued": self.enqueued,
            "flushed": self.flushed,
            "dropped_count": self.dropped_count,
            "flush_errors": self.flush_errors,
            "last_flush_ts": self.last_flush_ts,
            "queue_depth": self.queue_depth,
            "per_table_dropped": dict(self.per_table_dropped),
        }


# Pluggable executor: production wires it to snowflake-connector executemany.
# Tests inject a fake.
FlushFn = Callable[[str, list[dict[str, Any]]], Awaitable[None]]


class SnowflakeWriter:
    def __init__(
        self,
        flush_fn: FlushFn,
        *,
        max_queue: int = 10_000,
        batch_size: int = 50,
        flush_interval_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._flush_fn = flush_fn
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=max_queue)
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_s
        self._clock = clock
        self.metrics = WriterMetrics()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    # ── Public API ───────────────────────────────────────────────────────────

    def write(self, table: str, row: dict[str, Any]) -> None:
        """
        Non-blocking. Returns immediately. On overflow, drops the row and
        increments dropped_count. NEVER raises into the request path.
        """
        try:
            self._queue.put_nowait((table, row))
            self.metrics.enqueued += 1
            self.metrics.queue_depth = self._queue.qsize()
        except asyncio.QueueFull:
            self.metrics.dropped_count += 1
            self.metrics.per_table_dropped[table] += 1
            log.warning("snowflake_writer: queue full, dropping row for table=%s", table)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="snowflake-writer")

    async def stop(self, drain_timeout_s: float = 5.0) -> None:
        """Signal shutdown, drain remaining items up to deadline, then cancel."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=drain_timeout_s)
        except TimeoutError:
            log.warning("snowflake_writer: drain timed out, cancelling worker")
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None

    # ── Worker loop ──────────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Pull items, batch per-table, flush on size or interval."""
        pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
        last_flush = self._clock()

        try:
            while not (self._stop_event.is_set() and self._queue.empty() and not any(pending.values())):
                timeout = max(0.0, self._flush_interval_s - (self._clock() - last_flush))
                try:
                    table, row = await asyncio.wait_for(self._queue.get(), timeout=timeout or 0.01)
                    pending[table].append(row)
                    self.metrics.queue_depth = self._queue.qsize()
                except TimeoutError:
                    pass

                # Size-based flush per table
                for table in list(pending.keys()):
                    if len(pending[table]) >= self._batch_size:
                        await self._flush_one(table, pending[table])
                        pending[table] = []

                # Interval-based flush across all tables
                if (self._clock() - last_flush) >= self._flush_interval_s:
                    for table, rows in list(pending.items()):
                        if rows:
                            await self._flush_one(table, rows)
                            pending[table] = []
                    last_flush = self._clock()

                # If shutting down, drain remaining without further waiting
                if self._stop_event.is_set():
                    while not self._queue.empty():
                        table, row = self._queue.get_nowait()
                        pending[table].append(row)
                    for table, rows in list(pending.items()):
                        if rows:
                            await self._flush_one(table, rows)
                            pending[table] = []
                    break
        except asyncio.CancelledError:
            log.info("snowflake_writer: worker cancelled")
            raise

    async def _flush_one(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            await self._flush_fn(table, rows)
            self.metrics.flushed += len(rows)
            self.metrics.last_flush_ts = self._clock()
        except SnowflakeWriteError as e:
            self.metrics.flush_errors += 1
            # Sim writes are not authoritative for demo: drop the batch.
            log.error("snowflake_writer: flush failed for table=%s rows=%d err=%s", table, len(rows), e)

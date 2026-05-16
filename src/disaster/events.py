"""
SSE event broker.

  publisher (route handler)              subscribers (SSE clients)
       │                                        │
       │ broker.publish({...})                  │
       ▼                                        │
  asyncio.Queue (per subscriber)  ─── fan out ──▶ async generators yield
       │
       │ if subscriber slow:
       │   drop oldest events
       │   increment dropped_per_subscriber
       └─────────────────────────────────────────

Single-writer, multi-reader. Each SSE connection gets its own bounded queue;
slow consumers drop events instead of backing pressure into the publisher.
Maintains a monotonically increasing sequence_id used by severity_upgraded
events for frontend dedupe (P1 #8 server side).
"""
from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)


class EventBroker:
    def __init__(self, *, per_subscriber_queue: int = 256) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._per_subscriber_queue = per_subscriber_queue
        self._seq = itertools.count(1)
        self._dropped = 0
        self._lock = asyncio.Lock()

    def next_sequence_id(self) -> int:
        return next(self._seq)

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event: dict[str, Any]) -> None:
        """Fan event out to all subscribers. Slow subscribers drop oldest."""
        async with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest, keep newest
                    with contextlib.suppress(asyncio.QueueEmpty):
                        q.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(event)
                    self._dropped += 1
                    log.warning("event_broker: subscriber queue full, dropped event")

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Generator: yields events until consumer disconnects."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._per_subscriber_queue)
        async with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

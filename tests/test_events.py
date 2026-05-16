"""Tests for the SSE EventBroker."""
from __future__ import annotations

import asyncio

from disaster.events import EventBroker


async def test_publish_to_zero_subscribers_drops_silently():
    b = EventBroker()
    await b.publish({"type": "ping"})
    assert b.dropped == 0  # no subscribers means no overflow


async def test_subscriber_receives_published_event():
    b = EventBroker()

    async def consume():
        async for event in b.subscribe():
            return event

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await b.publish({"type": "incident_created", "data": {"id": 1}})
    result = await asyncio.wait_for(task, timeout=0.5)
    assert result == {"type": "incident_created", "data": {"id": 1}}


async def test_multiple_subscribers_all_receive():
    b = EventBroker()
    received_a: list = []
    received_b: list = []

    async def consume(target: list):
        async for event in b.subscribe():
            target.append(event)
            if len(target) >= 2:
                return

    ta = asyncio.create_task(consume(received_a))
    tb = asyncio.create_task(consume(received_b))
    await asyncio.sleep(0.01)
    await b.publish({"type": "e1"})
    await b.publish({"type": "e2"})
    await asyncio.gather(ta, tb)
    assert received_a == [{"type": "e1"}, {"type": "e2"}]
    assert received_b == [{"type": "e1"}, {"type": "e2"}]


async def test_subscriber_removed_after_iterator_closes():
    """When a consumer closes the iterator (or it's GC'd), the broker unregisters it."""
    b = EventBroker()

    agen = b.subscribe()
    # Consume one event so the generator suspends inside the loop
    consumer_task = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.01)
    assert b.subscriber_count == 1
    await b.publish({"type": "x"})
    await consumer_task
    # Now actively close — drives the finally block
    await agen.aclose()
    assert b.subscriber_count == 0


async def test_sequence_id_is_monotonic():
    b = EventBroker()
    ids = [b.next_sequence_id() for _ in range(5)]
    assert ids == [1, 2, 3, 4, 5]


async def test_slow_subscriber_drops_oldest_not_publisher_blocks():
    """A slow subscriber whose queue fills should NOT block publish()."""
    b = EventBroker(per_subscriber_queue=2)

    # Subscribe but never consume
    async def never_consume():
        async for _ in b.subscribe():
            await asyncio.sleep(60)  # consumer is "stuck"

    _stuck = asyncio.create_task(never_consume())  # noqa: RUF006 — intentionally leaked for test
    await asyncio.sleep(0.01)

    # Publish 10 events; each publish must return quickly
    for i in range(10):
        await asyncio.wait_for(b.publish({"type": f"e{i}"}), timeout=0.1)

    assert b.dropped > 0  # confirmed: events were dropped, publisher not blocked

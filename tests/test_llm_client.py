"""Tests for the simplified LLMClient (post-Tensormesh)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from disaster.errors import UpstreamUnavailable
from disaster.llm import LLMClient


def _ok(content: str = "ok", tokens: int = 42):
    async def fn(_p: str, _k: dict[str, Any]) -> dict[str, Any]:
        return {"content": content, "tokens": tokens}
    return fn


def _fail(msg: str = "down"):
    async def fn(_p: str, _k: dict[str, Any]) -> dict[str, Any]:
        raise UpstreamUnavailable(msg)
    return fn


async def test_happy_path_records_metrics():
    c = LLMClient(_ok("hello", tokens=10))
    result = await c.call("prompt")
    assert result["content"] == "hello"
    assert c.metrics.calls == 1
    assert c.metrics.total_tokens == 10
    assert c.metrics.failures == 0
    assert c.metrics.last_latency_ms >= 0


async def test_failure_propagates_and_increments_counter():
    c = LLMClient(_fail("openai 503"))
    with pytest.raises(UpstreamUnavailable):
        await c.call("prompt")
    assert c.metrics.failures == 1
    assert c.metrics.calls == 0


async def test_metrics_snapshot_is_serializable():
    c = LLMClient(_ok("x"))
    await c.call("p")
    snap = c.metrics.snapshot()
    assert snap["model"] == "gpt-4o-mini"
    assert snap["calls"] == 1
    assert "total_tokens" in snap


async def test_concurrent_calls_count_correctly():
    c = LLMClient(_ok("x", tokens=5))
    await asyncio.gather(*(c.call(f"p{i}") for i in range(10)))
    assert c.metrics.calls == 10
    assert c.metrics.total_tokens == 50


async def test_custom_model_label():
    c = LLMClient(_ok("x"), model="gpt-4o")
    assert c.metrics.model == "gpt-4o"
    await c.call("p")
    assert c.metrics.snapshot()["model"] == "gpt-4o"

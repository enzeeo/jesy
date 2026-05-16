"""
LLM client (OpenAI only).

  call(prompt)
        │
        ▼
  CompletionFn ─▶ OpenAI Chat Completions ─▶ {"content": str, "tokens": int}
        │
        ▼
  metrics.calls++  metrics.last_latency_ms  metrics.total_tokens

The router/failover machinery was stripped when Tensormesh was removed. If
multi-backend resilience comes back, restore the state-machine pattern from
git history (commit prior to "strip tensormesh").
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from disaster.errors import UpstreamUnavailable

log = logging.getLogger(__name__)


@dataclass
class ClientMetrics:
    """Snapshot fed to the infra panel via SSE."""
    model: str = "gpt-4o-mini"
    calls: int = 0
    failures: int = 0
    total_tokens: int = 0
    last_latency_ms: float = 0.0
    last_failure_ts: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.calls,
            "failures": self.failures,
            "total_tokens": self.total_tokens,
            "last_latency_ms": self.last_latency_ms,
            "last_failure_ts": self.last_failure_ts,
        }


CompletionFn = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class LLMClient:
    """
    Thin async wrapper around a completion function. DI-friendly: inject a fake
    in tests, the real OpenAI client at startup.
    """

    def __init__(
        self,
        completion: CompletionFn,
        *,
        model: str = "gpt-4o-mini",
        clock: Callable[[], float] = time.monotonic,
    ):
        self._completion = completion
        self.metrics = ClientMetrics(model=model)
        self._clock = clock
        self._lock = asyncio.Lock()

    async def call(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """
        Returns {"content": str, "tokens": int (optional)}.
        Raises UpstreamUnavailable on connection-level failure.
        """
        t0 = self._clock()
        try:
            result = await self._completion(prompt, kwargs)
        except UpstreamUnavailable:
            async with self._lock:
                self.metrics.failures += 1
                self.metrics.last_failure_ts = self._clock()
            raise

        latency_ms = (self._clock() - t0) * 1000.0
        async with self._lock:
            self.metrics.calls += 1
            self.metrics.last_latency_ms = latency_ms
            tokens = result.get("tokens")
            if isinstance(tokens, int):
                self.metrics.total_tokens += tokens
        return result

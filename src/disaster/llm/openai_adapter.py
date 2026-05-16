"""
OpenAI Chat Completions adapter for LLMClient.

  build_openai_completion(api_key, model) ─▶ CompletionFn
        │                                         │
        │                                         ▼
        │                              async (prompt, kwargs) -> {content, tokens}
        ▼
   wraps httpx.AsyncClient, calls /v1/chat/completions with
   response_format=json_object, raises UpstreamUnavailable on 5xx / network.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from disaster.errors import UpstreamUnavailable

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.openai.com/v1"
_RESPONSE_TIMEOUT_S = 30.0


def build_openai_completion(
    api_key: str,
    *,
    model: str = "gpt-4o-mini",
    base_url: str = _DEFAULT_BASE,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_s: float = _RESPONSE_TIMEOUT_S,
) -> Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]:
    """
    Returns a completion function suitable for LLMClient(completion=...).

    Pass `transport=MockTransport(...)` in tests to avoid real network.
    """
    client = httpx.AsyncClient(
        base_url=base_url,
        transport=transport,
        timeout=timeout_s,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    async def completion(prompt: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": kwargs.get("model", model),
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": kwargs.get("temperature", 0.0),
        }
        max_tokens = kwargs.get("max_tokens")
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        try:
            resp = await client.post("/chat/completions", json=body)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            raise UpstreamUnavailable(f"openai network error: {e}") from e

        if resp.status_code >= 500:
            raise UpstreamUnavailable(f"openai {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 429:
            raise UpstreamUnavailable(f"openai rate limited: {resp.text[:200]}")
        if resp.status_code >= 400:
            # 4xx is a programming error, not an upstream failure — let the JSON
            # surface so the malformed-response path handles it.
            log.error("openai 4xx: %s", resp.text[:200])
            return {"content": "", "tokens": 0}

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return {"content": "", "tokens": 0}
        content = choices[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        return {"content": content, "tokens": int(tokens)}

    return completion


async def close_openai_completion(completion_fn: Callable) -> None:
    """No-op closer (kept for symmetry; client closes on GC).

    If you need explicit shutdown, call _client.aclose() on the bound client.
    """
    # Closure captures `client`; access via __closure__ for cleanup.
    if hasattr(completion_fn, "__closure__") and completion_fn.__closure__:
        for cell in completion_fn.__closure__:
            obj = cell.cell_contents
            if isinstance(obj, httpx.AsyncClient):
                await obj.aclose()
                return

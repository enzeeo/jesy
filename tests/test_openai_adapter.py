"""Tests for OpenAI adapter using httpx.MockTransport."""
from __future__ import annotations

import json

import httpx
import pytest

from disaster.errors import UpstreamUnavailable
from disaster.llm import LLMClient, build_openai_completion


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _ok_handler(content: str = '{"ok":true}', tokens: int = 42):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"][0]["content"]
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"total_tokens": tokens},
            },
        )
    return handler


async def test_happy_path_returns_content_and_tokens():
    fn = build_openai_completion("sk-test", transport=_mock_transport(_ok_handler()))
    result = await fn("hello", {})
    assert result["content"] == '{"ok":true}'
    assert result["tokens"] == 42


async def test_5xx_raises_upstream_unavailable():
    def handler(_request):
        return httpx.Response(503, text="service down")
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    with pytest.raises(UpstreamUnavailable, match="503"):
        await fn("hello", {})


async def test_rate_limit_raises_upstream_unavailable():
    def handler(_request):
        return httpx.Response(429, text="too many requests")
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    with pytest.raises(UpstreamUnavailable, match="rate limited"):
        await fn("hello", {})


async def test_4xx_returns_empty():
    """400 is a programmer error, surfaces as empty content (handled by EmptyExtraction)."""
    def handler(_request):
        return httpx.Response(400, text="bad request")
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    result = await fn("hello", {})
    assert result["content"] == ""


async def test_connect_error_raises_upstream_unavailable():
    def handler(_request):
        raise httpx.ConnectError("dns failed")
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    with pytest.raises(UpstreamUnavailable, match="network error"):
        await fn("hello", {})


async def test_authorization_header_set():
    captured = {}
    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 1},
        })
    fn = build_openai_completion("sk-my-key", transport=_mock_transport(handler))
    await fn("x", {})
    assert captured["auth"] == "Bearer sk-my-key"


async def test_integration_with_llm_client():
    """Wire the adapter into LLMClient and verify metrics update."""
    fn = build_openai_completion("sk-test", transport=_mock_transport(_ok_handler(tokens=100)))
    client = LLMClient(fn)
    await client.call("prompt")
    assert client.metrics.calls == 1
    assert client.metrics.total_tokens == 100


async def test_temperature_zero_default():
    """Deterministic extraction: temperature should default to 0."""
    captured = {}
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 1},
        })
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    await fn("x", {})
    assert captured["body"]["temperature"] == 0.0


async def test_empty_choices_handled():
    def handler(_request):
        return httpx.Response(200, json={"choices": [], "usage": {"total_tokens": 0}})
    fn = build_openai_completion("sk-test", transport=_mock_transport(handler))
    result = await fn("x", {})
    assert result["content"] == ""
    assert result["tokens"] == 0

"""Tests for the top-level exception handler (P1 #5)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from disaster.app.exception_handler import register
from disaster.errors import (
    EmptyExtraction,
    IncompleteAssessment,
    UpstreamUnavailable,
)


def _app_with(route_fn) -> FastAPI:
    app = FastAPI()
    register(app)
    app.get("/boom")(route_fn)
    return app


# ── Named errors get the right status ────────────────────────────────────────

def test_upstream_unavailable_returns_503():
    async def boom():
        raise UpstreamUnavailable("tensormesh down")
    client = TestClient(_app_with(boom))
    r = client.get("/boom")
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "UpstreamUnavailable"
    assert "tensormesh" in body["message"]
    assert body["request_id"]


def test_incomplete_assessment_returns_422():
    async def boom():
        raise IncompleteAssessment("victim data missing")
    client = TestClient(_app_with(boom))
    r = client.get("/boom")
    assert r.status_code == 422


def test_empty_extraction_returns_422():
    async def boom():
        raise EmptyExtraction("LLM returned nothing")
    client = TestClient(_app_with(boom))
    r = client.get("/boom")
    assert r.status_code == 422


# ── Unknown errors fall through to 500 ───────────────────────────────────────

def test_unknown_error_returns_500_with_request_id():
    async def boom():
        raise ValueError("genuinely unexpected")
    client = TestClient(_app_with(boom), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "InternalError"
    assert body["message"] == "An unexpected error occurred"
    assert body["request_id"]


def test_request_id_propagates_from_header():
    async def boom():
        raise UpstreamUnavailable("x")
    client = TestClient(_app_with(boom))
    r = client.get("/boom", headers={"x-request-id": "my-trace-123"})
    assert r.headers["x-request-id"] == "my-trace-123"
    assert r.json()["request_id"] == "my-trace-123"


# ── Ruff actually rejects blind except ───────────────────────────────────────

@pytest.fixture
def tmp_module(tmp_path: Path) -> Path:
    src = tmp_path / "bad.py"
    src.write_text(dedent('''
        def f():
            try:
                pass
            except Exception:
                pass
    '''))
    return src


def test_ruff_rejects_blind_except(tmp_module: Path):
    """
    Smoke check: the ruff config bans `except Exception:` (BLE001).
    If a contributor accidentally adds one, CI fails.
    """
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select=BLE", str(tmp_module)],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert result.returncode != 0, f"ruff should have failed but didn't.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "BLE001" in result.stdout

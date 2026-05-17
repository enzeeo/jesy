"""Tests for analysis.narrative — LLM call + fallback paths."""
from __future__ import annotations

import json

from disaster.analysis.models import (
    AARResponse,
    AARScorecard,
    CounterfactualPanel,
    PolicyResult,
)
from disaster.analysis.narrative import (
    _parse_llm_payload,
    _static_fallback,
    generate_narrative,
)
from disaster.errors import UpstreamUnavailable
from disaster.llm import LLMClient


def _aar() -> AARResponse:
    return AARResponse(
        sim_run_id="r1",
        started_at=None,
        ended_at=None,
        is_live=False,
        badge=None,
        scorecard=AARScorecard(
            incident_count=10,
            assigned_count=8,
            assigned_pct=0.8,
            p50_eta_seconds=240.0,
            p90_eta_seconds=420.0,
            total_fleet_distance_km=12.5,
            vulnerable_incident_count=3,
            vulnerable_assigned_count=2,
            vulnerable_eta_p50_seconds=300.0,
            extraction_confidence_p50=0.92,
        ),
        counterfactual=CounterfactualPanel(
            actual=PolicyResult(key="actual", label="Actual", is_actual=True),
            policies=[PolicyResult(key="greedy", label="Greedy")],
            winner_by_assignment="greedy",
            winner_by_vulnerable_eta=None,
        ),
        vulnerability=[],
        timeline=[],
        incidents_geo=[],
        data_source="in_memory",
    )


# ── static fallback ────────────────────────────────────────────────────────

def test_static_fallback_uses_real_numbers():
    out = _static_fallback(_aar())
    assert out.source == "fallback"
    assert "10 incidents" in out.narrative
    assert "8" in out.narrative
    assert "80%" in out.narrative
    assert out.lessons == []


# ── _parse_llm_payload ─────────────────────────────────────────────────────

def test_parse_clean_json():
    aar = _aar()
    payload = json.dumps({
        "narrative": "ran cleanly",
        "lessons": [
            {"headline": "Pre-stage X", "rationale": "near Y", "metric_citations": ["p50=240s"]},
        ],
    })
    out = _parse_llm_payload(payload, aar)
    assert out.source == "openai"
    assert out.narrative == "ran cleanly"
    assert len(out.lessons) == 1
    assert out.lessons[0].headline == "Pre-stage X"


def test_parse_strips_markdown_fences():
    aar = _aar()
    raw = '```json\n{"narrative": "fenced", "lessons": []}\n```'
    out = _parse_llm_payload(raw, aar)
    assert out.narrative == "fenced"
    assert out.source == "openai"


def test_parse_malformed_json_falls_back():
    aar = _aar()
    out = _parse_llm_payload("not json {", aar)
    assert out.source == "fallback"
    assert "10 incidents" in out.narrative


def test_parse_missing_narrative_falls_back():
    aar = _aar()
    out = _parse_llm_payload(json.dumps({"lessons": []}), aar)
    assert out.source == "fallback"


def test_parse_drops_malformed_lessons_keeps_good_ones():
    aar = _aar()
    out = _parse_llm_payload(json.dumps({
        "narrative": "ok",
        "lessons": [
            {"headline": "good", "rationale": "valid", "metric_citations": ["a"]},
            "not a dict",
            {"missing_fields": True},
            {"headline": "also good", "rationale": "valid"},
        ],
    }), aar)
    assert out.source == "openai"
    assert len(out.lessons) == 2
    assert {lesson.headline for lesson in out.lessons} == {"good", "also good"}


# ── generate_narrative (with fake LLM) ─────────────────────────────────────

async def test_generate_with_no_llm_returns_fallback():
    out = await generate_narrative(_aar(), None)
    assert out.source == "fallback"


async def test_generate_with_working_llm_returns_openai():
    async def fake_completion(_prompt, _kwargs):
        return {"content": json.dumps({
            "narrative": "from llm",
            "lessons": [{"headline": "h", "rationale": "r"}],
        }), "tokens": 10}
    client = LLMClient(fake_completion)
    out = await generate_narrative(_aar(), client)
    assert out.source == "openai"
    assert out.narrative == "from llm"


async def test_generate_with_llm_error_returns_fallback():
    async def boom(_prompt, _kwargs):
        raise UpstreamUnavailable("simulated")
    client = LLMClient(boom)
    out = await generate_narrative(_aar(), client)
    assert out.source == "fallback"


async def test_generate_with_llm_timeout_returns_fallback():
    import asyncio

    async def slow(_prompt, _kwargs):
        await asyncio.sleep(10)  # exceeds 3s timeout
        return {"content": "{}"}
    client = LLMClient(slow)
    out = await generate_narrative(_aar(), client)
    assert out.source == "fallback"

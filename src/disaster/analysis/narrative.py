"""
LLM-generated AAR narrative + lessons learned.

  AARResponse (numbers)
        │
        ▼
   prompt builder (concise metric digest, no system prefix reuse)
        │
        ▼
   LLMClient.call with 3-second wall-clock cap
        │
        ▼
   parse JSON → NarrativeResponse{narrative, lessons[], source}
        │
        ▼
   on any failure → static fallback prose (still 200 OK to caller)

NOTE: deliberately does NOT reuse the byte-identical extraction prefix from
disaster/llm/prompt.py. That prefix is engineered for single-incident voice
extraction; using it here gains zero cache value because the user content is a
completely different shape. New prompt, separate cache namespace.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from disaster.analysis.models import AARResponse, LessonItem, NarrativeResponse

if TYPE_CHECKING:
    from disaster.llm import LLMClient

log = logging.getLogger(__name__)

_LLM_TIMEOUT_S = 3.0


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 60:
        return f"{value:.0f}s"
    return f"{value / 60:.1f}min"


def _build_prompt(aar: AARResponse) -> str:
    sc = aar.scorecard
    cf = aar.counterfactual
    vuln_lines = [
        f"  {v.class_name}: {v.assigned_count}/{v.incident_count} assigned, "
        f"p50 ETA {_format_seconds(v.p50_eta_seconds)}, "
        f"gap vs general {v.eta_gap_vs_baseline_seconds:+.0f}s"
        for v in aar.vulnerability
    ]
    policy_lines = []
    if cf is not None:
        policy_lines.append(
            f"  actual: assigned={cf.actual.assigned_count}, "
            f"p50={_format_seconds(cf.actual.p50_eta_seconds)}, "
            f"vuln_p50={_format_seconds(cf.actual.vulnerable_eta_p50_seconds)}"
        )
        for p in cf.policies:
            if p.error:
                policy_lines.append(f"  {p.key}: error={p.error}")
            else:
                policy_lines.append(
                    f"  {p.key}: assigned={p.assigned_count}, "
                    f"p50={_format_seconds(p.p50_eta_seconds)}, "
                    f"vuln_p50={_format_seconds(p.vulnerable_eta_p50_seconds)}"
                )

    return (
        "You are writing the closing summary of a disaster-response after-action "
        "report (AAR). Be terse, direct, and grounded in the numbers below. Do not "
        "speculate or invent metrics. If a metric is missing (—), say so. Output "
        "JSON only.\n\n"
        f"RUN: {aar.sim_run_id}\n"
        f"INCIDENTS: {sc.incident_count}\n"
        f"ASSIGNED: {sc.assigned_count} ({sc.assigned_pct * 100:.0f}%)\n"
        f"ETA p50 / p90 (among assigned): "
        f"{_format_seconds(sc.p50_eta_seconds)} / {_format_seconds(sc.p90_eta_seconds)}\n"
        f"VULNERABLE VICTIMS: {sc.vulnerable_incident_count} incidents, "
        f"{sc.vulnerable_assigned_count} assigned, "
        f"p50 ETA {_format_seconds(sc.vulnerable_eta_p50_seconds)}\n"
        f"VULNERABILITY BREAKDOWN:\n" + ("\n".join(vuln_lines) if vuln_lines else "  (none)") + "\n"
        f"COUNTERFACTUAL POLICIES:\n" + ("\n".join(policy_lines) if policy_lines else "  (none — live run)") + "\n\n"
        "Produce JSON of this exact shape:\n"
        "{\n"
        '  "narrative": "<2 paragraphs describing what happened and what stood out. '
        'Mention specific numbers. No more than 6 sentences total.>",\n'
        '  "lessons": [\n'
        '    {"headline": "<one-line recommendation>", '
        '"rationale": "<one sentence explaining the metric that triggered it>", '
        '"metric_citations": ["<key=value>", ...]},\n'
        "    ...3-5 items...\n"
        "  ]\n"
        "}\n"
        "JSON ONLY. No markdown fences. No prose outside the JSON."
    )


def _static_fallback(aar: AARResponse) -> NarrativeResponse:
    """Deterministic prose used when the LLM is unavailable, slow, or malformed."""
    sc = aar.scorecard
    pct = int(sc.assigned_pct * 100)
    p50 = _format_seconds(sc.p50_eta_seconds)
    vuln_p50 = _format_seconds(sc.vulnerable_eta_p50_seconds)
    paragraphs = [
        f"In run {aar.sim_run_id}, {sc.incident_count} incidents were recorded "
        f"and {sc.assigned_count} ({pct}%) received a dispatch. Median ETA among "
        f"assigned incidents was {p50}.",
        f"Of {sc.vulnerable_incident_count} incidents involving vulnerable victims, "
        f"{sc.vulnerable_assigned_count} were assigned with median ETA {vuln_p50}.",
    ]
    return NarrativeResponse(
        narrative=" ".join(paragraphs),
        lessons=[],
        source="fallback",
    )


def _parse_llm_payload(raw: str, aar: AARResponse) -> NarrativeResponse:
    """
    Parse the LLM response. Tolerates surrounding whitespace / accidental code
    fences. Falls back to static prose on any structural failure.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences if the model ignored the instruction
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        payload: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("aar narrative: malformed LLM JSON (%s); using fallback", e)
        return _static_fallback(aar)

    narrative = payload.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        log.warning("aar narrative: missing narrative field; using fallback")
        return _static_fallback(aar)

    lessons_raw = payload.get("lessons") or []
    lessons: list[LessonItem] = []
    if isinstance(lessons_raw, list):
        for item in lessons_raw[:5]:
            if not isinstance(item, dict):
                continue
            headline = item.get("headline")
            rationale = item.get("rationale")
            if not isinstance(headline, str) or not isinstance(rationale, str):
                continue
            citations_raw = item.get("metric_citations") or []
            citations = [c for c in citations_raw if isinstance(c, str)][:10]
            lessons.append(LessonItem(
                headline=headline.strip(),
                rationale=rationale.strip(),
                metric_citations=citations,
            ))

    return NarrativeResponse(narrative=narrative.strip(), lessons=lessons, source="openai")


async def generate_narrative(
    aar: AARResponse,
    llm_client: LLMClient | None,
) -> NarrativeResponse:
    """
    Public entry. Returns a NarrativeResponse — never raises. The endpoint can
    always return 200. `source` field tells the caller whether to expect rich
    lessons (`"openai"`) or just two paragraphs (`"fallback"`).
    """
    if llm_client is None:
        return _static_fallback(aar)

    prompt = _build_prompt(aar)
    try:
        result = await asyncio.wait_for(llm_client.call(prompt), timeout=_LLM_TIMEOUT_S)
    except TimeoutError:
        log.warning("aar narrative: LLM call exceeded %.1fs; using fallback", _LLM_TIMEOUT_S)
        return _static_fallback(aar)
    except Exception as e:  # noqa: BLE001 — narrative MUST always return; never bubble
        log.warning("aar narrative: LLM call failed (%s); using fallback", e)
        return _static_fallback(aar)

    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, str):
        log.warning("aar narrative: LLM returned no content; using fallback")
        return _static_fallback(aar)
    return _parse_llm_payload(content, aar)

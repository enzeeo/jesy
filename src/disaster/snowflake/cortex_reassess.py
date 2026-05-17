"""
Snowflake Cortex reassessment of incident severity and priority from narrative text.

Uses SNOWFLAKE.CORTEX.COMPLETE when a query runner is available. Falls back to
keyword heuristics over the incident description + transcript so demos work
without Cortex access.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from disaster.models import IncidentReport, Severity

log = logging.getLogger(__name__)

_SEVERITY_VALUES = {s.value for s in Severity}
_BASE_PRIORITY = {
    Severity.IMMEDIATE: 0.85,
    Severity.DELAYED: 0.50,
    Severity.MINOR: 0.20,
    Severity.DECEASED: 0.05,
}

_PROMPT_TEMPLATE = """You are a disaster-response triage assistant applying START triage.
Read the incident narrative and return ONLY a JSON object (no markdown) with:
- "severity": exactly one of "Immediate", "Delayed", "Minor", "Deceased"
- "priority_score": number from 0.0 to 1.0 (higher = dispatch sooner)
- "reason": one short sentence (max 120 chars) citing the narrative

NARRATIVE:
{narrative}
"""


@dataclass(frozen=True)
class ReassessResult:
    severity: Severity
    priority_score: float
    reason: str


def cortex_model() -> str:
    return os.environ.get("SNOWFLAKE_CORTEX_MODEL", "llama3.1-8b")


def incident_narrative(incident: IncidentReport) -> str:
    parts: list[str] = []
    if incident.location.description:
        parts.append(f"Location / situation: {incident.location.description}")
    if incident.call_transcript:
        parts.append(f"Transcript: {incident.call_transcript}")
    if incident.victims:
        v = incident.victims[0]
        victim_bits: list[str] = []
        if v.injuries:
            victim_bits.append("injuries: " + ", ".join(v.injuries))
        if v.mobility.value != "unknown":
            victim_bits.append(f"mobility: {v.mobility.value}")
        if v.breathing.value != "unknown":
            victim_bits.append(f"breathing: {v.breathing.value}")
        if victim_bits:
            parts.append("Victim: " + "; ".join(victim_bits))
    return "\n".join(parts) or incident.location.description


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json\n"):
            stripped = stripped[5:]
        stripped = stripped.rstrip("`").strip()
    return stripped


def parse_cortex_json(raw: str) -> ReassessResult:
    """Parse Cortex COMPLETE output into validated severity + priority."""
    text = _strip_json_fences(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")

    severity_raw = str(parsed.get("severity", "")).strip()
    if severity_raw not in _SEVERITY_VALUES:
        for candidate in Severity:
            if severity_raw.lower() == candidate.value.lower():
                severity_raw = candidate.value
                break
        else:
            raise ValueError(f"invalid severity: {severity_raw!r}")

    severity = Severity(severity_raw)
    priority = float(parsed.get("priority_score", _BASE_PRIORITY[severity]))
    priority = max(0.0, min(1.0, priority))
    reason = str(parsed.get("reason", "cortex reassessment")).strip()[:200]
    if not reason:
        reason = "cortex reassessment"
    return ReassessResult(severity=severity, priority_score=priority, reason=reason)


def reassess_heuristic(incident: IncidentReport) -> ReassessResult:
    """Keyword fallback when Snowflake Cortex is unavailable."""
    text = incident_narrative(incident).lower()

    if any(k in text for k in ("deceased", "no pulse", "dead", "not breathing after")):
        severity = Severity.DECEASED
        reason = "heuristic: deceased / no breathing after airway"
    elif any(k in text for k in (
        "not breathing", "unresponsive", "crush", "trapped", "drowning",
        "severe bleeding", "unconscious", "cardiac", "can't breathe",
    )):
        severity = Severity.IMMEDIATE
        reason = "heuristic: urgent keywords in narrative"
    elif any(k in text for k in ("walking", "minor cut", "scratch", "sprain", "stable")):
        severity = Severity.MINOR
        reason = "heuristic: minor / walking keywords"
    else:
        severity = Severity.DELAYED
        reason = "heuristic: default delayed pending clearer signal"

    priority = _BASE_PRIORITY[severity]
    if incident.victims and incident.victims[0].age_estimate is not None:
        age = incident.victims[0].age_estimate
        if age <= 12:
            priority = min(1.0, priority + 0.10)
        elif age >= 75:
            priority = min(1.0, priority + 0.05)

    return ReassessResult(
        severity=severity,
        priority_score=max(0.0, min(1.0, priority)),
        reason=reason,
    )


async def reassess_via_snowflake(
    runner: Callable[[str, tuple], Awaitable[list[dict[str, Any]]]],
    incident: IncidentReport,
) -> ReassessResult:
    narrative = incident_narrative(incident)
    prompt = _PROMPT_TEMPLATE.format(narrative=narrative)
    model = cortex_model()
    sql = "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS RESPONSE"
    rows = await runner(sql, (model, prompt))
    if not rows:
        raise RuntimeError("cortex COMPLETE returned no rows")
    raw = rows[0].get("RESPONSE") or rows[0].get("response") or ""
    if not str(raw).strip():
        raise RuntimeError("cortex COMPLETE returned empty response")
    try:
        return parse_cortex_json(str(raw))
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("cortex reassess: parse failed (%s), raw=%r", e, raw[:200])
        raise

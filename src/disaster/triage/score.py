"""
START triage scorer. Pure function — no I/O, no clock, no randomness.

  ┌───────────────────────────────────────────────────────────────┐
  │  START decision tree (first match wins)                       │
  │                                                                │
  │  walking?                       ─yes─▶ MINOR                  │
  │  no breathing AFTER airway?     ─yes─▶ DECEASED               │
  │  resp rate > 30/min?            ─yes─▶ IMMEDIATE              │
  │  perfusion poor?                ─yes─▶ IMMEDIATE              │
  │  cannot follow simple commands? ─yes─▶ IMMEDIATE              │
  │  otherwise                            ─▶ DELAYED              │
  └───────────────────────────────────────────────────────────────┘

Priority score (0.0-1.0) layered on top of severity:
  base by severity:  IMMEDIATE=0.85, DELAYED=0.50, MINOR=0.20, DECEASED=0.05
  +0.10  if child (age <= 12)
  +0.05  if elderly (age >= 75)
  +0.05  if mobility-dependent or medical-dependency vulnerability flagged
  +0.05  per 60s elapsed since incident timestamp, capped at +0.10
  clamped to [0.0, 1.0]

Triages the FIRST victim only (single-victim incidents are the demo norm).
For multi-victim, call once per victim and bubble up the highest priority.
"""
from __future__ import annotations

from datetime import datetime

from disaster.errors import IncompleteAssessment
from disaster.models import (
    Breathing,
    IncidentReport,
    Mobility,
    Perfusion,
    Severity,
    TriageResult,
    Victim,
)

_CHILD_AGE = 12
_ELDERLY_AGE = 75
_RESP_RATE_THRESHOLD = 30
_TIME_BONUS_PER_60S = 0.05
_TIME_BONUS_CAP = 0.10

_VULN_HIGH_PRIORITY = frozenset({
    "mobility_dependent",
    "wheelchair",
    "medical_dependency",
    "oxygen",
    "dialysis",
    "child_trapped",
})


def _classify(victim: Victim) -> tuple[Severity, str]:
    """Apply START decision tree. Returns (severity, one-line reason)."""
    if victim.mobility == Mobility.WALKING:
        return Severity.MINOR, "victim is walking"

    if victim.breathing == Breathing.ABSENT:
        # ABSENT means absent after airway-opening attempt per protocol.
        return Severity.DECEASED, "no breathing after airway opened"

    if victim.breathing == Breathing.UNKNOWN and victim.mobility == Mobility.UNKNOWN:
        raise IncompleteAssessment("breathing and mobility both unknown")

    if (
        victim.respiratory_rate is not None
        and victim.respiratory_rate > _RESP_RATE_THRESHOLD
    ):
        return Severity.IMMEDIATE, f"respiratory rate {victim.respiratory_rate}/min > 30"

    if victim.perfusion == Perfusion.POOR:
        return Severity.IMMEDIATE, "poor perfusion (cap refill ≥2s or no radial pulse)"

    if victim.mobility == Mobility.CANNOT_FOLLOW_COMMANDS:
        return Severity.IMMEDIATE, "cannot follow simple commands"

    return Severity.DELAYED, "breathing, perfusion adequate, follows commands"


def _base_priority(severity: Severity) -> float:
    return {
        Severity.IMMEDIATE: 0.85,
        Severity.DELAYED: 0.50,
        Severity.MINOR: 0.20,
        Severity.DECEASED: 0.05,
    }[severity]


def _vulnerability_bonus(victim: Victim) -> float:
    bonus = 0.0
    if victim.age_estimate is not None:
        if victim.age_estimate <= _CHILD_AGE:
            bonus += 0.10
        elif victim.age_estimate >= _ELDERLY_AGE:
            bonus += 0.05

    flags = {v.strip().lower() for v in victim.vulnerabilities}
    if flags & _VULN_HIGH_PRIORITY:
        bonus += 0.05
    return bonus


def _time_bonus(incident_ts: datetime, current_time: datetime) -> float:
    elapsed_s = max(0.0, (current_time - incident_ts).total_seconds())
    minutes = elapsed_s / 60.0
    return min(_TIME_BONUS_CAP, minutes * _TIME_BONUS_PER_60S)


def score(report: IncidentReport, *, current_time: datetime) -> TriageResult:
    """
    Pure function. Inject current_time for testability.

    Raises IncompleteAssessment if the victim record lacks enough signal to classify.
    Caller should rescue and persist with status=PARTIAL.
    """
    if not report.victims:
        raise IncompleteAssessment("no victims in report")

    victim = report.victims[0]
    severity, reason = _classify(victim)

    raw = (
        _base_priority(severity)
        + _vulnerability_bonus(victim)
        + _time_bonus(report.timestamp, current_time)
    )
    priority = max(0.0, min(1.0, raw))

    return TriageResult(severity=severity, priority_score=priority, reason=reason)

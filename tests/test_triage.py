"""Tests for /triage/score (P1 #4). Covers each START branch + priority modifiers."""
from datetime import UTC, datetime, timedelta

import pytest

from disaster.errors import IncompleteAssessment
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    Perfusion,
    Severity,
    Victim,
)
from disaster.triage import score

FIXED_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


def _incident(victim: Victim, *, ts: datetime = FIXED_NOW) -> IncidentReport:
    return IncidentReport(
        timestamp=ts,
        location=Location(lat=19.7, lng=-155.0, description="test"),
        victims=[victim],
    )


# ── START decision tree ──────────────────────────────────────────────────────

def test_walking_is_minor():
    v = Victim(mobility=Mobility.WALKING)
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.MINOR
    assert "walking" in result.reason


def test_not_breathing_after_airway_is_deceased():
    v = Victim(mobility=Mobility.CANNOT_FOLLOW_COMMANDS, breathing=Breathing.ABSENT)
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.DECEASED


def test_high_respiratory_rate_is_immediate():
    v = Victim(
        mobility=Mobility.CANNOT_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=32,
    )
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.IMMEDIATE
    assert "32" in result.reason


def test_resp_rate_at_threshold_is_not_immediate():
    """Exactly 30 should NOT trigger immediate (> 30 per protocol)."""
    v = Victim(
        mobility=Mobility.CAN_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=30,
        perfusion=Perfusion.NORMAL,
    )
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.DELAYED


def test_poor_perfusion_is_immediate():
    v = Victim(
        mobility=Mobility.CAN_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=20,
        perfusion=Perfusion.POOR,
    )
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.IMMEDIATE
    assert "perfusion" in result.reason


def test_cannot_follow_commands_is_immediate():
    v = Victim(
        mobility=Mobility.CANNOT_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=20,
        perfusion=Perfusion.NORMAL,
    )
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.IMMEDIATE


def test_otherwise_delayed():
    v = Victim(
        mobility=Mobility.CAN_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=18,
        perfusion=Perfusion.NORMAL,
    )
    result = score(_incident(v), current_time=FIXED_NOW)
    assert result.severity == Severity.DELAYED


def test_incomplete_assessment_raises():
    v = Victim()  # all UNKNOWN
    with pytest.raises(IncompleteAssessment):
        score(_incident(v), current_time=FIXED_NOW)


# ── Priority modifiers ───────────────────────────────────────────────────────

def test_child_adds_priority_bonus():
    v_adult = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                     respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=30)
    v_child = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                     respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=8)
    adult = score(_incident(v_adult), current_time=FIXED_NOW)
    child = score(_incident(v_child), current_time=FIXED_NOW)
    assert adult.severity == child.severity == Severity.DELAYED
    assert child.priority_score > adult.priority_score
    assert pytest.approx(child.priority_score - adult.priority_score, abs=1e-9) == 0.10


def test_elderly_adds_priority_bonus():
    v_adult = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                     respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=40)
    v_elderly = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                       respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=80)
    adult = score(_incident(v_adult), current_time=FIXED_NOW)
    elderly = score(_incident(v_elderly), current_time=FIXED_NOW)
    assert pytest.approx(elderly.priority_score - adult.priority_score, abs=1e-9) == 0.05


def test_vulnerability_flag_adds_bonus():
    v_plain = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                     respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=40)
    v_flagged = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
                       respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=40,
                       vulnerabilities=["child_trapped"])
    plain = score(_incident(v_plain), current_time=FIXED_NOW)
    flagged = score(_incident(v_flagged), current_time=FIXED_NOW)
    assert pytest.approx(flagged.priority_score - plain.priority_score, abs=1e-9) == 0.05


def test_time_bonus_scales_with_elapsed_minutes():
    v = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
               respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=40)
    fresh = score(_incident(v, ts=FIXED_NOW), current_time=FIXED_NOW)
    one_min = score(_incident(v, ts=FIXED_NOW - timedelta(minutes=1)), current_time=FIXED_NOW)
    capped = score(_incident(v, ts=FIXED_NOW - timedelta(minutes=10)), current_time=FIXED_NOW)
    assert pytest.approx(one_min.priority_score - fresh.priority_score, abs=1e-9) == 0.05
    # capped at +0.10
    assert pytest.approx(capped.priority_score - fresh.priority_score, abs=1e-9) == 0.10


def test_priority_clamped_to_one():
    v = Victim(
        mobility=Mobility.CANNOT_FOLLOW_COMMANDS,
        breathing=Breathing.SPONTANEOUS,
        respiratory_rate=40,
        perfusion=Perfusion.POOR,
        age_estimate=8,
        vulnerabilities=["child_trapped", "medical_dependency"],
    )
    # base IMMEDIATE=0.85 + child 0.10 + flag 0.05 + 10min = 0.10 → 1.10, clamped to 1.0
    result = score(
        _incident(v, ts=FIXED_NOW - timedelta(minutes=10)),
        current_time=FIXED_NOW,
    )
    assert result.priority_score == 1.0


# ── Purity ───────────────────────────────────────────────────────────────────

def test_purity_same_input_same_output():
    v = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
               respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=30)
    incident = _incident(v)
    r1 = score(incident, current_time=FIXED_NOW)
    r2 = score(incident, current_time=FIXED_NOW)
    assert r1 == r2


def test_purity_does_not_mutate_input():
    v = Victim(mobility=Mobility.CAN_FOLLOW_COMMANDS, breathing=Breathing.SPONTANEOUS,
               respiratory_rate=18, perfusion=Perfusion.NORMAL, age_estimate=30)
    incident = _incident(v)
    snapshot = incident.model_dump_json()
    score(incident, current_time=FIXED_NOW)
    assert incident.model_dump_json() == snapshot

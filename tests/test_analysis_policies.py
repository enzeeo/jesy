"""Tests for analysis.policies — scorers + vulnerability normalization."""
from __future__ import annotations

import pytest

from disaster.analysis.policies import (
    POLICIES,
    has_vulnerable_victim,
    incident_vuln_classes,
    normalize_vulnerability,
    score_default,
    score_vulnerability_priority,
)
from disaster.models import (
    Breathing,
    IncidentReport,
    Location,
    Mobility,
    Victim,
)


def _incident(*, priority: float = 0.5, vulns: list[str] | None = None) -> IncidentReport:
    return IncidentReport(
        location=Location(lat=19.7, lng=-155.0, description="x"),
        victims=[Victim(
            mobility=Mobility.WALKING,
            breathing=Breathing.SPONTANEOUS,
            vulnerabilities=vulns or [],
        )],
        priority_score=priority,
    )


# ── normalize_vulnerability ──────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("elderly", "elderly"),
    ("ELDERLY", "elderly"),
    (" Elderly ", "elderly"),
    ("elder", "elderly"),
    ("senior", "elderly"),
    ("elderly_person", "elderly"),
    ("elderly-person", "elderly"),
    ("child", "child"),
    ("CHILD", "child"),
    ("kid", "child"),
    ("infant", "child"),
    ("disabled", "disabled"),
    ("non_ambulatory", "disabled"),
    ("wheelchair_user", "disabled"),
    ("medical_dependency", "medical_dependency"),
    ("ventilator", "medical_dependency"),
    ("oxygen", "medical_dependency"),
])
def test_normalize_vulnerability_known_aliases(raw, expected):
    assert normalize_vulnerability(raw) == expected


@pytest.mark.parametrize("raw", ["alien", "", "  ", "tourist", "unknown_label"])
def test_normalize_vulnerability_unknown_returns_none(raw):
    assert normalize_vulnerability(raw) is None


# ── has_vulnerable_victim / incident_vuln_classes ───────────────────────────

def test_has_vulnerable_true_for_known_class():
    inc = _incident(vulns=["elderly"])
    assert has_vulnerable_victim(inc) is True


def test_has_vulnerable_true_for_aliased_string():
    inc = _incident(vulns=["ELDERLY_PERSON"])
    assert has_vulnerable_victim(inc) is True


def test_has_vulnerable_false_for_empty():
    inc = _incident(vulns=[])
    assert has_vulnerable_victim(inc) is False


def test_has_vulnerable_false_for_unknown_only():
    inc = _incident(vulns=["alien", "tourist"])
    assert has_vulnerable_victim(inc) is False


def test_incident_vuln_classes_dedupes_and_normalizes():
    inc = _incident(vulns=["elderly", "elder", "SENIOR", "child"])
    assert incident_vuln_classes(inc) == {"elderly", "child"}


# ── scorers ──────────────────────────────────────────────────────────────────

def test_score_default_is_negative_priority():
    assert score_default(_incident(priority=0.7)) == pytest.approx(-0.7)
    assert score_default(_incident(priority=0.0)) == pytest.approx(0.0)
    assert score_default(_incident(priority=1.0)) == pytest.approx(-1.0)


def test_score_vulnpri_bumps_vulnerable_more_negative():
    vuln = _incident(priority=0.5, vulns=["elderly"])
    plain = _incident(priority=0.5, vulns=[])
    # vuln should sort BEFORE plain (more negative = higher priority)
    assert score_vulnerability_priority(vuln) < score_vulnerability_priority(plain)


def test_score_vulnpri_clamps_to_1():
    # priority 0.9 + bonus 0.2 = 1.1; clamped to 1.0 → score = -1.0
    inc = _incident(priority=0.9, vulns=["elderly"])
    assert score_vulnerability_priority(inc) == pytest.approx(-1.0)


def test_score_vulnpri_equals_default_when_not_vulnerable():
    inc = _incident(priority=0.6, vulns=[])
    assert score_vulnerability_priority(inc) == score_default(inc)


# ── POLICIES registry ────────────────────────────────────────────────────────

def test_policies_registry_has_three_canonical_entries():
    assert set(POLICIES.keys()) == {"greedy", "vrp_current", "vrp_vulnpri"}


def test_policies_have_human_readable_labels():
    for p in POLICIES.values():
        assert p.label and isinstance(p.label, str)
        assert p.label != p.key  # not just the bare key

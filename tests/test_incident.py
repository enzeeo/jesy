"""Tests for IncidentReport (P1 #3)."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from disaster.models import (
    Breathing,
    Caller,
    Consciousness,
    IncidentReport,
    IncidentSource,
    IncidentStatus,
    Location,
    Mobility,
    Perfusion,
    Severity,
    TriageResult,
    Victim,
)


def _minimal_incident(**overrides) -> IncidentReport:
    base = dict(
        location=Location(lat=19.7297, lng=-155.0900, description="Hilo Bay Front"),
        victims=[Victim(age_estimate=34, injuries=["laceration"])],
    )
    base.update(overrides)
    return IncidentReport(**base)


# ── Strictness ────────────────────────────────────────────────────────────────

def test_rejects_extra_fields_on_root():
    with pytest.raises(ValidationError) as exc:
        IncidentReport.model_validate({
            "location": {"lat": 19.7, "lng": -155.0, "description": "test"},
            "victims": [{"injuries": []}],
            "rogue_field": "should fail",
        })
    assert "rogue_field" in str(exc.value)


def test_rejects_extra_fields_on_nested():
    with pytest.raises(ValidationError):
        IncidentReport.model_validate({
            "location": {"lat": 19.7, "lng": -155.0, "description": "test", "extra": 1},
            "victims": [{"injuries": []}],
        })


def test_requires_at_least_one_victim():
    with pytest.raises(ValidationError):
        IncidentReport.model_validate({
            "location": {"lat": 19.7, "lng": -155.0, "description": "test"},
            "victims": [],
        })


# ── Range validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("lat,lng", [
    (-91.0, 0.0),
    (91.0, 0.0),
    (0.0, -181.0),
    (0.0, 181.0),
])
def test_location_out_of_range(lat, lng):
    with pytest.raises(ValidationError):
        Location(lat=lat, lng=lng, description="bad")


def test_respiratory_rate_bounds():
    with pytest.raises(ValidationError):
        Victim(respiratory_rate=-1)
    with pytest.raises(ValidationError):
        Victim(respiratory_rate=200)


def test_priority_score_bounds():
    with pytest.raises(ValidationError):
        _minimal_incident(priority_score=1.5)
    with pytest.raises(ValidationError):
        _minimal_incident(priority_score=-0.1)


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_round_trip_serialization():
    incident = _minimal_incident(
        caller=Caller(phone_hash="a" * 16, callback_available=True),
        source=IncidentSource.VOICE,
        status=IncidentStatus.NEW,
    )
    serialized = incident.model_dump_json()
    restored = IncidentReport.model_validate_json(serialized)
    assert restored == incident


@pytest.mark.parametrize("severity", list(Severity))
def test_all_severity_values_round_trip(severity):
    incident = _minimal_incident(severity=severity)
    serialized = incident.model_dump_json()
    restored = IncidentReport.model_validate_json(serialized)
    assert restored.severity == severity


@pytest.mark.parametrize("status", list(IncidentStatus))
def test_all_status_values_round_trip(status):
    incident = _minimal_incident(status=status)
    serialized = incident.model_dump_json()
    restored = IncidentReport.model_validate_json(serialized)
    assert restored.status == status


@pytest.mark.parametrize("source", list(IncidentSource))
def test_all_source_values_round_trip(source):
    incident = _minimal_incident(source=source)
    serialized = incident.model_dump_json()
    restored = IncidentReport.model_validate_json(serialized)
    assert restored.source == source


# ── Victim enum coverage ─────────────────────────────────────────────────────

@pytest.mark.parametrize("consciousness", list(Consciousness))
def test_consciousness_round_trip(consciousness):
    v = Victim(consciousness=consciousness)
    assert Victim.model_validate(v.model_dump()).consciousness == consciousness


@pytest.mark.parametrize("breathing", list(Breathing))
def test_breathing_round_trip(breathing):
    v = Victim(breathing=breathing)
    assert Victim.model_validate(v.model_dump()).breathing == breathing


@pytest.mark.parametrize("perfusion", list(Perfusion))
def test_perfusion_round_trip(perfusion):
    v = Victim(perfusion=perfusion)
    assert Victim.model_validate(v.model_dump()).perfusion == perfusion


@pytest.mark.parametrize("mobility", list(Mobility))
def test_mobility_round_trip(mobility):
    v = Victim(mobility=mobility)
    assert Victim.model_validate(v.model_dump()).mobility == mobility


# ── Timezone enforcement ─────────────────────────────────────────────────────

def test_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        _minimal_incident(timestamp=datetime(2026, 5, 16, 12, 0, 0))  # no tzinfo


def test_accepts_aware_timestamp():
    ts = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    incident = _minimal_incident(timestamp=ts)
    assert incident.timestamp == ts


# ── with_triage helper ───────────────────────────────────────────────────────

def test_with_triage_applies_severity_and_priority():
    incident = _minimal_incident()
    result = TriageResult(severity=Severity.IMMEDIATE, priority_score=0.95, reason="poor perfusion")
    updated = incident.with_triage(result)
    assert updated.severity == Severity.IMMEDIATE
    assert updated.priority_score == 0.95
    # original unchanged
    assert incident.severity == Severity.DELAYED


# ── Caller is optional for simulator ─────────────────────────────────────────

def test_simulator_incident_no_caller():
    incident = _minimal_incident(source=IncidentSource.SIMULATED, caller=None, sim_run_id="run-001")
    assert incident.caller is None
    assert incident.sim_run_id == "run-001"

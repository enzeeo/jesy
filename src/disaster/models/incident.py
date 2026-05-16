"""
IncidentReport: the single pydantic model used by every layer.

  voice intake  ─┐
  simulator     ─┼─▶ IncidentReport ─▶ /incidents store ─▶ snowflake_writer
  /incidents API ─┘                                       ─▶ SSE broadcast

Strict mode rejects unknown fields loudly. If a producer adds a field, every
consumer fails fast and obvious instead of silently dropping data.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Enums ─────────────────────────────────────────────────────────────────────

class Severity(StrEnum):
    IMMEDIATE = "Immediate"
    DELAYED = "Delayed"
    MINOR = "Minor"
    DECEASED = "Deceased"


class Consciousness(StrEnum):
    ALERT = "alert"
    RESPONDS_TO_VOICE = "responds_to_voice"
    RESPONDS_TO_PAIN = "responds_to_pain"
    UNRESPONSIVE = "unresponsive"
    UNKNOWN = "unknown"


class Breathing(StrEnum):
    SPONTANEOUS = "spontaneous"
    AFTER_AIRWAY = "after_airway"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class Perfusion(StrEnum):
    NORMAL = "normal"          # cap refill <2s OR radial pulse present
    POOR = "poor"              # cap refill ≥2s OR no radial pulse
    UNKNOWN = "unknown"


class Mobility(StrEnum):
    WALKING = "walking"
    CAN_FOLLOW_COMMANDS = "can_follow_commands"
    CANNOT_FOLLOW_COMMANDS = "cannot_follow_commands"
    UNKNOWN = "unknown"


class IncidentStatus(StrEnum):
    NEW = "new"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RESOLVED = "resolved"
    PARTIAL = "partial"       # extraction incomplete, flagged for review


class IncidentSource(StrEnum):
    VOICE = "voice"
    SIMULATED = "simulated"
    MANUAL = "manual"


# ── Nested models ─────────────────────────────────────────────────────────────

class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lng: float
    description: str = Field(min_length=1, max_length=500)

    @field_validator("lat")
    @classmethod
    def _lat_range(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError(f"lat out of range: {v}")
        return v

    @field_validator("lng")
    @classmethod
    def _lng_range(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError(f"lng out of range: {v}")
        return v


class Caller(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_hash: str = Field(min_length=8, max_length=128)
    callback_available: bool = False


class Victim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_estimate: int | None = Field(default=None, ge=0, le=120)
    injuries: list[str] = Field(default_factory=list, max_length=20)
    consciousness: Consciousness = Consciousness.UNKNOWN
    breathing: Breathing = Breathing.UNKNOWN
    respiratory_rate: int | None = Field(default=None, ge=0, le=80)  # breaths/min
    perfusion: Perfusion = Perfusion.UNKNOWN
    mobility: Mobility = Mobility.UNKNOWN
    vulnerabilities: list[str] = Field(default_factory=list, max_length=20)


class TriageResult(BaseModel):
    """Return value of the pure /triage/score function."""
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    priority_score: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str = Field(min_length=1, max_length=200)


# ── Root model ────────────────────────────────────────────────────────────────

class IncidentReport(BaseModel):
    """
    Authoritative incident record. One instance per (voice call | simulator emit | manual entry).

    Created with severity=UNCLASSIFIED proxy; triage scorer fills severity + priority_score
    via .with_triage(result).
    """
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: IncidentSource = IncidentSource.VOICE
    status: IncidentStatus = IncidentStatus.NEW

    location: Location
    caller: Caller | None = None       # None for simulator-generated
    victims: list[Victim] = Field(min_length=1, max_length=20)

    severity: Severity = Severity.DELAYED   # default until triage runs
    priority_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    call_transcript: str = ""
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    sim_run_id: str | None = None          # idempotency key for simulator replays

    def with_triage(self, result: TriageResult) -> IncidentReport:
        """Return a new IncidentReport with triage fields applied."""
        return self.model_copy(update={
            "severity": result.severity,
            "priority_score": result.priority_score,
        })

    @field_validator("timestamp")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v

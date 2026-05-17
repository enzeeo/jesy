"""Pydantic models for the AAR API response shape."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AARScorecard(BaseModel):
    """Top-of-page KPIs for the run."""
    model_config = ConfigDict(extra="forbid")

    incident_count: int
    assigned_count: int
    assigned_pct: float                                 # 0-1
    p50_eta_seconds: float | None                       # among assigned only
    p90_eta_seconds: float | None
    total_fleet_distance_km: float
    vulnerable_incident_count: int
    vulnerable_assigned_count: int
    vulnerable_eta_p50_seconds: float | None
    extraction_confidence_p50: float | None             # voice intake quality


class PolicyResult(BaseModel):
    """One row of the counterfactual panel — either the actual dispatch or a replay."""
    model_config = ConfigDict(extra="forbid")

    key: str                                            # actual | greedy | vrp_current | vrp_vulnpri
    label: str
    is_actual: bool = False
    assigned_count: int = 0
    total_fleet_distance_km: float = 0.0
    p50_eta_seconds: float | None = None
    p90_eta_seconds: float | None = None
    vulnerable_assigned_count: int = 0
    vulnerable_eta_p50_seconds: float | None = None
    error: str | None = None                            # set on solver failure


class CounterfactualPanel(BaseModel):
    """Side-by-side comparison: actual dispatch vs three policy replays."""
    model_config = ConfigDict(extra="forbid")

    actual: PolicyResult
    policies: list[PolicyResult]                        # 3 entries: greedy, vrp_current, vrp_vulnpri
    winner_by_assignment: str | None                    # policy key with highest assigned_count
    winner_by_vulnerable_eta: str | None                # policy key with lowest vulnerable_eta_p50


class VulnerabilityBreakdown(BaseModel):
    """ETA performance for one vulnerability class."""
    model_config = ConfigDict(extra="forbid")

    class_name: str                                     # elderly | child | disabled | medical_dependency
    incident_count: int
    assigned_count: int
    p50_eta_seconds: float | None
    p90_eta_seconds: float | None
    eta_gap_vs_baseline_seconds: float                  # signed; positive = slower than general pop


class TimelineSlice(BaseModel):
    """One bucket in the incidents-over-time chart."""
    model_config = ConfigDict(extra="forbid")

    t_seconds: int                                      # seconds since first incident
    incidents_total: int                                # cumulative count
    incidents_assigned: int                             # cumulative count


class LessonItem(BaseModel):
    """One recommendation produced by the LLM (or empty list on fallback)."""
    model_config = ConfigDict(extra="forbid")

    headline: str
    rationale: str
    metric_citations: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)


class NarrativeResponse(BaseModel):
    """Separate endpoint payload so the main AAR JSON doesn't block on the LLM call."""
    model_config = ConfigDict(extra="forbid")

    narrative: str                                      # 2-paragraph prose summary
    lessons: list[LessonItem] = Field(default_factory=list)
    source: str                                         # "openai" | "fallback"


class AARResponse(BaseModel):
    """Full AAR payload returned by GET /api/analysis/{sim_run_id}."""
    model_config = ConfigDict(extra="forbid")

    sim_run_id: str
    started_at: datetime | None                         # earliest incident timestamp
    ended_at: datetime | None                           # latest incident timestamp
    is_live: bool                                       # true if sim_run_id == active_sim_run_id
    badge: str | None = None                            # "Run in progress — numbers may shift"
    scorecard: AARScorecard
    counterfactual: CounterfactualPanel | None          # None when is_live=true
    vulnerability: list[VulnerabilityBreakdown]
    timeline: list[TimelineSlice]
    data_source: str                                    # "snowflake" | "in_memory"

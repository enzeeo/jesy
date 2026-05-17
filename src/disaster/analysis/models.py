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
    p50_eta_seconds: float | None                       # estimated ETA among assigned
    p90_eta_seconds: float | None
    total_fleet_distance_km: float
    vulnerable_incident_count: int
    vulnerable_assigned_count: int
    vulnerable_eta_p50_seconds: float | None
    extraction_confidence_p50: float | None             # voice intake quality

    # Real wheels-on-scene timings sourced from SERVING.RESPONDER_ARRIVALS.
    # None when no arrival data exists (in-memory fallback, or sim ended with
    # no responders that ever pinged "arrived").
    actual_eta_p50_seconds: float | None = None
    actual_eta_p90_seconds: float | None = None
    # Signed delta: actual_p50 minus estimated_p50. Positive = slower than estimate.
    # Suppressed when coverage is too low to be statistically meaningful.
    eta_actual_vs_estimated_p50_delta_seconds: float | None = None
    actuals_coverage_pct: float = 0.0                   # share of assigned with real arrival


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

    # Real-run enrichments — populated only on the "actual" row from
    # SERVING.ROUTE_RECOMMENDATIONS + ROUTE_LEGS aggregates.
    solver_mix: dict[str, int] | None = None            # {"weighted_flow": 12, "greedy": 3}
    elapsed_ms_p50: float | None = None
    elapsed_ms_p90: float | None = None
    degraded_leg_pct: float | None = None               # 0-1; denominator = legs w/ incident_id
    provider_status: str | None = None                  # most common non-null provider
    optimization_count: int | None = None               # distinct ROUTE_ID count


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


class IncidentGeoPoint(BaseModel):
    """Slim projection used to render incidents on the AAR map (scrubber filter)."""
    model_config = ConfigDict(extra="forbid")

    id: str                                             # UUID str
    lat: float
    lng: float
    timestamp: datetime
    severity: str
    eta_seconds: float | None                           # None if unassigned
    has_vulnerable: bool


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


class RoadAccessContext(BaseModel):
    """Snapshot of road-closure state in effect during the run."""
    model_config = ConfigDict(extra="forbid")

    feature_count: int
    hard_avoid_count: int
    soft_penalty_count: int
    provider: str | None = None
    loaded_at: datetime | None = None


class CortexAlertEvent(BaseModel):
    """One Cortex/cluster detection that fired during the run window."""
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    alert_type: str
    severity: str
    message: str | None = None
    detected_at: datetime
    sector_id: str | None = None


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
    incidents_geo: list[IncidentGeoPoint]               # for the AAR map + scrubber filter
    data_source: str                                    # "snowflake" | "in_memory"
    road_access_context: RoadAccessContext | None = None
    cortex_alerts: list[CortexAlertEvent] = Field(default_factory=list)

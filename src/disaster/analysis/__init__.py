"""
Post-disaster After Action Report (AAR).

  GET /api/analysis/{sim_run_id}
        │
        ▼
   AAR orchestrator (aar.py)
        │
        ├── load incidents + dispatches from Snowflake or IncidentStore
        ├── scorecard: assignment %, ETA percentiles, fleet distance, vuln gap
        ├── counterfactual replay (counterfactual.py) — 3 policies in parallel
        ├── vulnerability breakdown (vulnerability.py) — Python-side from victims
        └── timeline (incidents per minute since first arrival)
        ▼
   AARResponse → JSON
"""
from disaster.analysis.models import (
    AARResponse,
    AARScorecard,
    CounterfactualPanel,
    IncidentGeoPoint,
    LessonItem,
    NarrativeResponse,
    PolicyResult,
    TimelineSlice,
    VulnerabilityBreakdown,
)

__all__ = [
    "AARResponse",
    "AARScorecard",
    "CounterfactualPanel",
    "IncidentGeoPoint",
    "LessonItem",
    "NarrativeResponse",
    "PolicyResult",
    "TimelineSlice",
    "VulnerabilityBreakdown",
]

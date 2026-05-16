"""/triage/score endpoint — exposes the pure scorer for ad-hoc scoring."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from disaster.models import IncidentReport, TriageResult
from disaster.triage import score

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("/score", response_model=TriageResult)
async def score_incident(report: IncidentReport) -> TriageResult:
    """Run the START scorer. Pure: no state mutated, no persistence."""
    return score(report, current_time=datetime.now(UTC))

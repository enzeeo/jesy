"""
DisasterSimulator — generates synthetic incidents on a compressed temporal curve.

  90s demo = 4 simulated hours (compression factor 160x)

  Generate once: 200 incidents with realistic spatial + temporal distribution
  Replay     : feed them to /incidents at the demo cadence
  Idempotent : same (sim_run_id, external_id) is rejected by IncidentStore

Profile: 1960 Hilo tsunami parameters.
  - Coastal weighting: most incidents within 1 km of waterfront
  - Severity distribution: 12% Immediate, 35% Delayed, 50% Minor, 3% Deceased
  - Temporal: front-loaded (impact + 2 hours = 70% of incidents)
  - Vulnerabilities: 8% child, 18% elderly, 4% mobility-dep
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from disaster.models import (
    Breathing,
    IncidentReport,
    IncidentSource,
    Location,
    Mobility,
    Perfusion,
    Severity,
    Victim,
)

log = logging.getLogger(__name__)

# Hilo Bay center (1960 tsunami impact zone)
_HILO_CENTER = (19.7297, -155.0900)
_COASTAL_LAT = 19.7297
_COASTAL_LNG_RANGE = (-155.105, -155.075)

_SEVERITY_DIST = [
    (Severity.IMMEDIATE, 0.12),
    (Severity.DELAYED, 0.35),
    (Severity.MINOR, 0.50),
    (Severity.DECEASED, 0.03),
]

_INJURIES_BY_SEVERITY: dict[Severity, list[str]] = {
    Severity.IMMEDIATE: ["respiratory distress", "crush injury", "head trauma", "internal bleeding"],
    Severity.DELAYED: ["fracture", "laceration", "burn", "spinal pain"],
    Severity.MINOR: ["abrasion", "contusion", "mild laceration", "shock"],
    Severity.DECEASED: ["multiple trauma"],
}

_LANDMARKS = [
    "Pier 1", "Pier 2", "Pier 3", "Pier 4",
    "Bayfront Hwy", "Kamehameha Ave & Mamo St", "Banyan Drive",
    "Hilo Hawaiian Hotel", "Wailoa Harbor", "Hilo Union Elementary",
    "Reeds Bay", "Lyman Museum area", "Mooheau Bus Terminal",
    "Hilo Farmers Market", "Liliuokalani Gardens",
]


def _sample_severity(rng: random.Random) -> Severity:
    roll = rng.random()
    cumulative = 0.0
    for sev, weight in _SEVERITY_DIST:
        cumulative += weight
        if roll <= cumulative:
            return sev
    return Severity.MINOR


def _sample_age(rng: random.Random) -> int:
    """Skew toward 30-60 with tails for child/elderly."""
    bucket = rng.random()
    if bucket < 0.08:
        return rng.randint(3, 12)        # child
    if bucket < 0.26:
        return rng.randint(75, 92)       # elderly
    return rng.randint(18, 70)


def _sample_vulnerabilities(rng: random.Random, age: int) -> list[str]:
    vulns = []
    if age <= 12:
        vulns.append("child")
    if age >= 75:
        vulns.append("elderly")
    if rng.random() < 0.04:
        vulns.append("mobility_dependent")
    if rng.random() < 0.03:
        vulns.append("medical_dependency")
    return vulns


def _sample_location(rng: random.Random) -> Location:
    """Coastal-weighted spatial distribution."""
    lat_jitter = rng.gauss(0.0, 0.002)
    lng = rng.uniform(*_COASTAL_LNG_RANGE)
    landmark = rng.choice(_LANDMARKS)
    return Location(
        lat=_COASTAL_LAT + lat_jitter,
        lng=lng,
        description=f"{landmark} area",
    )


def _build_victim(rng: random.Random, severity: Severity) -> Victim:
    age = _sample_age(rng)
    injuries = rng.sample(
        _INJURIES_BY_SEVERITY[severity],
        k=min(2, len(_INJURIES_BY_SEVERITY[severity])),
    )
    return Victim(
        age_estimate=age,
        injuries=injuries,
        breathing=Breathing.SPONTANEOUS if severity != Severity.DECEASED else Breathing.ABSENT,
        perfusion=Perfusion.POOR if severity == Severity.IMMEDIATE else Perfusion.NORMAL,
        mobility=(
            Mobility.WALKING if severity == Severity.MINOR
            else Mobility.CANNOT_FOLLOW_COMMANDS if severity == Severity.IMMEDIATE
            else Mobility.CAN_FOLLOW_COMMANDS
        ),
        respiratory_rate=32 if severity == Severity.IMMEDIATE else 18,
        vulnerabilities=_sample_vulnerabilities(rng, age),
    )


def _emit_delay_seconds(idx: int, total: int, demo_window_s: float = 60.0) -> float:
    """
    Front-loaded delay curve. First 50% of incidents arrive in the first
    30% of the window; tail is sparser.
    """
    pct = idx / total
    if pct < 0.5:
        return (pct / 0.5) * (demo_window_s * 0.3)
    return demo_window_s * 0.3 + ((pct - 0.5) / 0.5) * (demo_window_s * 0.7)


@dataclass
class SimEvent:
    incident: IncidentReport
    external_id: str
    delay_s: float


def generate_hilo_tsunami_profile(
    *,
    count: int = 200,
    run_id: str = "hilo-1960",
    seed: int = 42,
    demo_window_s: float = 60.0,
    impact_time: datetime | None = None,
) -> list[SimEvent]:
    """
    Pre-generate `count` incidents. Deterministic given `seed` — same profile
    every run, so the demo is reproducible.
    """
    rng = random.Random(seed)
    if impact_time is None:
        impact_time = datetime.now(UTC)

    events: list[SimEvent] = []
    for i in range(count):
        sev = _sample_severity(rng)
        delay_s = _emit_delay_seconds(i, count, demo_window_s)
        # Simulated incident timestamps are spread across 4 sim hours
        sim_minutes = (i / count) * 240.0
        ts = impact_time + timedelta(minutes=sim_minutes)
        incident = IncidentReport(
            timestamp=ts,
            source=IncidentSource.SIMULATED,
            location=_sample_location(rng),
            victims=[_build_victim(rng, sev)],
            severity=sev,
            confidence=1.0,
            sim_run_id=run_id,
            call_transcript="",
        )
        events.append(SimEvent(
            incident=incident,
            external_id=f"{run_id}-{i:04d}",
            delay_s=delay_s,
        ))
    return events


class DisasterSimulator:
    """
    Async runner: kicks off the simulation, drops incidents into the system
    over `demo_window_s`. Idempotent — same run_id replay is safe.
    """

    def __init__(
        self,
        *,
        on_incident: Callable[[IncidentReport, str], Awaitable[None]],
    ):
        self._on_incident = on_incident
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self.events_emitted = 0
        self.events_dropped = 0
        self.run_id: str | None = None

    async def start(
        self,
        *,
        count: int = 200,
        run_id: str = "hilo-1960",
        seed: int = 42,
        demo_window_s: float = 60.0,
    ) -> None:
        if self._task is not None and not self._task.done():
            log.warning("simulator already running, ignoring start")
            return
        self._stopped = False
        self.events_emitted = 0
        self.events_dropped = 0
        self.run_id = run_id
        events = generate_hilo_tsunami_profile(
            count=count, run_id=run_id, seed=seed, demo_window_s=demo_window_s,
        )
        self._task = asyncio.create_task(self._run(events), name="disaster-sim")

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self, events: list[SimEvent]) -> None:
        start = asyncio.get_running_loop().time()
        for event in events:
            if self._stopped:
                return
            target = start + event.delay_s
            now = asyncio.get_running_loop().time()
            await asyncio.sleep(max(0.0, target - now))
            try:
                await self._on_incident(event.incident, event.external_id)
                self.events_emitted += 1
            except Exception as e:  # noqa: BLE001 — caller-supplied handler may raise anything
                self.events_dropped += 1
                log.warning("simulator: on_incident failed external_id=%s err=%s",
                            event.external_id, e)

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "run_id": self.run_id,
            "events_emitted": self.events_emitted,
            "events_dropped": self.events_dropped,
        }

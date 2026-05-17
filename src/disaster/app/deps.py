"""
Shared dependencies. Single AppState bag attached to the FastAPI app at startup.

Held by app.state.disaster so request handlers can reach it via Request.app.state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from disaster.events import EventBroker
from disaster.snowflake import SnowflakeWriter
from disaster.store import (
    ActiveDispatchStore,
    IncidentStore,
    ResponderStore,
    RoadAccessStore,
    RouteRecommendationStore,
)
from disaster.tracking import ResponderTrackingStore

if TYPE_CHECKING:
    from disaster.llm import LLMClient


@dataclass
class AppState:
    incidents: IncidentStore = field(default_factory=IncidentStore)
    responders: ResponderStore = field(default_factory=ResponderStore)
    route_recommendations: RouteRecommendationStore = field(default_factory=RouteRecommendationStore)
    active_dispatches: ActiveDispatchStore = field(default_factory=ActiveDispatchStore)
    road_access: RoadAccessStore = field(default_factory=RoadAccessStore)
    responder_tracking: ResponderTrackingStore = field(default_factory=ResponderTrackingStore)
    events: EventBroker = field(default_factory=EventBroker)
    snowflake: SnowflakeWriter | None = None        # injected at startup
    llm_client: LLMClient | None = None             # injected at startup
    elevenlabs_secret: bytes | None = None          # for HMAC verification

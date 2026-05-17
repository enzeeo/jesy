"""
Shared dependencies. Single AppState bag attached to the FastAPI app at startup.

Held by app.state.disaster so request handlers can reach it via Request.app.state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

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

    # ElevenLabs Conversational AI: maps the agent's conversation_id to the
    # provisional incident it created, so retried tool calls don't duplicate.
    # Single-caller demo scope — in-memory, no eviction.
    voice_conversations: dict[str, UUID] = field(default_factory=dict)

    # The sim_run_id of the run currently in progress. Set by /sim/start and
    # cleared by /sim/stop. Every incident-write path stamps incident.sim_run_id
    # from this field when it's not None, so the AAR for that run can scope to
    # exactly the incidents that arrived during it (caller-ui submissions and
    # /demo/trigger-call would otherwise have sim_run_id=None and be invisible
    # to the AAR). Singleton: /sim/start returns 409 if this is already set.
    active_sim_run_id: str | None = None

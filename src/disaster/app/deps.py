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
from disaster.store import IncidentStore, ResponderStore

if TYPE_CHECKING:
    from disaster.llm import LLMClient


@dataclass
class AppState:
    incidents: IncidentStore = field(default_factory=IncidentStore)
    responders: ResponderStore = field(default_factory=ResponderStore)
    events: EventBroker = field(default_factory=EventBroker)
    snowflake: SnowflakeWriter | None = None        # injected at startup
    llm_client: LLMClient | None = None             # injected at startup
    elevenlabs_secret: bytes | None = None          # for HMAC verification

    # ElevenLabs Conversational AI: maps the agent's conversation_id to the
    # provisional incident it created, so retried tool calls don't duplicate.
    # Single-caller demo scope — in-memory, no eviction.
    voice_conversations: dict[str, UUID] = field(default_factory=dict)

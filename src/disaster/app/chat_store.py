"""In-memory multi-turn chat sessions for the dispatch console."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass
class StoredChatMessage:
    role: str
    content: str
    sources: list[dict]
    warehouse_backed: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ChatSession:
    id: UUID
    scope: str
    scope_ref_id: str | None
    title: str
    messages: list[StoredChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ChatStore:
    def __init__(self) -> None:
        self._sessions: dict[UUID, ChatSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        scope: str = "global",
        scope_ref_id: str | None = None,
        title: str | None = None,
    ) -> ChatSession:
        session = ChatSession(
            id=uuid4(),
            scope=scope,
            scope_ref_id=scope_ref_id,
            title=title or _default_title(scope, scope_ref_id),
        )
        async with self._lock:
            self._sessions[session.id] = session
        return session

    async def get(self, session_id: UUID) -> ChatSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def append(
        self,
        session_id: UUID,
        *,
        role: str,
        content: str,
        sources: list[dict],
        warehouse_backed: bool,
    ) -> ChatSession | None:
        msg = StoredChatMessage(
            role=role,
            content=content,
            sources=sources,
            warehouse_backed=warehouse_backed,
        )
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.messages.append(msg)
            return session


def _default_title(scope: str, scope_ref_id: str | None) -> str:
    if scope == "incident" and scope_ref_id:
        return f"Incident {scope_ref_id[:8]}…"
    if scope == "sector" and scope_ref_id:
        return f"Sector {scope_ref_id.upper()}"
    if scope == "cluster" and scope_ref_id:
        return f"Cluster {scope_ref_id[:12]}…"
    return "Dispatch console"

"""Dispatch console chat — multi-turn, Snowflake-grounded when available."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from disaster.app.chat_store import ChatStore
from disaster.snowflake.chat_backend import ChatContext, ChatTurn, build_chat_backend

if TYPE_CHECKING:
    from disaster.app.deps import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _state(req: Request) -> AppState:
    return req.app.state.disaster


def _chat_store(state: AppState) -> ChatStore:
    store = getattr(state, "chat_store", None)
    if store is None:
        store = ChatStore()
        state.chat_store = store
    return store


class CreateSessionBody(BaseModel):
    scope: Literal["global", "incident", "sector", "cluster"] = "global"
    scope_ref_id: str | None = None
    title: str | None = None


class ChatContextBody(BaseModel):
    incident_id: str | None = None
    sector: str | None = None
    cluster_id: str | None = None


class PostMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: ChatContextBody | None = None


def _session_to_dict(session) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "scope": session.scope,
        "scope_ref_id": session.scope_ref_id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "warehouse_backed": m.warehouse_backed,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    }


def _resolve_context(body: PostMessageBody | None, session, *, sim_run_id: str | None) -> ChatContext:
    if body and body.context:
        return ChatContext(
            incident_id=body.context.incident_id,
            sector=body.context.sector,
            cluster_id=body.context.cluster_id,
            sim_run_id=sim_run_id,
        )
    if session.scope == "incident" and session.scope_ref_id:
        return ChatContext(incident_id=session.scope_ref_id, sim_run_id=sim_run_id)
    if session.scope == "sector" and session.scope_ref_id:
        return ChatContext(sector=session.scope_ref_id, sim_run_id=sim_run_id)
    if session.scope == "cluster" and session.scope_ref_id:
        return ChatContext(cluster_id=session.scope_ref_id, sim_run_id=sim_run_id)
    return ChatContext(sim_run_id=sim_run_id)


@router.post("/sessions")
async def create_session(body: CreateSessionBody, request: Request) -> dict[str, Any]:
    session = await _chat_store(_state(request)).create(
        scope=body.scope,
        scope_ref_id=body.scope_ref_id,
        title=body.title,
    )
    return _session_to_dict(session)


@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID, request: Request) -> dict[str, Any]:
    session = await _chat_store(_state(request)).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_to_dict(session)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: UUID,
    body: PostMessageBody,
    request: Request,
) -> dict[str, Any]:
    state = _state(request)
    store = _chat_store(state)
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    await store.append(session_id, role="user", content=body.message, sources=[], warehouse_backed=True)

    runner = getattr(state, "_sf_query_runner", None)
    backend = await build_chat_backend(
        runner,
        get_incidents=state.incidents.list,
        get_responders=state.responders.list,
    )
    sim_run_id = getattr(state, "active_sim_run_id", None)
    context = _resolve_context(body, session, sim_run_id=sim_run_id)
    history = [
        ChatTurn(role=m.role, content=m.content)
        for m in session.messages[:-1]
    ]
    reply = await backend.reply(body.message, context=context, history=history)

    sources_payload = [
        {"query_id": s.query_id, "tables": s.tables, "row_count": s.row_count}
        for s in reply.sources
    ]
    await store.append(
        session_id,
        role="assistant",
        content=reply.content,
        sources=sources_payload,
        warehouse_backed=reply.warehouse_backed,
    )

    updated = await store.get(session_id)
    assert updated is not None
    return {
        "reply": {
            "content": reply.content,
            "sources": sources_payload,
            "warehouse_backed": reply.warehouse_backed,
        },
        "session": _session_to_dict(updated),
    }

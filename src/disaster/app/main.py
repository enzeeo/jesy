"""
FastAPI application factory.

Lifespan:
  startup → snowflake_writer.start()
  shutdown → snowflake_writer.stop() (drains queue with timeout)

.env loaded by `_load_env()` before create_app() reads any env vars.
Shell env vars win — override=False.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI

from disaster.app.deps import AppState
from disaster.app.exception_handler import register as register_exception_handler
from disaster.app.middleware import register_elevenlabs_hmac
from disaster.app.routes.cortex import router as cortex_router
from disaster.app.routes.demo import router as demo_router
from disaster.app.routes.events import router as events_router
from disaster.app.routes.incidents import router as incidents_router
from disaster.app.routes.intake import router as intake_router
from disaster.app.routes.responders import router as responders_router
from disaster.app.routes.routing import router as routing_router
from disaster.app.routes.sim import router as sim_router
from disaster.app.routes.tiles import router as tiles_router
from disaster.app.routes.triage import router as triage_router
from disaster.llm import LLMClient, build_openai_completion, close_openai_completion
from disaster.snowflake import (
    SnowflakeWriter,
    build_snowflake_flush,
    env_configured,
    get_query_runner,
)

# Load .env from project root if present. Safe to call multiple times; safe in tests.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_PROJECT_ROOT / "frontend" / ".env.local", override=False)

log = logging.getLogger(__name__)


def _noop_snowflake_flush() -> SnowflakeWriter:
    """Default flush implementation: discard. Real connector wires in via env."""

    async def noop(table: str, rows: list[dict[str, Any]]) -> None:
        log.debug("snowflake_noop: would flush table=%s rows=%d", table, len(rows))

    return SnowflakeWriter(noop)


def create_app(
    *,
    snowflake_writer: SnowflakeWriter | None = None,
    state: AppState | None = None,
) -> FastAPI:
    """
    Build the app. Pass a custom AppState (with real LLM router etc.)
    or let the factory create defaults.
    """
    state = state or AppState()
    if snowflake_writer is not None:
        state.snowflake = snowflake_writer
    elif env_configured():
        try:
            state.snowflake = SnowflakeWriter(build_snowflake_flush())
            state._sf_query_runner = get_query_runner()
            log.info("snowflake: connected and ready for tile queries")
        except Exception as e:  # noqa: BLE001
            log.warning("snowflake: connect failed (%s) — using noop writer + in-memory tiles", e)
            state.snowflake = _noop_snowflake_flush()
    else:
        state.snowflake = _noop_snowflake_flush()
    if state.elevenlabs_secret is None:
        env_secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
        state.elevenlabs_secret = env_secret.encode() if env_secret else None

    # Wire real OpenAI client if API key present and no client injected.
    if state.llm_client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            completion = build_openai_completion(api_key, model=model)
            state.llm_client = LLMClient(completion, model=model)
            state._llm_completion = completion
            log.info("llm_client: wired OpenAI model=%s", model)
        else:
            log.warning("llm_client: OPENAI_API_KEY unset — /intake/voice will return 503")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if state.snowflake is not None:
            await state.snowflake.start()
        try:
            yield
        finally:
            if state.snowflake is not None:
                await state.snowflake.stop(drain_timeout_s=5.0)
            completion = getattr(state, "_llm_completion", None)
            if completion is not None:
                await close_openai_completion(completion)

    app = FastAPI(title="Disaster Response Coordination", lifespan=lifespan)
    app.state.disaster = state

    register_exception_handler(app)
    register_elevenlabs_hmac(app)
    app.include_router(incidents_router)
    app.include_router(triage_router)
    app.include_router(events_router)
    app.include_router(responders_router)
    app.include_router(routing_router)
    app.include_router(intake_router)
    app.include_router(tiles_router)
    app.include_router(cortex_router)
    app.include_router(sim_router)
    app.include_router(demo_router)

    # CORS: allow the Next.js dev origin (and *) for hackathon ergonomics.
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/responders")
    async def list_responders() -> list[dict]:
        units = await state.responders.list()
        return [u.model_dump(mode="json") for u in units]

    return app


# Convenience for `uvicorn disaster.app.main:app`
app = create_app()

"""
Top-level FastAPI exception handler.

We ban `except Exception:` via ruff (BLE001). Everything below the handler must
either name its exception class or let it bubble. This handler is the absolute
backstop for things we genuinely didn't anticipate. Logs full context with
request_id and returns a structured error to the caller.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from disaster.errors import (
    DisasterError,
    EmptyExtraction,
    IncompleteAssessment,
    MalformedLLMResponse,
    NoFeasibleSolution,
    SnowflakeWriteError,
    UpstreamUnavailable,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

log = logging.getLogger(__name__)


# Map our named errors to HTTP status codes. Anything not listed gets 500.
_STATUS_BY_ERROR: dict[type[DisasterError], int] = {
    UpstreamUnavailable: 503,
    MalformedLLMResponse: 502,
    EmptyExtraction: 422,
    IncompleteAssessment: 422,
    SnowflakeWriteError: 500,
    NoFeasibleSolution: 503,
}


def register(app: FastAPI) -> None:
    """Wire all named-error handlers + the unknown-error backstop on `app`."""
    from fastapi import Request as _Request  # lazy: avoid hard FastAPI dep at import
    from fastapi.responses import JSONResponse as _JSONResponse

    async def _handle_named(request: _Request, exc: DisasterError) -> _JSONResponse:
        status = _STATUS_BY_ERROR.get(type(exc), 500)
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        log.warning(
            "request_failed request_id=%s path=%s method=%s error=%s message=%s",
            request_id, request.url.path, request.method, type(exc).__name__, exc,
        )
        return _JSONResponse(
            status_code=status,
            content={
                "error": type(exc).__name__,
                "message": str(exc),
                "request_id": request_id,
            },
            headers={"x-request-id": request_id},
        )

    async def _handle_unknown(request: _Request, exc: BaseException) -> _JSONResponse:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        # Full context: this is the backstop. Print the type and a truncated repr
        # plus stack so we can find the root cause from logs alone.
        log.exception(
            "unhandled_exception request_id=%s path=%s method=%s error=%s",
            request_id, request.url.path, request.method, type(exc).__name__,
        )
        return _JSONResponse(
            status_code=500,
            content={
                "error": "InternalError",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            },
            headers={"x-request-id": request_id},
        )

    app.add_exception_handler(DisasterError, _handle_named)
    app.add_exception_handler(Exception, _handle_unknown)

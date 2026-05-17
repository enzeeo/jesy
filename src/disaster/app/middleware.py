"""ElevenLabs webhook HMAC verification middleware."""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

log = logging.getLogger(__name__)


def register_elevenlabs_hmac(app: FastAPI) -> None:
    """
    Verify HMAC-SHA256 signature on /intake/voice and all /intake/voice/* paths
    (server-tool endpoints called by the ElevenLabs Conversational AI agent).
    If app.state.disaster.elevenlabs_secret is unset (dev mode), allow all
    requests through with a warning.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def verify_sig(request: Request, call_next):
        if not request.url.path.startswith("/intake/voice"):
            return await call_next(request)

        secret = request.app.state.disaster.elevenlabs_secret
        if secret is None:
            log.warning("elevenlabs_hmac: secret unset, allowing unverified webhook (dev mode)")
            return await call_next(request)

        body = await request.body()
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        provided = request.headers.get("x-elevenlabs-signature", "")
        if not hmac.compare_digest(expected, provided):
            return JSONResponse(
                status_code=401,
                content={"error": "invalid signature"},
            )

        # Re-inject the body since we already read it
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        return await call_next(request)

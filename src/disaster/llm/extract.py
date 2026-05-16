"""
LLM-driven structured extraction from a voice transcript.

  transcript ──▶ llm_router.call(assembled_prompt + transcript)
                          │
                          ▼
                     raw JSON content
                          │
                          ├── parse JSON ─── on fail, retry once with strict reminder
                          │
                          ▼
                     IncidentReport.model_validate(...)
                          │
                          ├── ValidationError ──▶ MalformedLLMResponse
                          │
                          ▼
                     IncidentReport (validated)

Confidence calculation:
  - 1.0 if all required fields present + START-classifiable
  - 0.5 if extraction succeeded but assessment will be incomplete
  - 0.0 if extraction returned empty/null
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from disaster.errors import EmptyExtraction, MalformedLLMResponse
from disaster.llm.client import LLMClient
from disaster.llm.prompt import assemble_prompt
from disaster.models import IncidentReport

log = logging.getLogger(__name__)

_STRICT_RETRY = (
    "\n\nIMPORTANT: Your previous response was not valid JSON. "
    "Respond with ONLY a JSON object matching the IncidentReport schema. "
    "No prose, no markdown fences.\n"
)


def _parse_json(raw: str) -> dict[str, Any]:
    """Tolerant JSON parse: strips markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` style fences
        text = text.strip("`")
        if text.lower().startswith("json\n"):
            text = text[5:]
        text = text.rstrip("`").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise MalformedLLMResponse(f"non-JSON response: {e}") from e
    if not isinstance(parsed, dict):
        raise MalformedLLMResponse(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


async def extract_incident(
    client: LLMClient,
    transcript: str,
    *,
    call_state: dict[str, Any] | None = None,
) -> IncidentReport:
    """
    Run LLM extraction. One strict-retry on malformed JSON. Pydantic-validated.

    Raises:
      EmptyExtraction      — model returned no content
      MalformedLLMResponse — could not parse JSON or schema validation failed
      UpstreamUnavailable  — OpenAI connection failure (bubbles from client)
    """
    base_prompt = assemble_prompt(call_state) + "\nTRANSCRIPT:\n" + transcript + "\n"
    response = await client.call(base_prompt)
    content = (response or {}).get("content", "").strip()
    if not content:
        raise EmptyExtraction("LLM returned empty content")

    try:
        parsed = _parse_json(content)
    except MalformedLLMResponse as first_err:
        log.warning("extract: first attempt non-JSON, retrying strict: %s", first_err)
        retry_response = await client.call(base_prompt + _STRICT_RETRY)
        retry_content = (retry_response or {}).get("content", "").strip()
        if not retry_content:
            raise EmptyExtraction("LLM returned empty content on retry") from first_err
        parsed = _parse_json(retry_content)   # may raise again — that's fine, surfaces clearly

    parsed.setdefault("call_transcript", transcript)
    parsed.setdefault("confidence", 1.0)

    try:
        return IncidentReport.model_validate(parsed)
    except ValidationError as e:
        raise MalformedLLMResponse(f"schema validation failed: {e}") from e

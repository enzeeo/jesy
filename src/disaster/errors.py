"""Named exception classes. Catch-all `except Exception` is banned (see ruff BLE rules)."""


class DisasterError(Exception):
    """Base for all named errors in this codebase."""


# LLM / inference layer
class UpstreamUnavailable(DisasterError):
    """OpenAI returned a connection-level failure or 5xx."""


class MalformedLLMResponse(DisasterError):
    """LLM returned response that failed JSON parse or pydantic validation."""


class EmptyExtraction(DisasterError):
    """LLM returned no extractable structured data."""


# Triage
class IncompleteAssessment(DisasterError):
    """START scorer received insufficient input to classify; default to DELAYED + flag."""


# Snowflake
class SnowflakeWriteError(DisasterError):
    """Batch flush to Snowflake failed; rows dropped, dropped_count incremented."""


# Routing
class NoFeasibleSolution(DisasterError):
    """OR-Tools VRP solver could not find a solution; fall back to greedy."""

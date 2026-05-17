"""
Prompt assembly: [GLOBAL_PROTOCOL] + [DISASTER_CONTEXT] + [CALL_STATE].

The first two segments are byte-identical across every call so Tensormesh's
KV-cache hits at maximum rate. Drift of even one whitespace character breaks
the cache silently and the 92% claim collapses to 0%.

The byte-identity test (test_prompt_byte_identity.py) pins PREFIX_SHA256.
Any change to GLOBAL_PROTOCOL or DISASTER_CONTEXT fails the test and must
be re-pinned intentionally.
"""
from __future__ import annotations

import hashlib
from typing import Final

# ── Segment 1: protocol, never changes per deployment ─────────────────────────
GLOBAL_PROTOCOL: Final[str] = (
    "You are an emergency intake assistant. Extract structured incident data from a "
    "live phone call. Stay calm. Confirm location twice. Apply START triage by "
    "asking about: walking ability, breathing (spontaneous or after airway), "
    "respiratory rate, capillary refill or radial pulse, ability to follow simple "
    "commands. Identify vulnerabilities: age, mobility, medical dependencies, "
    "presence of children. Never promise response times. Never give medical advice "
    "beyond basic life-safety. Do not disconnect until structured data is confirmed.\n"
    "Respond with JSON only matching the IncidentReport schema. No prose.\n"
)

# ── Segment 2: disaster context for current deployment ────────────────────────
# This block is loaded from the active DisasterProfile at startup.
# For demo: Texas Gulf Coast flood surge parameters.
DISASTER_CONTEXT: Final[str] = (
    "ACTIVE DISASTER: Hurricane flood surge, Galveston Texas, coastal radius 8 km.\n"
    "Expected injuries: drowning, blunt trauma, lacerations, hypothermia, crush "
    "injuries from debris. Vulnerable populations: coastal residents, tourists at "
    "Seawall Boulevard hotels, dock workers at Pier 21, patients near the UTMB "
    "Health campus. Communication may be intermittent. Power may be out in west "
    "island sector. Roads flooded: Seawall Boulevard low points, Harborside Drive, "
    "Broadway Avenue J near 25th Street.\n"
)

# ── Pinned SHA256 of the prefix ───────────────────────────────────────────────
# Regenerate intentionally if either segment above changes:
#   python -c "from disaster.llm.prompt import prefix_bytes; \
#              import hashlib; print(hashlib.sha256(prefix_bytes()).hexdigest())"
PREFIX_SHA256: Final[str] = (
    "2433438ff24af6036a07d9b234213114a625af6c1623d2f92509da90321697d0"
)


def prefix_bytes() -> bytes:
    """Concatenated bytes of [GLOBAL_PROTOCOL] + [DISASTER_CONTEXT]."""
    return (GLOBAL_PROTOCOL + DISASTER_CONTEXT).encode("utf-8")


def assemble_prompt(call_state: dict[str, object] | None = None) -> str:
    """
    Build the full prompt. Prefix is byte-identical for cache hits.
    Tail varies per call.
    """
    prefix = GLOBAL_PROTOCOL + DISASTER_CONTEXT
    if not call_state:
        tail = "CALL STATE: (call just started, no data yet)\n"
    else:
        # Deterministic key ordering so cache behavior is reproducible.
        lines = [f"  {k}: {call_state[k]}" for k in sorted(call_state.keys())]
        tail = "CALL STATE:\n" + "\n".join(lines) + "\n"
    return prefix + tail


def current_prefix_sha256() -> str:
    """Compute the current hash; used by the byte-identity test."""
    return hashlib.sha256(prefix_bytes()).hexdigest()

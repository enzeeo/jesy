"""
Byte-identity test for the cached prefix (P1 #7).

The Tensormesh KV-cache hits only when the prompt prefix is byte-identical
across calls. A single stray whitespace or trailing newline breaks the hit
silently — the infra panel will report 0% cache hit rate and you won't know
why until demo day.

This test is the first line of defense:
  1. Pins the SHA256 of [GLOBAL_PROTOCOL] + [DISASTER_CONTEXT]
  2. Asserts the prefix is byte-identical across multiple call_state variations
  3. Asserts only the tail varies
"""
import hashlib

import pytest

from disaster.llm.prompt import (
    DISASTER_CONTEXT,
    GLOBAL_PROTOCOL,
    PREFIX_SHA256,
    assemble_prompt,
    current_prefix_sha256,
    prefix_bytes,
)

PREFIX_LEN = len(GLOBAL_PROTOCOL) + len(DISASTER_CONTEXT)


def test_prefix_sha256_matches_pinned():
    """
    If this fails: the GLOBAL_PROTOCOL or DISASTER_CONTEXT changed.
    Regenerate PREFIX_SHA256 in src/disaster/llm/prompt.py with:
        uv run python -c "from disaster.llm.prompt import current_prefix_sha256; \\
                         print(current_prefix_sha256())"
    """
    assert current_prefix_sha256() == PREFIX_SHA256


def test_prefix_bytes_decode_round_trip():
    """Prefix is valid UTF-8 (would break Tensormesh tokenization if not)."""
    bytes_ = prefix_bytes()
    decoded = bytes_.decode("utf-8")
    assert decoded == GLOBAL_PROTOCOL + DISASTER_CONTEXT


# ── Cross-call prefix identity ───────────────────────────────────────────────

@pytest.mark.parametrize("call_state", [
    None,
    {},
    {"victim_count": 1},
    {"victim_count": 3, "location": "Pier 4"},
    {"breathing": "irregular", "perfusion": "poor", "respiratory_rate": 32},
    {"caller_name": "Anonymous", "callback_available": True},
])
def test_prefix_byte_identical_across_call_states(call_state):
    """
    Whatever the call state, the prefix bytes must match the pinned hash.
    This is what makes Tensormesh's KV-cache hit.
    """
    full = assemble_prompt(call_state)
    prefix = full.encode("utf-8")[:PREFIX_LEN]
    assert hashlib.sha256(prefix).hexdigest() == PREFIX_SHA256


def test_two_different_call_states_have_identical_prefix():
    """Direct comparison: prefix bytes are the same regardless of tail."""
    a = assemble_prompt({"victim_count": 1}).encode("utf-8")[:PREFIX_LEN]
    b = assemble_prompt({"location": "Banyan Drive", "victim_count": 5}).encode("utf-8")[:PREFIX_LEN]
    c = assemble_prompt(None).encode("utf-8")[:PREFIX_LEN]
    assert a == b == c


def test_tail_differs_when_call_state_differs():
    """Sanity: the tail actually changes, so we're not just hashing empty strings."""
    a = assemble_prompt({"victim_count": 1})
    b = assemble_prompt({"victim_count": 5})
    assert a != b
    # but prefix is still identical
    assert a[:PREFIX_LEN] == b[:PREFIX_LEN]


def test_call_state_keys_are_sorted_for_determinism():
    """
    Same dict, different insertion order → identical prompt.
    Without this, dict ordering would cause the tail to differ and break
    deterministic eval comparisons.
    """
    a = assemble_prompt({"a": 1, "b": 2, "c": 3})
    b = assemble_prompt({"c": 3, "a": 1, "b": 2})
    assert a == b


# ── Guard against accidental edits ───────────────────────────────────────────

def test_global_protocol_minimum_length():
    """If somebody accidentally truncates the protocol, this catches it."""
    assert len(GLOBAL_PROTOCOL) > 400


def test_disaster_context_minimum_length():
    assert len(DISASTER_CONTEXT) > 200


def test_prefix_does_not_contain_call_state_marker():
    """The 'CALL STATE:' marker must live in the tail, never in the prefix."""
    assert "CALL STATE:" not in GLOBAL_PROTOCOL
    assert "CALL STATE:" not in DISASTER_CONTEXT

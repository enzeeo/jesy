"""Tests for snowflake/connection.py env detection + auth method selection."""
from __future__ import annotations

import os

import pytest

from disaster.snowflake.connection import _SCHEMAS, _connect_params, _row_to_columns, env_configured

# Required base
_BASE = {"SNOWFLAKE_ACCOUNT": "xy12345", "SNOWFLAKE_USER": "demo"}


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all SNOWFLAKE_* env vars before each test for isolation."""
    for k in list(os.environ):
        if k.startswith("SNOWFLAKE_"):
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ── env_configured() ─────────────────────────────────────────────────────────

def test_env_configured_false_when_nothing_set(clean_env):
    assert env_configured() is False


def test_env_configured_false_when_only_password_no_account(clean_env):
    clean_env.setenv("SNOWFLAKE_PASSWORD", "x")
    assert env_configured() is False


def test_env_configured_false_when_account_user_but_no_auth(clean_env):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    assert env_configured() is False


def test_env_configured_true_with_password(clean_env):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PASSWORD", "secret")
    assert env_configured() is True


def test_env_configured_true_with_keypair(clean_env, tmp_path):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    fake_key = tmp_path / "fake.p8"
    fake_key.write_text("(not a real key — just for env_configured check)")
    clean_env.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(fake_key))
    # env_configured doesn't actually parse the key, just checks presence
    assert env_configured() is True


# ── _connect_params() picks the right auth ───────────────────────────────────

def test_connect_params_uses_password_when_set(clean_env):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PASSWORD", "secret")
    params = _connect_params()
    assert params["password"] == "secret"
    assert "private_key" not in params
    assert params["account"] == "xy12345"
    assert params["user"] == "demo"


def test_connect_params_uses_keypair_when_path_set(clean_env, tmp_path):
    # Generate a real RSA key so _load_private_key_bytes() succeeds
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test.p8"
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))

    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(key_path))

    params = _connect_params()
    assert "password" not in params
    assert "private_key" in params
    assert isinstance(params["private_key"], bytes)
    # PKCS#8 DER bytes are non-trivial
    assert len(params["private_key"]) > 100


def test_connect_params_prefers_keypair_over_password(clean_env, tmp_path):
    """When both are set, key-pair wins (more secure)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test.p8"
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))

    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(key_path))
    clean_env.setenv("SNOWFLAKE_PASSWORD", "should-be-ignored")

    params = _connect_params()
    assert "password" not in params
    assert "private_key" in params


def test_connect_params_includes_warehouse_db_schema_defaults(clean_env):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PASSWORD", "x")
    params = _connect_params()
    assert params["warehouse"] == "DISASTER_WH"
    assert params["database"] == "DISASTER_DB"
    assert params["schema"] == "CLEAN"


def test_connect_params_overrides_warehouse_db_schema(clean_env):
    for k, v in _BASE.items():
        clean_env.setenv(k, v)
    clean_env.setenv("SNOWFLAKE_PASSWORD", "x")
    clean_env.setenv("SNOWFLAKE_WAREHOUSE", "CUSTOM_WH")
    clean_env.setenv("SNOWFLAKE_DATABASE", "CUSTOM_DB")
    clean_env.setenv("SNOWFLAKE_SCHEMA", "CUSTOM_SCHEMA")
    params = _connect_params()
    assert params["warehouse"] == "CUSTOM_WH"
    assert params["database"] == "CUSTOM_DB"
    assert params["schema"] == "CUSTOM_SCHEMA"


def test_serving_responder_arrivals_schema_is_flushable():
    row = {
        "ASSIGNMENT_ID": "assignment-1",
        "RESPONDER_ID": "responder-1",
        "CALLSIGN": "ALS-1",
        "INCIDENT_ID": "incident-1",
        "CLUSTER_ID": None,
        "ARRIVAL_TIMESTAMP": "2026-05-17T12:00:00Z",
        "PING_LAT": 19.701,
        "PING_LNG": -155.0,
        "ACCURACY_M": 8,
        "ROUTE_ID": "route-1",
        "DETECTION_METHOD": "geofence_two_pings",
        "DISTANCE_M": 12.5,
    }

    table_key = "SERVING.RESPONDER_ARRIVALS"
    assert table_key in _SCHEMAS
    assert _row_to_columns(table_key, row) == [row[column] for column in _SCHEMAS[table_key]]

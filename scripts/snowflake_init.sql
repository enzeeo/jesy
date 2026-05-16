-- Snowflake schema for Hilo Dispatch (hackathon).
-- Idempotent: safe to run repeatedly.
--
-- Run via:
--   snowsql -a <account> -u <user> -d <db> -s <schema> -w <warehouse> -f scripts/snowflake_init.sql
-- or:
--   uv run python scripts/snowflake_smoke.py --init
--
-- Column types match what _row_to_columns in src/disaster/snowflake/connection.py
-- emits. If you change one, change both.

CREATE DATABASE IF NOT EXISTS DISASTER_DB;
CREATE SCHEMA IF NOT EXISTS DISASTER_DB.OPERATIONAL;

USE DATABASE DISASTER_DB;
USE SCHEMA OPERATIONAL;

-- ── incidents ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id                    VARCHAR(36)   NOT NULL,    -- IncidentReport.id (UUID)
    timestamp             TIMESTAMP_TZ  NOT NULL,
    source                VARCHAR(20)   NOT NULL,    -- voice | simulated | manual
    status                VARCHAR(20)   NOT NULL,    -- new | dispatched | en_route | on_scene | resolved | partial
    lat                   FLOAT         NOT NULL,
    lng                   FLOAT         NOT NULL,
    location_description  VARCHAR(500)  NOT NULL,
    severity              VARCHAR(20)   NOT NULL,    -- Immediate | Delayed | Minor | Deceased
    priority_score        FLOAT         NOT NULL,
    victim_count          NUMBER        NOT NULL,
    vulnerabilities       VARCHAR(500),              -- comma-joined from victim flags
    confidence            FLOAT         NOT NULL,
    sim_run_id            VARCHAR(64),
    -- Append-only fact table. Multiple rows per incident_id are expected
    -- (one per state mutation). Latest-row semantics via QUALIFY ROW_NUMBER.
    _ingested_at          TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP()
);

CREATE INDEX IF NOT EXISTS idx_incidents_ts ON incidents(timestamp);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);

-- ── voice_calls ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_calls (
    incident_id           VARCHAR(36)   NOT NULL,
    transcript_length     NUMBER        NOT NULL,
    model                 VARCHAR(64)   NOT NULL,
    tokens                NUMBER        NOT NULL,
    _ingested_at          TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP()
);

-- ── responder_dispatches ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS responder_dispatches (
    responder_id          VARCHAR(36)   NOT NULL,
    incident_id           VARCHAR(36)   NOT NULL,
    dispatched_at         TIMESTAMP_TZ  NOT NULL,
    distance_km           FLOAT         NOT NULL,
    eta_seconds           FLOAT         NOT NULL,
    solver                VARCHAR(20)   NOT NULL,    -- greedy | vrp
    _ingested_at          TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP()
);

-- ── cortex_alerts ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cortex_alerts (
    alert_type            VARCHAR(40)   NOT NULL,    -- cluster | anomaly | gap
    severity              VARCHAR(40)   NOT NULL,    -- info | warning | critical
    message               VARCHAR(500)  NOT NULL,
    detected_at           TIMESTAMP_TZ  NOT NULL,
    _ingested_at          TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP()
);

-- ── Verify ───────────────────────────────────────────────────────────────────
SHOW TABLES IN SCHEMA DISASTER_DB.OPERATIONAL;

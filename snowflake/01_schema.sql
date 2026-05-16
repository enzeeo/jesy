-- Apply with: snowsql -f 01_schema.sql
-- Or paste into a Snowflake worksheet sequentially.

USE WAREHOUSE COMPUTE_WH;
USE DATABASE DISASTER_RELIEF;
USE SCHEMA PUBLIC;

-- =============================================================
-- PROFILES
-- =============================================================
CREATE TABLE IF NOT EXISTS PROFILES (
  profile_id          STRING PRIMARY KEY,
  device_id           STRING,
  name                STRING,
  age                 NUMBER,
  conditions          ARRAY,
  devices_owned       ARRAY,
  emergency_contact   VARIANT,
  payload             VARIANT,
  created_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- INCIDENTS_RAW (ingest table)
-- =============================================================
CREATE TABLE IF NOT EXISTS INCIDENTS_RAW (
  incident_id         STRING PRIMARY KEY,
  profile_id          STRING,
  device_id           STRING,
  lat                 FLOAT,
  lng                 FLOAT,
  accuracy_m          FLOAT,
  location_source     STRING,         -- 'gps' | 'place_description_udf' | 'manual'
  location_confidence FLOAT,
  raw_text            STRING,
  needs               VARIANT,
  inventory_have      ARRAY,
  inventory_need      ARRAY,
  ts                  TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- INCIDENTS_ENRICHED — physical table written by TRIAGE_TASK
-- =============================================================
CREATE TABLE IF NOT EXISTS INCIDENTS_ENRICHED (
  incident_id         STRING PRIMARY KEY,
  profile_id          STRING,
  device_id           STRING,
  lat                 FLOAT,
  lng                 FLOAT,
  raw_text            STRING,
  severity            VARIANT,
  triage_status       STRING DEFAULT 'ok',   -- 'ok' | 'degraded'
  summary             STRING,
  embedding           VECTOR(FLOAT, 768),
  status              STRING DEFAULT 'open', -- 'open'|'assigned'|'in_progress'|'resolved'
  enriched_at         TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- RESPONDERS
-- =============================================================
CREATE TABLE IF NOT EXISTS RESPONDERS (
  responder_id        STRING PRIMARY KEY,
  type                STRING,         -- police|fire|ems|paramedic|nurse|doctor|volunteer
  callsign            STRING,
  current_lat         FLOAT,
  current_lng         FLOAT,
  status              STRING DEFAULT 'available' -- 'available'|'busy'|'offline'
);

-- =============================================================
-- ASSIGNMENTS
-- =============================================================
CREATE TABLE IF NOT EXISTS ASSIGNMENTS (
  assignment_id       STRING PRIMARY KEY,
  incident_id         STRING,
  responder_id        STRING,
  resource_type       STRING,
  eta_sec             NUMBER,
  status              STRING DEFAULT 'enroute',   -- 'enroute'|'on_scene'|'completed'
  assigned_at         TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- UNMET_RESOURCE_NEEDS (visible partial assignments)
-- =============================================================
CREATE TABLE IF NOT EXISTS UNMET_RESOURCE_NEEDS (
  incident_id         STRING,
  resource_type       STRING,
  quantity_needed     NUMBER,
  reason              STRING,         -- 'no_available_responder' | 'responder_offline'
  updated_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- ROUTES (Mapbox polyline cache)
-- =============================================================
CREATE TABLE IF NOT EXISTS ROUTES (
  responder_id        STRING PRIMARY KEY,
  polyline            STRING,
  total_duration_sec  NUMBER,
  updated_at          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================
-- STREAM on INCIDENTS_RAW (drives TRIAGE_TASK)
-- =============================================================
CREATE OR REPLACE STREAM INCIDENT_STREAM ON TABLE INCIDENTS_RAW
  APPEND_ONLY = TRUE;

-- =============================================================================
-- Attribution Data Model — Snowflake DDL
-- =============================================================================
-- Run this script once to create the required tables.
-- Adjust warehouse / database / schema to match your environment.
-- =============================================================================

USE WAREHOUSE COMPUTE_WH;
USE DATABASE MY_DB;

CREATE SCHEMA IF NOT EXISTS ATTRIBUTION;
USE SCHEMA ATTRIBUTION;

-- ── TOUCHPOINTS ───────────────────────────────────────────────────────────────
-- One row per marketing touchpoint (ad impression, click, session, etc.)

CREATE TABLE IF NOT EXISTS TOUCHPOINTS (
    touchpoint_id   VARCHAR(64)   NOT NULL,     -- unique ID for this touch
    user_id         VARCHAR(64)   NOT NULL,     -- anonymised user / device ID
    session_id      VARCHAR(64),                -- web session ID
    channel         VARCHAR(128)  NOT NULL,     -- e.g. paid_search, organic, email
    campaign        VARCHAR(256),               -- campaign name
    source          VARCHAR(128),               -- utm_source
    medium          VARCHAR(128),               -- utm_medium
    content         VARCHAR(256),               -- utm_content / ad creative
    keyword         VARCHAR(256),               -- paid search keyword
    touched_at      TIMESTAMP_NTZ NOT NULL,
    created_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_touchpoints PRIMARY KEY (touchpoint_id)
)
CLUSTER BY (DATE_TRUNC('day', touched_at));

-- ── CONVERSIONS ───────────────────────────────────────────────────────────────
-- One row per conversion event (purchase, sign-up, lead, etc.)

CREATE TABLE IF NOT EXISTS CONVERSIONS (
    conversion_id       VARCHAR(64)       NOT NULL,
    user_id             VARCHAR(64)       NOT NULL,
    conversion_event    VARCHAR(128)      NOT NULL,   -- e.g. purchase, signup
    conversion_value    NUMBER(18, 2)     DEFAULT 0,  -- revenue / goal value
    currency            VARCHAR(3)        DEFAULT 'USD',
    order_id            VARCHAR(64),                  -- optional external ref
    converted_at        TIMESTAMP_NTZ     NOT NULL,
    created_at          TIMESTAMP_NTZ     DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_conversions PRIMARY KEY (conversion_id)
)
CLUSTER BY (DATE_TRUNC('day', converted_at));

-- ── SESSIONS ──────────────────────────────────────────────────────────────────
-- Optional enrichment table for session-level signals

CREATE TABLE IF NOT EXISTS SESSIONS (
    session_id      VARCHAR(64)   NOT NULL,
    user_id         VARCHAR(64)   NOT NULL,
    channel         VARCHAR(128),
    landing_page    VARCHAR(512),
    device_type     VARCHAR(64),     -- desktop | mobile | tablet
    country         VARCHAR(64),
    session_start   TIMESTAMP_NTZ NOT NULL,
    session_end     TIMESTAMP_NTZ,
    pageviews       INTEGER       DEFAULT 0,
    created_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_sessions PRIMARY KEY (session_id)
)
CLUSTER BY (DATE_TRUNC('day', session_start));

-- ── CHANNEL_SPEND ─────────────────────────────────────────────────────────────
-- Daily spend per channel / campaign for ROAS and CPA calculations

CREATE TABLE IF NOT EXISTS CHANNEL_SPEND (
    spend_id        VARCHAR(64)   NOT NULL,
    spend_date      DATE          NOT NULL,
    channel         VARCHAR(128)  NOT NULL,
    campaign        VARCHAR(256),
    spend_amount    NUMBER(18, 2) NOT NULL,
    impressions     INTEGER       DEFAULT 0,
    clicks          INTEGER       DEFAULT 0,
    currency        VARCHAR(3)    DEFAULT 'USD',
    created_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_channel_spend PRIMARY KEY (spend_id)
)
CLUSTER BY (spend_date);

-- ── Indexes / search optimisation ─────────────────────────────────────────────
ALTER TABLE TOUCHPOINTS  ADD SEARCH OPTIMIZATION ON EQUALITY(user_id, channel, campaign);
ALTER TABLE CONVERSIONS  ADD SEARCH OPTIMIZATION ON EQUALITY(user_id, conversion_event);
ALTER TABLE CHANNEL_SPEND ADD SEARCH OPTIMIZATION ON EQUALITY(channel, campaign);

-- ── Sample data (dev / testing) ───────────────────────────────────────────────
-- Uncomment to insert minimal test records

/*
INSERT INTO TOUCHPOINTS VALUES
  ('tp_001','u_001','s_001','paid_search','Brand Q1','google','cpc',NULL,'running shoes','2024-01-10 09:00:00',DEFAULT),
  ('tp_002','u_001','s_002','email',      'Jan Newsletter',NULL,NULL,NULL,NULL,'2024-01-12 14:00:00',DEFAULT),
  ('tp_003','u_001','s_003','paid_social','Retargeting Jan','facebook','cpc',NULL,NULL,'2024-01-15 18:00:00',DEFAULT);

INSERT INTO CONVERSIONS VALUES
  ('cv_001','u_001','purchase',89.99,'USD','ord_1234','2024-01-15 19:30:00',DEFAULT);

INSERT INTO CHANNEL_SPEND VALUES
  ('sp_001','2024-01-10','paid_search','Brand Q1',  250.00,15000,320,'USD',DEFAULT),
  ('sp_002','2024-01-10','email',      'Jan Newsletter', 50.00, 0,  0,'USD',DEFAULT),
  ('sp_003','2024-01-10','paid_social','Retargeting Jan',180.00,80000,410,'USD',DEFAULT);
*/

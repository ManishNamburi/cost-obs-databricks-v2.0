-- Migration 001: Initial Lakebase schema for cost-obs V2
-- Idempotent — all statements use IF NOT EXISTS or ON CONFLICT DO NOTHING.
-- Run by bootstrap_lakebase() in shared_setup_lib.py (setup job task 02).

-- ── Setup state (idempotency markers) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS setup_state (
    step          TEXT        PRIMARY KEY,
    completed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata      JSONB
);

-- ── App configuration (replaces DBFS catalog_override.json) ───────────────────

CREATE TABLE IF NOT EXISTS app_config (
    key           TEXT        PRIMARY KEY,
    value         JSONB       NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pre-populate with empty config rows so reads never 404.
INSERT INTO app_config (key, value) VALUES
    ('catalog_schema',   '{}'),
    ('workspace_filter', '{}'),
    ('auth_mode',        '"sp"'),
    ('mv_table_overrides', '{}')
ON CONFLICT (key) DO NOTHING;

-- ── Build / setup progress (replaces DBFS build_state blob) ───────────────────

CREATE TABLE IF NOT EXISTS build_progress (
    id            SERIAL      PRIMARY KEY,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        TEXT        NOT NULL,   -- running | done | failed
    payload       JSONB       NOT NULL
);

-- Only keep the last 50 build runs.
CREATE INDEX IF NOT EXISTS build_progress_recorded_at_idx ON build_progress (recorded_at DESC);

-- ── Alerts (replaces Delta alerts table) ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
    id            SERIAL      PRIMARY KEY,
    name          TEXT        NOT NULL UNIQUE,
    enabled       BOOLEAN     NOT NULL DEFAULT true,
    condition     JSONB       NOT NULL,   -- {metric, operator, threshold, ...}
    destinations  JSONB       NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_fired_at TIMESTAMPTZ
);

-- ── Alert history ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_events (
    id            SERIAL      PRIMARY KEY,
    alert_id      INT         NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    fired_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    value         DOUBLE PRECISION,
    message       TEXT
);

CREATE INDEX IF NOT EXISTS alert_events_alert_id_idx ON alert_events (alert_id, fired_at DESC);

-- ── User permissions / role overrides ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_permissions (
    subject_id    TEXT        PRIMARY KEY,  -- SP client_id or user email
    subject_type  TEXT        NOT NULL,     -- 'sp' | 'user' | 'group'
    role          TEXT        NOT NULL,     -- 'admin' | 'viewer'
    granted_by    TEXT,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Tagging rules (replaces Delta tagging_rules table) ───────────────────────

CREATE TABLE IF NOT EXISTS tagging_rules (
    id            SERIAL      PRIMARY KEY,
    rule_name     TEXT        NOT NULL UNIQUE,
    conditions    JSONB       NOT NULL DEFAULT '[]',
    tags          JSONB       NOT NULL DEFAULT '{}',
    priority      INT         NOT NULL DEFAULT 0,
    enabled       BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Workspace metadata cache (avoids redundant SDK calls) ────────────────────

CREATE TABLE IF NOT EXISTS workspace_cache (
    workspace_id  TEXT        PRIMARY KEY,
    display_name  TEXT,
    cloud         TEXT,
    region        TEXT,
    cached_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

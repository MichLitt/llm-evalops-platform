-- 001_initial.sql — full schema for MVP
-- All tables use INTEGER surrogate PKs; child tables FK to runs(id) as run_pk.
-- ingested_reports is the worker lifecycle table; runs is the normalized read layer.

CREATE TABLE IF NOT EXISTS ingested_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    app_type      TEXT    NOT NULL,
    schema_version TEXT   NOT NULL,  -- canonical key: "{app_type}/{version}", e.g. "rag/v1"
    run_id        TEXT    NOT NULL,
    raw_payload   TEXT    NOT NULL,  -- original JSON, never modified
    status        TEXT    NOT NULL DEFAULT 'pending',  -- pending/processing/processed/failed/unsupported
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_at    REAL,              -- set when worker claims; used for lease timeout
    last_error    TEXT,
    processed_at  REAL,
    received_at   REAL    NOT NULL,
    UNIQUE (app_type, schema_version, run_id)
);

CREATE INDEX IF NOT EXISTS idx_ingested_reports_claimable
    ON ingested_reports (status, claimed_at);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    app_type              TEXT    NOT NULL,
    run_id                TEXT    NOT NULL,
    ingest_report_id      INTEGER REFERENCES ingested_reports (id),
    schema_version        TEXT    NOT NULL,
    task_set_id           TEXT,     -- NULL => cannot participate in compare
    dataset_version       TEXT,
    config_version        TEXT,
    model_version         TEXT,
    source_commit         TEXT,
    primary_artifact_path TEXT,
    status                TEXT    NOT NULL,
    wall_duration_ms      INTEGER, -- NULL for producers that cannot report wall time (e.g. rag/v1)
    created_at            REAL    NOT NULL,
    UNIQUE (app_type, run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_app_type_task_set
    ON runs (app_type, task_set_id);

CREATE INDEX IF NOT EXISTS idx_runs_status
    ON runs (status);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS run_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_pk       INTEGER NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    metric_name  TEXT    NOT NULL,
    metric_value REAL    NOT NULL,
    created_at   REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_metrics_run_pk
    ON run_metrics (run_pk);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_pk        INTEGER NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    artifact_type TEXT    NOT NULL,  -- e.g. "trajectory", "eval_report", "bad_cases"
    artifact_path TEXT    NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_run_pk
    ON artifacts (run_pk);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS compare_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    app_type         TEXT    NOT NULL,
    task_set_id      TEXT    NOT NULL,
    baseline_run_id  TEXT    NOT NULL,
    candidate_run_id TEXT    NOT NULL,
    result_json      TEXT,   -- per-metric {absolute_delta, percent_delta} map
    created_at       REAL    NOT NULL
);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS release_decisions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    compare_session_id INTEGER NOT NULL REFERENCES compare_sessions (id),
    rules_json         TEXT    NOT NULL,  -- snapshot of rules used
    decision           TEXT    NOT NULL,  -- "promoted" or "rejected"
    detail_json        TEXT    NOT NULL,  -- [{metric, op, threshold, actual, passed, reason?}]
    created_at         REAL    NOT NULL
);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bad_case_tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_pk     INTEGER NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    case_id    TEXT    NOT NULL,
    tag        TEXT    NOT NULL,
    note       TEXT,
    created_at REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bad_case_tags_run_pk
    ON bad_case_tags (run_pk);

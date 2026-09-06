-- Phase 10 reconciliation/review persistence (PostgreSQL)

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL,
    status text NOT NULL,
    results_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    exceptions_json jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS reconciliation_runs_created_at_idx
    ON reconciliation_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS review_decisions (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES reconciliation_runs(id),
    status text NOT NULL,
    actor text,
    reason text,
    created_at timestamptz NOT NULL,
    decided_at timestamptz
);

CREATE INDEX IF NOT EXISTS review_decisions_run_id_idx
    ON review_decisions (run_id);

CREATE INDEX IF NOT EXISTS review_decisions_status_idx
    ON review_decisions (status);

CREATE TABLE IF NOT EXISTS investigation_runs (
    id uuid PRIMARY KEY,
    reconciliation_run_id uuid NOT NULL REFERENCES reconciliation_runs(id),
    created_at timestamptz NOT NULL,
    output_json jsonb NOT NULL,
    telemetry_json jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS investigation_runs_reconciliation_run_id_idx
    ON investigation_runs (reconciliation_run_id, created_at DESC);

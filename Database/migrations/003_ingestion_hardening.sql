CREATE TABLE IF NOT EXISTS ingestion_documents (
    id uuid PRIMARY KEY,
    filename text NOT NULL,
    media_type text NOT NULL,
    sha256 text NOT NULL UNIQUE,
    uploaded_at timestamptz NOT NULL,
    source text NOT NULL,
    status text NOT NULL,
    progress integer NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    progress_message text NOT NULL DEFAULT '',
    record_type text NOT NULL,
    column_mapping_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    object_key text NOT NULL,
    records_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    preview_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    errors_json jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS ingestion_documents_status_idx
    ON ingestion_documents (status);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL UNIQUE REFERENCES ingestion_documents(id),
    status text NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL,
    locked_at timestamptz,
    last_error text
);

CREATE INDEX IF NOT EXISTS ingestion_jobs_claim_idx
    ON ingestion_jobs (status, available_at);

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS details_json jsonb NOT NULL DEFAULT '{}'::jsonb;

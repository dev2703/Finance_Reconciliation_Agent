CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY,
    filename text NOT NULL,
    media_type text NOT NULL,
    sha256 text NOT NULL,
    uploaded_at timestamptz NOT NULL,
    source text NOT NULL,
    page_count integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS financial_records (
    id uuid PRIMARY KEY,
    record_type text NOT NULL,
    external_id text,
    amount numeric(20, 4) NOT NULL,
    currency char(3) NOT NULL,
    record_date date NOT NULL,
    source_document_id uuid REFERENCES documents(id),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_events (
    id uuid PRIMARY KEY,
    event_type text NOT NULL,
    actor text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    reason text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE job_status AS ENUM (
    'queued',
    'running',
    'completed',
    'failed',
    'cancelled'
);

CREATE TABLE jobs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    status           job_status  NOT NULL DEFAULT 'queued',
    base_model       TEXT        NOT NULL,
    dataset_path     TEXT        NOT NULL,
    hyperparameters  JSONB       NOT NULL,
    checkpoint_path  TEXT,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_status ON jobs (status);
CREATE INDEX idx_jobs_created_at ON jobs (created_at DESC);

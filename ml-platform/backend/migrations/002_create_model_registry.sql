CREATE TABLE models (
    id               SERIAL      PRIMARY KEY,
    name             TEXT        NOT NULL,
    version          TEXT        NOT NULL,
    storage_path     TEXT        NOT NULL,
    path_type        TEXT        NOT NULL CHECK (path_type IN ('prefix', 'object')),
    size_bytes       BIGINT      NOT NULL,
    sha256_checksum  TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'archived')),
    is_default       BOOLEAN     NOT NULL DEFAULT false,
    source_url       TEXT,
    archived_at      TIMESTAMPTZ DEFAULT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (name, version)
);

CREATE UNIQUE INDEX models_one_default_per_name ON models (name) WHERE is_default = true;

CREATE INDEX idx_models_name ON models (name);
CREATE INDEX idx_models_status ON models (status);

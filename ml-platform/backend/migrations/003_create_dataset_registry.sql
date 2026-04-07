CREATE TABLE datasets (
    id                  SERIAL      PRIMARY KEY,
    name                TEXT        NOT NULL,
    version             TEXT        NOT NULL,
    storage_path        TEXT        NOT NULL,
    path_type           TEXT        NOT NULL CHECK (path_type IN ('prefix', 'object')),
    size_bytes          BIGINT      NOT NULL,
    sha256_checksum     TEXT        NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'archived')),
    source_description  TEXT,
    archived_at         TIMESTAMPTZ DEFAULT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (name, version)
);

CREATE INDEX idx_datasets_name ON datasets (name);
CREATE INDEX idx_datasets_status ON datasets (status);

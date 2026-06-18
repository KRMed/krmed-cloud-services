-- Base-model allow-list catalog.
--
-- Crucible does NOT store base-model weights. The worker downloads them from the
-- Hugging Face Hub on demand and caches them on the GPU box local HDD (a
-- read-through cache, reconstructible from HF). This table is only an allow-list
-- of which HF repos + revisions users may fine-tune, plus display metadata
-- derived from the Hub at registration time.

CREATE TABLE models (
    id            SERIAL      PRIMARY KEY,
    hf_repo_id    TEXT        NOT NULL,-- e.g. mistralai/Mistral-7B-Instruct-v0.2
    revision      TEXT        NOT NULL, -- HF commit SHA (pinned, immutable)
    display_name  TEXT        NOT NULL, -- human label for the UI
    param_count   BIGINT, -- total parameters, null when unknown
    vram_hint     TEXT        CHECK (vram_hint IN ('comfortable', 'tight', 'unsupported')),
    status        TEXT        NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'archived')),
    is_default    BOOLEAN     NOT NULL DEFAULT false,
    archived_at   TIMESTAMPTZ DEFAULT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (hf_repo_id, revision)
);

-- At most one default revision per HF repo.
CREATE UNIQUE INDEX models_one_default_per_repo ON models (hf_repo_id) WHERE is_default = true;

CREATE INDEX idx_models_hf_repo_id ON models (hf_repo_id);
CREATE INDEX idx_models_status ON models (status);

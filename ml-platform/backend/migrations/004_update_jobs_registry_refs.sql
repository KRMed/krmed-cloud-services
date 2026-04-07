ALTER TABLE jobs
    ADD COLUMN model_id   INTEGER REFERENCES models(id)   ON DELETE RESTRICT,
    ADD COLUMN dataset_id INTEGER REFERENCES datasets(id) ON DELETE RESTRICT;

-- base_model and dataset_path are intentionally retained until the application
-- layer is updated to use model_id and dataset_id.

CREATE INDEX idx_jobs_model_id   ON jobs (model_id);
CREATE INDEX idx_jobs_dataset_id ON jobs (dataset_id);

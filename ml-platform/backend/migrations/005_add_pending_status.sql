-- Extend the status CHECK constraints on both registry tables to allow a
-- transient 'pending' state used by ingestion scripts while an upload is in
-- progress. Rows in 'pending' have a reserved DB entry but no complete object
-- prefix in Garage yet; a failed ingestion leaves a 'pending' row that the
-- next retry will clean up before re-attempting.

ALTER TABLE models DROP CONSTRAINT IF EXISTS models_status_check;
ALTER TABLE models ADD CONSTRAINT models_status_check
    CHECK (status IN ('pending', 'ready', 'archived'));

ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_status_check;
ALTER TABLE datasets ADD CONSTRAINT datasets_status_check
    CHECK (status IN ('pending', 'ready', 'archived'));

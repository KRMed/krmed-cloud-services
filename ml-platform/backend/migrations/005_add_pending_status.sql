ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_status_check;
ALTER TABLE datasets ADD CONSTRAINT datasets_status_check
    CHECK (status IN ('pending', 'ready', 'archived'));

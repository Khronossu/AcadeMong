-- Migration 001: rename user_test_scores.test_code → subject
--
-- The develop branch originally created user_test_scores with column
-- name test_code (VARCHAR 30). The DATA_CONTRACT §7.1 and schema.sql
-- both specify the column as subject (VARCHAR 50). This migration
-- aligns the live database with the schema.
--
-- Run once on any database created before phase-5/data-contract merged.
-- Safe to run again — the COLUMN RENAME will error if subject already
-- exists; wrap in a DO block to make it idempotent.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_test_scores'
          AND column_name = 'test_code'
    ) THEN
        ALTER TABLE user_test_scores RENAME COLUMN test_code TO subject;
        ALTER TABLE user_test_scores ALTER COLUMN subject TYPE VARCHAR(50);
        RAISE NOTICE 'Migration 001 applied: test_code renamed to subject';
    ELSE
        RAISE NOTICE 'Migration 001 skipped: column subject already exists';
    END IF;
END
$$;

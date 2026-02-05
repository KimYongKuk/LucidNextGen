-- Add metadata JSON column to chat_log_new table for storing images, sources, etc.
-- Migration: add_metadata_column.sql
-- Date: 2025-12-31

ALTER TABLE chat_log_new
ADD COLUMN metadata JSON DEFAULT NULL
COMMENT 'Images, sources, and other metadata (excludes CoT messages)';

-- Index for querying by session (if needed)
-- CREATE INDEX idx_session_metadata ON chat_log_new(session);

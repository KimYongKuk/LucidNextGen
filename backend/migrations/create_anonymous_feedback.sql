-- Create anonymous_feedback table for anonymous feedback channel
-- Migration: create_anonymous_feedback.sql
-- Date: 2026-02-05

CREATE TABLE IF NOT EXISTS anonymous_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feedback_id VARCHAR(36) NOT NULL UNIQUE COMMENT 'UUID for client-side identification',
    message TEXT NOT NULL COMMENT 'Feedback message content',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created_at (created_at DESC),
    INDEX idx_feedback_id (feedback_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

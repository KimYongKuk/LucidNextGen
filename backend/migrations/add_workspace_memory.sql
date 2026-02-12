-- ============================================================
-- Workspace Memory Table
-- 워크스페이스별 대화 메모리 (롤링 요약 + 핵심 사실)
-- ============================================================

CREATE TABLE IF NOT EXISTS workspace_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- 식별자
    workspace_id INT NOT NULL,
    user_id VARCHAR(50) NOT NULL,

    -- 메모리 데이터
    summary TEXT,                              -- 롤링 요약 (최대 500자)
    key_facts JSON,                            -- 핵심 사실 배열 (최대 10개)

    -- 메타데이터
    total_message_count INT DEFAULT 0,         -- 워크스페이스 총 메시지 수
    last_summary_message_count INT DEFAULT 0,  -- 마지막 요약 시점 메시지 수
    last_summarized_at DATETIME,

    -- 타임스탬프
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 제약조건
    UNIQUE KEY idx_workspace_user (workspace_id, user_id),
    INDEX idx_workspace_id (workspace_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Note: Foreign key는 workspaces 테이블 구조에 따라 선택적으로 추가
-- ALTER TABLE workspace_memory
--     ADD CONSTRAINT fk_workspace_memory_workspace
--     FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;

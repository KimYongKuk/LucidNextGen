-- ============================================================
-- Global User Memory Table
-- 사용자별 전역 메모리 (핵심 사실만, 롤링 요약 없음)
-- 모든 세션에서 공유되는 사용자 개인 특성 기억
-- ============================================================

CREATE TABLE IF NOT EXISTS user_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- 식별자 (사용자당 1행)
    user_id VARCHAR(50) NOT NULL,

    -- 메모리 데이터 (key_facts ONLY, no rolling summary)
    key_facts JSON,                              -- {"facts": [{content, extracted_at}, ...]}

    -- 카운팅 메타데이터 (전체 세션 기준)
    total_message_count INT DEFAULT 0,           -- 사용자의 전체 메시지 수
    last_extraction_message_count INT DEFAULT 0, -- 마지막 추출 시점 메시지 수

    -- 타임스탬프
    last_extracted_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 제약조건
    UNIQUE KEY idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

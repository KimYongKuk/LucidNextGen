-- 토큰 사용량 로깅 테이블
-- 모든 LLM 호출(Sonnet/Haiku)을 개별 row로 기록하여 모델별/워커별/사용자별 모니터링 지원
CREATE TABLE IF NOT EXISTS token_usage_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) DEFAULT NULL,
    user_id VARCHAR(50) DEFAULT NULL,
    caller VARCHAR(50) NOT NULL COMMENT 'intent_classifier, DirectWorker, CorpRAGWorker, memory_ws_summary, memory_ws_facts, memory_user_facts, title_generation 등',
    model_id VARCHAR(100) NOT NULL COMMENT '전체 Bedrock 모델 ID',
    model_type VARCHAR(10) NOT NULL COMMENT 'sonnet 또는 haiku',
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cache_read_tokens INT DEFAULT 0,
    cache_write_tokens INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_token_created (created_at),
    INDEX idx_token_model (model_type, created_at),
    INDEX idx_token_caller (caller, created_at),
    INDEX idx_token_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

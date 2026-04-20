-- ============================================================
-- Security Guard Agent 테이블 (2026-04-20)
-- 보안 위협 탐지 이벤트 로그 + 사용자 차단 상태 관리
-- ============================================================

-- 1. 보안 이벤트 로그 (모든 탐지 이벤트)
CREATE TABLE IF NOT EXISTS user_security_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    session_id VARCHAR(100),
    workspace_id VARCHAR(36) NULL,
    threat_type ENUM(
        'INJECTION','JAILBREAK','DATA_EXFIL',
        'PRIVILEGE_ESCALATION','ABUSE','MALICIOUS_CONTENT','OTHER'
    ) NOT NULL,
    severity TINYINT UNSIGNED NOT NULL COMMENT '0-100 severity score',
    action_taken ENUM(
        'LOGGED','WARNED','BLOCKED_REQUEST','TEMP_BLOCKED','PERM_BLOCKED'
    ) NOT NULL,
    detection_layer ENUM('RULE','RATE','LLM','COMBINED') NOT NULL,
    user_message TEXT COMMENT 'User message snippet (truncated/masked)',
    reason TEXT COMMENT 'Detection reason',
    matched_patterns JSON COMMENT 'Matched rule patterns',
    llm_raw_response TEXT COMMENT 'LLM classifier raw output (debug)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_severity_created (severity, created_at),
    INDEX idx_threat_type (threat_type, created_at),
    INDEX idx_action_taken (action_taken, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='보안 위협 탐지 이벤트 로그';

-- 2. 사용자 차단 상태 (현재 차단 중인 사용자)
CREATE TABLE IF NOT EXISTS user_blocks (
    user_id VARCHAR(50) PRIMARY KEY,
    block_type ENUM('TEMPORARY','PERMANENT') NOT NULL,
    reason TEXT NOT NULL,
    threat_type VARCHAR(50) COMMENT 'Triggering threat type',
    blocked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL COMMENT 'NULL = permanent',
    unblocked_at DATETIME NULL,
    unblocked_by VARCHAR(50) NULL,
    unblock_reason TEXT NULL,
    triggering_event_id BIGINT NULL COMMENT 'Causing event ID',
    warn_count_at_block INT DEFAULT 0,
    temp_block_count INT DEFAULT 0 COMMENT 'Total TEMP_BLOCK history count',
    FOREIGN KEY (triggering_event_id) REFERENCES user_security_events(id) ON DELETE SET NULL,
    INDEX idx_expires (expires_at),
    INDEX idx_block_type (block_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='사용자 차단 상태';

-- 3. LLM 일일 호출 카운터 (비용 폭탄 방지)
CREATE TABLE IF NOT EXISTS security_llm_daily_usage (
    usage_date DATE PRIMARY KEY,
    call_count INT NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='보안 검사 LLM 일일 호출 수 (한도 제어)';

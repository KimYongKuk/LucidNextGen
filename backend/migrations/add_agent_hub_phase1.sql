-- ============================================================
-- Agent Hub Phase 1 — 신규 8개 테이블 (2026-04-30)
-- 설계: docs/agent-hub/02_data_model.md
--
-- 테이블:
--   1. agents              — 에이전트 카탈로그
--   2. user_agents         — 사용자별 설치/활성화
--   3. workspace_agents    — 워크스페이스 부착
--   4. agent_review_reports— AI 자동 검증 리포트
--   5. agent_approvals     — 인간 승인 결정
--   6. agent_executions    — 실행 이력
--   7. user_notifications  — 알림함
--   8. runners             — Runner EC2 등록
--
-- 외래키 정책: 모두 ON DELETE RESTRICT (soft delete만 허용)
-- ============================================================


-- ============================================================
-- 1. agents — 에이전트 카탈로그
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    slug VARCHAR(100) NOT NULL COMMENT 'URL-friendly identifier',

    -- 메타
    name VARCHAR(200) NOT NULL,
    description TEXT,
    icon VARCHAR(20) COMMENT 'Emoji or icon identifier',
    tags JSON COMMENT 'Array of tag strings',

    -- 작성자
    author_user_id VARCHAR(50) NOT NULL,
    author_team VARCHAR(100),

    -- 분류 (정규화된 컬럼 — 자주 쿼리/필터)
    platform ENUM('native', 'miso', 'runner', 'webhook') NOT NULL,
    capabilities JSON NOT NULL COMMENT 'Array: chat/run/scheduled/async (multiple)',
    visibility ENUM('private', 'team', 'public') NOT NULL DEFAULT 'private',
    status ENUM('draft', 'pending_review', 'pending_approval', 'rejected',
                'active', 'maintenance', 'disabled', 'deleted') NOT NULL DEFAULT 'draft',

    -- 매니페스트 (디테일은 JSON)
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    manifest JSON NOT NULL COMMENT 'inputs/output/runtime/triggers/intent_hints/requires',

    -- 카운터
    install_count INT NOT NULL DEFAULT 0 COMMENT 'Denormalized — updated by application',

    -- Native seed 식별
    is_native_seed TINYINT(1) NOT NULL DEFAULT 0,

    -- Runner 매핑 (runner 플랫폼인 경우)
    runner_id VARCHAR(36) NULL COMMENT 'FK runners.id (runner platform only)',

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_slug (slug),
    INDEX idx_platform_status (platform, status),
    INDEX idx_visibility_status (visibility, status),
    INDEX idx_author (author_user_id),
    INDEX idx_native_seed (is_native_seed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='에이전트 카탈로그';


-- ============================================================
-- 2. user_agents — 사용자별 설치/활성화
-- ============================================================
CREATE TABLE IF NOT EXISTS user_agents (
    user_id VARCHAR(50) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Soft toggle (uninstall vs disable)',
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME NULL COMMENT 'Updated by application on execution',

    PRIMARY KEY (user_id, agent_id),
    INDEX idx_user_enabled (user_id, enabled),
    INDEX idx_last_used (last_used_at),
    CONSTRAINT fk_ua_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='사용자별 설치한 에이전트 (Active Agents 리스트 소스)';


-- ============================================================
-- 3. workspace_agents — 워크스페이스 부착
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace_agents (
    workspace_id VARCHAR(36) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    attached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    attached_by_user_id VARCHAR(50) NOT NULL,

    PRIMARY KEY (workspace_id, agent_id),
    INDEX idx_workspace (workspace_id),
    INDEX idx_agent (agent_id),
    CONSTRAINT fk_wa_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='워크스페이스에 붙은 에이전트 매핑';


-- ============================================================
-- 4. agent_review_reports — AI 자동 검증 리포트
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_review_reports (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    agent_id VARCHAR(36) NOT NULL,
    agent_version VARCHAR(20) NOT NULL,
    review_round INT NOT NULL DEFAULT 1 COMMENT 'Re-validation round number',

    category ENUM('quality', 'security') NOT NULL,
    reviewer_kind ENUM('auto') NOT NULL DEFAULT 'auto'
        COMMENT 'Phase 1: auto only (humans are in agent_approvals)',
    reviewer_id VARCHAR(100) NOT NULL COMMENT 'e.g., validator-v1',

    score TINYINT UNSIGNED NULL COMMENT '0-100 score (NULL if not scored)',
    severity_max ENUM('info', 'warn', 'error', 'critical') NOT NULL,
    findings JSON NOT NULL COMMENT 'Array of {severity, category, message, location, suggestion}',
    status ENUM('passed', 'warnings', 'failed') NOT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,

    INDEX idx_agent_version (agent_id, agent_version),
    INDEX idx_status_created (status, created_at),
    CONSTRAINT fk_arr_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 자동 검증 리포트 (퀄리티/보안)';


-- ============================================================
-- 5. agent_approvals — 인간 승인 결정
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_approvals (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    agent_id VARCHAR(36) NOT NULL,
    agent_version VARCHAR(20) NOT NULL,
    report_ids JSON COMMENT 'Array of agent_review_reports.id seen by approver',

    approver_user_id VARCHAR(50) NOT NULL COMMENT 'operator role only (Phase 1)',
    decision ENUM('approved', 'rejected', 'request_changes') NOT NULL,
    comment TEXT,
    decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_agent_decided (agent_id, decided_at),
    INDEX idx_approver (approver_user_id),
    INDEX idx_decision (decision, decided_at),
    CONSTRAINT fk_aa_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='인간 승인 결정 (operator role)';


-- ============================================================
-- 6. agent_executions — 실행 이력
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_executions (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    agent_id VARCHAR(36) NOT NULL,
    agent_version VARCHAR(20) NOT NULL,

    user_id VARCHAR(50) NOT NULL,
    workspace_id VARCHAR(36) NULL,
    session_id VARCHAR(100) NULL COMMENT 'chat_sessions reference',

    runner_id VARCHAR(36) NULL COMMENT 'For runner platform agents',

    input_args JSON COMMENT 'PII-masked input parameters',
    output_summary TEXT COMMENT 'Truncated output (large outputs go to S3/file_archive)',
    output_files JSON COMMENT 'Array of S3 keys / file paths',

    status ENUM('pending', 'running', 'success', 'failed', 'timeout', 'cancelled') NOT NULL,
    error_message TEXT,

    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    execution_time_ms INT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_agent_created (agent_id, created_at),
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_status (status, created_at),
    INDEX idx_workspace (workspace_id, created_at),
    INDEX idx_runner_status (runner_id, status),
    CONSTRAINT fk_ae_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='에이전트 실행 이력 (감사·디버깅·통계)';


-- ============================================================
-- 7. user_notifications — 알림함
-- ============================================================
CREATE TABLE IF NOT EXISTS user_notifications (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    user_id VARCHAR(50) NOT NULL,

    type ENUM('schedule_done', 'async_done', 'sync_done', 'mail',
              'approval', 'announcement', 'system') NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT,

    agent_id VARCHAR(36) NULL,
    execution_id VARCHAR(36) NULL,
    link_url VARCHAR(500) NULL COMMENT 'URL to navigate on click',

    read_at DATETIME NULL COMMENT 'NULL = unread',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_user_created (user_id, created_at),
    INDEX idx_user_unread (user_id, read_at),
    INDEX idx_created (created_at) COMMENT 'For 90-day cleanup batch',
    CONSTRAINT fk_un_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='알림함 (90일 hard delete by batch)';


-- ============================================================
-- 8. runners — Runner EC2 등록
-- ============================================================
CREATE TABLE IF NOT EXISTS runners (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    name VARCHAR(200) NOT NULL COMMENT 'Display name e.g., CPO본부 Runner',
    ec2_instance_id VARCHAR(50) NULL COMMENT 'AWS EC2 instance ID',

    labels JSON NOT NULL COMMENT 'Capability labels e.g., ["cpo","sap-fi","office"]',
    responsible_dept_groups JSON COMMENT 'Manual mapping: ["CPO", "재경본부", ...]',

    status ENUM('online', 'offline', 'busy', 'maintenance') NOT NULL DEFAULT 'offline',
    last_heartbeat DATETIME NULL,

    auth_token_hash VARCHAR(255) NOT NULL COMMENT 'SHA-256 hash of runner auth token',

    efs_mount_path VARCHAR(500) NULL COMMENT 'Phase 2: EFS path for shared macro files',

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_status (status),
    INDEX idx_last_heartbeat (last_heartbeat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Runner EC2 등록 (4대 본부별, 기존 RPA 자산 흡수)';


-- ============================================================
-- agents → runners 외래키 (run platform 매핑, 두 테이블 모두 생성 후 추가)
-- ============================================================
ALTER TABLE agents
    ADD CONSTRAINT fk_agents_runner
    FOREIGN KEY (runner_id) REFERENCES runners(id) ON DELETE RESTRICT;

-- Eval (Golden Case Regression Testing) 테이블 추가
-- 적용: mysql -h <host> -u operator -p<pw> lucid < add_eval_tables.sql
--
-- 설계:
-- - 케이스 정의의 source of truth는 backend/tests/eval/cases/*.yaml (git)
-- - DB는 실행 결과/triage 메타만 저장
-- - 실행은 cron(매일 새벽) 또는 수동 (관리자 UI에서 트리거 — Phase 4)

-- ── 실행 단위 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE COMMENT 'UUID',
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    total_count INT NOT NULL DEFAULT 0,
    pass_count INT NOT NULL DEFAULT 0,
    fail_count INT NOT NULL DEFAULT 0,
    error_count INT NOT NULL DEFAULT 0,
    skip_count INT NOT NULL DEFAULT 0,
    triggered_by VARCHAR(50) NOT NULL COMMENT 'cron | manual:<empno>',
    status ENUM('running', 'finished', 'aborted') NOT NULL DEFAULT 'running',
    notes TEXT NULL,
    INDEX idx_started (started_at),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 케이스별 결과 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL COMMENT 'eval_runs.run_id',
    case_id VARCHAR(100) NOT NULL COMMENT 'yaml의 id (예: direct_basic_greeting)',
    worker VARCHAR(50) NULL COMMENT '케이스가 속한 워커 (yaml 파일명에서 유도)',
    status ENUM('pass', 'fail', 'error', 'skip') NOT NULL,
    assertions_failed JSON NULL COMMENT '실패한 assertion 키 배열',
    input_text TEXT NOT NULL,
    response_text MEDIUMTEXT NULL,
    intent_actual VARCHAR(50) NULL,
    worker_actual VARCHAR(50) NULL,
    tools_called JSON NULL COMMENT '호출된 도구 이름 배열',
    duration_ms INT NULL,
    error_text TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run (run_id),
    INDEX idx_case (case_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Triage (Phase 2에서 활성, 스키마는 미리 마련) ──────────────
CREATE TABLE IF NOT EXISTS eval_triages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    result_id INT NOT NULL COMMENT 'eval_results.id',
    category ENUM('real_regression', 'stale_test', 'flaky', 'fixed') NOT NULL,
    note TEXT NULL,
    triaged_by VARCHAR(50) NOT NULL,
    triaged_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_result (result_id),
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Cron 자동 호출용 chat_sessions 메타데이터 (Phase 3b, 2026-05-06)
--
-- 목적: 스케줄러가 자동 호출한 워크플로우 결과를 별도 채팅 세션으로
--       격리하고 사이드바/알림에서 구분 가능하게 함.
--
-- 안전: 기존 세션은 auto_generated=0, source_agent_id=NULL 로 자연 처리.
-- ============================================================

ALTER TABLE chat_sessions
    ADD COLUMN auto_generated TINYINT(1) NOT NULL DEFAULT 0
        COMMENT 'Cron/스케줄러 자동 생성 세션 여부',
    ADD COLUMN source_agent_id VARCHAR(36) NULL
        COMMENT 'Auto-generated 세션을 만든 agent (FK agents.id, soft)',
    ADD INDEX idx_auto_user (auto_generated, user_id),
    ADD INDEX idx_source_agent (source_agent_id);

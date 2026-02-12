-- ============================================================
-- Migration: Change workspace_id columns from INT to VARCHAR(36) (UUID)
-- Run this AFTER backing up your database
-- ============================================================

-- 0. 외래 키 제약조건 삭제 (있는 경우)
ALTER TABLE chat_sessions
DROP FOREIGN KEY fk_chat_sessions_workspace;

-- 1. chat_sessions 테이블의 workspace_id를 VARCHAR(36)으로 변경
ALTER TABLE chat_sessions
MODIFY COLUMN workspace_id VARCHAR(36) NULL;

-- 2. workspace_memory 테이블의 workspace_id를 VARCHAR(36)으로 변경
ALTER TABLE workspace_memory
MODIFY COLUMN workspace_id VARCHAR(36) NOT NULL;

-- 3. 기존 INT 값이 있으면 UUID로 업데이트 (workspaces.uuid 참조)
-- chat_sessions
UPDATE chat_sessions cs
JOIN workspaces w ON cs.workspace_id = CAST(w.id AS CHAR)
SET cs.workspace_id = w.uuid
WHERE cs.workspace_id IS NOT NULL
  AND cs.workspace_id REGEXP '^[0-9]+$';

-- workspace_memory
UPDATE workspace_memory wm
JOIN workspaces w ON wm.workspace_id = CAST(w.id AS CHAR)
SET wm.workspace_id = w.uuid
WHERE wm.workspace_id REGEXP '^[0-9]+$';

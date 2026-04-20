-- 공용 워크스페이스 플래그 추가
-- is_public = 1 인 워크스페이스는 모든 사용자에게 읽기 전용으로 노출됨
-- 쓰기 권한(파일 업로드/수정/삭제, 시스템 프롬프트 변경)은 여전히 소유자(A2304013)만 가능

ALTER TABLE workspaces
    ADD COLUMN is_public TINYINT(1) NOT NULL DEFAULT 0 AFTER instructions;

CREATE INDEX idx_workspaces_is_public ON workspaces(is_public);

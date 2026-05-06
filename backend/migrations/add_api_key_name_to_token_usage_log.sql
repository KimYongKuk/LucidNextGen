-- OpenAI-compatible API 토큰 추적용 컬럼 추가
-- 실행: MySQL CLI에서 수동 실행

ALTER TABLE token_usage_log
  ADD COLUMN api_key_name VARCHAR(50) DEFAULT NULL COMMENT 'OpenAPI 서비스 API Key 이름 (svc-common 등)' AFTER user_id,
  ADD INDEX idx_token_apikey (api_key_name, created_at);

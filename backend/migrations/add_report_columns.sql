-- 서비스 리포트 대시보드를 위한 chat_log_new 테이블 컬럼 추가
-- 실행: MySQL 클라이언트에서 수동 실행

ALTER TABLE chat_log_new
  ADD COLUMN intent VARCHAR(20) DEFAULT NULL,
  ADD COLUMN worker_name VARCHAR(30) DEFAULT NULL,
  ADD COLUMN response_time_ms INT DEFAULT NULL;

-- 리포트 쿼리 성능을 위한 인덱스
CREATE INDEX idx_chatlog_createdate ON chat_log_new(createDate);
CREATE INDEX idx_chatlog_intent ON chat_log_new(intent);

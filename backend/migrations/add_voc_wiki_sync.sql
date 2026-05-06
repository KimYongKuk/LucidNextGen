-- VOC Wiki 동기화 로그 테이블
-- IT VOC → L&F Wiki 자동 축적 배치의 실행 이력을 관리합니다.

CREATE TABLE IF NOT EXISTS voc_wiki_sync_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sync_date DATE NOT NULL COMMENT '동기화 대상 날짜',
    voc_count INT DEFAULT 0 COMMENT '처리된 VOC 건수',
    docs_created INT DEFAULT 0 COMMENT '생성된 문서 수',
    docs_updated INT DEFAULT 0 COMMENT '업데이트된 문서 수',
    status ENUM('success', 'partial', 'failed') DEFAULT 'success' COMMENT '실행 결과',
    error_message TEXT COMMENT '에러 메시지 (실패 시)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '실행 시각'
);

-- Weekly Report Email 기능 - 테이블 3개
-- 실행: MySQL에서 수동 실행

-- 1. 이메일 발송 설정 (싱글턴 레코드)
CREATE TABLE IF NOT EXISTS report_email_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    send_day VARCHAR(10) DEFAULT 'mon' COMMENT 'mon/tue/wed/thu/fri/sat/sun',
    send_hour INT DEFAULT 9 COMMENT '0-23',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 수신자 목록
CREATE TABLE IF NOT EXISTS report_email_recipients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100),
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 발송 이력
CREATE TABLE IF NOT EXISTS report_email_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    recipient_count INT DEFAULT 0,
    recipients_json JSON COMMENT '발송 시점 수신자 스냅샷',
    pdf_filename VARCHAR(255),
    status ENUM('success', 'partial', 'failed') DEFAULT 'success',
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 초기 설정 (disabled 상태로 시작)
INSERT INTO report_email_config (enabled, send_day, send_hour)
VALUES (FALSE, 'mon', 9);

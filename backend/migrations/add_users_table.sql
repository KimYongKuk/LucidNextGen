-- 자체 인증용 사용자 테이블
-- 실행: MySQL chatbot DB에서 실행

CREATE TABLE IF NOT EXISTS users (
    empno VARCHAR(20) PRIMARY KEY COMMENT '사번 (PK)',
    login_id VARCHAR(50) NOT NULL COMMENT '로그인 ID',
    name VARCHAR(50) NOT NULL COMMENT '사용자 이름',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 해시',
    is_active TINYINT(1) DEFAULT 1 COMMENT '활성 상태 (0=비활성)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_login_id (login_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='자체 인증 사용자';

-- 비밀번호 설정 초대 토큰
CREATE TABLE IF NOT EXISTS setup_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    token VARCHAR(64) NOT NULL COMMENT '1회용 토큰 (UUID)',
    empno VARCHAR(20) NOT NULL COMMENT '사번',
    login_id VARCHAR(50) NOT NULL COMMENT '로그인 ID',
    name VARCHAR(50) NOT NULL COMMENT '사용자 이름',
    email VARCHAR(100) NOT NULL COMMENT '이메일',
    used TINYINT(1) DEFAULT 0 COMMENT '사용 여부',
    expires_at DATETIME NOT NULL COMMENT '만료 시각',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_token (token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='비밀번호 설정 초대 토큰';
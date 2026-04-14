-- 서비스 메뉴 테이블 생성
-- 그룹웨어 플로팅 위젯에서 SSO 연동 서비스 바로가기를 제공하기 위한 테이블

CREATE TABLE IF NOT EXISTS service_menu (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '메뉴명',
    icon VARCHAR(50) DEFAULT NULL COMMENT '아이콘 키 (SVG 이름)',
    target_url VARCHAR(500) NOT NULL COMMENT 'SSO 경유 후 이동할 최종 URL',
    orgs JSON NOT NULL COMMENT '노출 대상 조직 배열 (예: ["엘앤에프","엘앤에프플러스"])',
    sort_order INT DEFAULT 0 COMMENT '정렬 순서',
    enabled TINYINT DEFAULT 1 COMMENT '활성 여부',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='그룹웨어 서비스 메뉴';

-- 초기 데이터
INSERT INTO service_menu (name, icon, target_url, orgs, sort_order) VALUES
('e-HR',       'users',    'https://lfon.landf.co.kr/slo/hrslo.jsp',    '["엘앤에프"]', 1),
('e-HR(LFP)',  'users',    'https://lfon.landf.co.kr/slo/lfphrslo.jsp', '["엘앤에프플러스"]', 2),
('EHS',        'shield',   'https://lfon.landf.co.kr/slo/ehs.jsp',      '["엘앤에프"]', 3),
('wa',         'briefcase','https://lfon.landf.co.kr/slo/waslo.jsp',     '["엘앤에프"]', 4),
('Lucid',      'bot',      'https://lfon.landf.co.kr/slo/lucid.jsp',     '["엘앤에프","엘앤에프플러스"]', 5),
('Pilot',      'rocket',   'https://lfon.landf.co.kr/slo/pilot.jsp',     '["엘앤에프","엘앤에프플러스"]', 6),
('Hub',        'layout',   'https://lfon.landf.co.kr/slo/hubslo.jsp',    '["엘앤에프"]', 7);

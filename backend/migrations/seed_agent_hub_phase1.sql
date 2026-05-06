-- ============================================================
-- Agent Hub Phase 1 — 초기 Seed 데이터 (2026-04-30)
--
-- 1. Runner 4대 (본부별 매핑)
-- 2. Native Agent 18개 카탈로그 (기존 Worker 흡수)
--
-- 실행 순서: add_agent_hub_phase1.sql 실행 후 이 파일 실행
-- 재실행 안전: ON DUPLICATE KEY UPDATE 패턴 사용
-- ============================================================


-- ============================================================
-- 1. Runner 4대 초기 등록 (본부별)
-- ============================================================
-- 주의: ec2_instance_id, auth_token_hash는 실제 배포 시점에 갱신 필요

INSERT INTO runners (id, name, ec2_instance_id, labels, responsible_dept_groups,
                      status, auth_token_hash)
VALUES
    (UUID(), 'CPO본부 Runner',
     'i-PLACEHOLDER-cpo',
     JSON_ARRAY('cpo', 'sap', 'office', 'mes', 'production'),
     JSON_ARRAY('CPO', '생산기술원', '소재개발연구소', '원료개발연구소', 'IBS부문'),
     'offline',
     'PLACEHOLDER_HASH_CPO'),

    (UUID(), '영업/마케팅 Runner',
     'i-PLACEHOLDER-sales',
     JSON_ARRAY('sales', 'office', 'crm'),
     JSON_ARRAY('영업본부', '마케팅'),
     'offline',
     'PLACEHOLDER_HASH_SALES'),

    (UUID(), 'CFO본부 Runner',
     'i-PLACEHOLDER-cfo',
     JSON_ARRAY('cfo', 'sap-fi', 'office'),
     JSON_ARRAY('CFO', '재경본부'),
     'offline',
     'PLACEHOLDER_HASH_CFO'),

    (UUID(), '공통/감사 Runner',
     'i-PLACEHOLDER-shared',
     JSON_ARRAY('shared', 'office'),
     JSON_ARRAY('감사실', '직속'),
     'offline',
     'PLACEHOLDER_HASH_SHARED');


-- ============================================================
-- 2. Native Agent 18개 카탈로그 seed
-- ============================================================
-- 각 Native Worker를 Hub Agent로 등록.
-- is_native_seed=TRUE 마크.
-- status='active' (검증/승인 거치지 않음 — 코드 배포된 것이므로 신뢰)

INSERT INTO agents (id, slug, name, description, icon, tags,
                     author_user_id, author_team,
                     platform, capabilities, visibility, status,
                     version, manifest, is_native_seed)
VALUES
    -- 1. DirectWorker — 일반 대화
    (UUID(), 'native-direct', '일반 대화',
     '루시드AI 기본 대화 어시스턴트 (Sonnet)',
     '💬', JSON_ARRAY('대화', '기본'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'DirectWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '일반 대화 및 자유 질문 응답. 다른 Agent로 분류되지 않은 모든 발화를 처리.'
        )
     ),
     1),

    -- 2. WebSearchWorker
    (UUID(), 'native-web-search', '웹 검색',
     'Tavily 기반 실시간 웹 검색',
     '🌐', JSON_ARRAY('웹', '검색', 'tavily'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'WebSearchWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '실시간 웹 정보가 필요한 질문(뉴스, 최신 동향, 외부 정보)에 사용.'
        )
     ),
     1),

    -- 3. UserFilesWorker
    (UUID(), 'native-user-files', '내 파일 검색',
     '사용자 업로드 파일 + 워크스페이스 문서 RAG',
     '📁', JSON_ARRAY('파일', 'RAG', '문서'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'UserFilesWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '사용자가 업로드한 파일이나 워크스페이스 문서 내용을 묻는 질문에 사용.'
        )
     ),
     1),

    -- 4. CorpRAGWorker
    (UUID(), 'native-corp-rag', '사내 문서 검색 (HR/안전)',
     '인사/안전환경팀 규정 문서 검색 + 조직도 조회',
     '📚', JSON_ARRAY('사내', 'HR', '안전', '조직도'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'CorpRAGWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '인사/안전환경 규정, 사내 조직도/담당자 조회 질문에 사용.'
        )
     ),
     1),

    -- 5. VisualizationWorker
    (UUID(), 'native-visualization', '시각화 (PDF/차트)',
     'PDF·차트·DOCX 산출물 생성',
     '📊', JSON_ARRAY('PDF', '차트', '시각화'),
     'system', 'lucid',
     'native', JSON_ARRAY('run'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'VisualizationWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'file'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'PDF, 차트, DOCX 등 시각/문서 산출물 생성 요청에 사용.'
        )
     ),
     1),

    -- 6. YouTubeWorker
    (UUID(), 'native-youtube', 'YouTube 요약',
     'YouTube 비디오 URL 요약 (타임스탬프, 인사이트)',
     '🎬', JSON_ARRAY('YouTube', '요약', '비디오'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'YouTubeWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'YouTube URL이 포함된 발화에 사용. 비디오 요약 생성.'
        )
     ),
     1),

    -- 7. URLFetchWorker
    (UUID(), 'native-url-fetch', 'URL 콘텐츠 추출',
     '웹 페이지 URL → 마크다운 콘텐츠 추출 + 요약',
     '🔗', JSON_ARRAY('URL', '페치', '뉴스', '블로그'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'URLFetchWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'URL이 포함된 발화에서 해당 페이지 내용 추출/요약 요청 시 사용.'
        )
     ),
     1),

    -- 8. ITSupportWorker
    (UUID(), 'native-it-support', 'IT 지원 (VOC + 규정)',
     'IT 지원 사례 + IT 규정 + WORKS VOC 등록 + SAP 패스워드 초기화',
     '🖥️', JSON_ARRAY('IT', 'VOC', 'WORKS'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'ITSupportWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'IT 관련 문제, 보안 정책, IT VOC 사례, SAP 비밀번호 초기화 요청에 사용.'
        )
     ),
     1),

    -- 9. AcctSupportWorker
    (UUID(), 'native-acct-support', '회계 지원 (VOC + 규정)',
     '회계/재경 지원 사례 + 회계 규정 + 조직도',
     '💰', JSON_ARRAY('회계', 'VOC', '재경'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'AcctSupportWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '회계/재경 처리 방법, 회계 VOC 사례, 회계 규정 질문에 사용.'
        )
     ),
     1),

    -- 10. MailWorker
    (UUID(), 'native-mail', '메일 조회',
     '받은편지함/보낸편지함/검색/요약/답장 초안',
     '📧', JSON_ARRAY('메일', '메일함'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'MailWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '받은/보낸 메일 조회, 검색, 요약, 답장 초안 요청에 사용.'
        )
     ),
     1),

    -- 11. ApprovalWorker
    (UUID(), 'native-approval', '결재 조회',
     '기안함/결재대기/결재완료/참조함 조회',
     '📋', JSON_ARRAY('결재', '기안', '상신'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'ApprovalWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '결재 문서 조회 (기안/대기/완료/참조)에 사용. "결산"이 아닌 "결재" 키워드.'
        )
     ),
     1),

    -- 12. PPTWorker
    (UUID(), 'native-ppt', 'PPT 생성',
     '사내 템플릿 기반 PPT 생성 (표지/목차/내용/차트)',
     '📑', JSON_ARRAY('PPT', '프레젠테이션'),
     'system', 'lucid',
     'native', JSON_ARRAY('run'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'PPTWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'file', 'format', 'pptx'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'PPT 슬라이드 생성 요청에 사용. 사내 템플릿 자동 적용.'
        )
     ),
     1),

    -- 13. XlsxWorker
    (UUID(), 'native-xlsx', '엑셀 생성/수정',
     'Excel 파일 생성/수정/서식/차트/피벗',
     '📈', JSON_ARRAY('엑셀', 'xlsx'),
     'system', 'lucid',
     'native', JSON_ARRAY('run'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'XlsxWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'file', 'format', 'xlsx'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'Excel 파일 생성, 수정, 서식 적용 요청에 사용.'
        )
     ),
     1),

    -- 14. CalendarWorker
    (UUID(), 'native-calendar', '캘린더',
     '일정 조회/등록/삭제, 빈 시간 검색, 타인 공개 캘린더',
     '📅', JSON_ARRAY('캘린더', '일정'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'CalendarWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '일정 조회/등록/삭제, 빈 시간 검색 요청에 사용.'
        )
     ),
     1),

    -- 15. ReservationWorker
    (UUID(), 'native-reservation', '회의실/자산 예약',
     '회의실 조회/등록/취소, 빈 회의실 검색',
     '🏢', JSON_ARRAY('예약', '회의실'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'ReservationWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '회의실/자산 예약 조회, 등록, 취소 요청에 사용.'
        )
     ),
     1),

    -- 16. BoardWorker
    (UUID(), 'native-board', '사내 게시판 검색',
     '전사/회사별 공지사항·게시글 검색',
     '📌', JSON_ARRAY('게시판', '공지'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'BoardWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '사내 게시판 공지/게시글 검색 요청에 사용.'
        )
     ),
     1),

    -- 17. NasWorker
    (UUID(), 'native-nas', 'NAS 파일 탐색',
     '사내 Synology NAS 파일 탐색·다운로드',
     '🗂️', JSON_ARRAY('NAS', '공유폴더'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'NasWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', '사내 NAS 공유폴더 파일 탐색/다운로드 요청에 사용.'
        )
     ),
     1),

    -- 18. OutlineWorker
    (UUID(), 'native-outline', 'L&F Wiki',
     'Outline Wiki 문서 검색/조회/생성/수정',
     '📖', JSON_ARRAY('Wiki', 'Outline', '문서'),
     'system', 'lucid',
     'native', JSON_ARRAY('chat'), 'public', 'active',
     '1.0.0',
     JSON_OBJECT(
        'platform', 'native',
        'runtime', JSON_OBJECT('platform', 'native', 'worker_class', 'OutlineWorker'),
        'inputs', JSON_ARRAY(),
        'output', JSON_OBJECT('type', 'text'),
        'intent_hints', JSON_OBJECT(
            'system_prompt', 'L&F Wiki 문서 검색, 조회, 생성, 수정 요청에 사용.'
        )
     ),
     TRUE);


-- ============================================================
-- 검증 쿼리 (실행 후 확인용)
-- ============================================================
-- SELECT COUNT(*) FROM agents WHERE is_native_seed = TRUE;  -- 기대: 18
-- SELECT COUNT(*) FROM runners;                              -- 기대: 4
-- SELECT slug, name, platform, status FROM agents WHERE is_native_seed = TRUE ORDER BY name;

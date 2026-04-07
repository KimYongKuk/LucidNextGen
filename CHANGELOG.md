# 변경 이력 (CHANGELOG)

> 이 파일은 Claude Code 작업 세션 중 자동으로 업데이트됩니다.
> 상세 내용은 각 항목의 [상세] 링크를 참조하세요.

---

## [2026-04-07]
- **추가** [UserFilesWorker] 파일 전문 전달 기능(Fulltext) — 업로드 시 전체 텍스트 디스크 보관(`data/fulltext/`), `get_uploaded_file_content` MCP 도구(50,000자 제한), 요약/번역은 전문 전달·검색은 기존 ChromaDB 유지 → [상세](docs/history/2026-04-07_Fulltext-전문전달.md)

## [2026-04-06]
- **수정** [CalendarWorker/ReservationWorker] 테스트 버그 수정 및 기능 보강 — find_available_rooms 도구 추가(LLM 시간대 분석 오류 방지), create_reservation 충돌 사전 검증, get_my_calendars user API 기반 변경, URL 인코딩/timeType 수정, attendee_names 사내 참석자 이름 검색, 일정+회의실 동시 등록, calendar+reservation 인텐트 우선 규칙 → [상세](docs/history/2026-04-06_캘린더-예약-Worker.md)
- **추가** [NASWorker] NAS 파일 탐색/다운로드/업로드 — Synology NAS WebDAV 연동, 6개 MCP 도구(목록/검색/다운로드/정보/업로드/폴더생성), 이중 경로 검증 + 로컬 산출물 샌드박스, 감사 로깅 → [상세](docs/history/2026-04-06_NAS-Worker.md)
- **추가** [OutlineWorker] 하이브리드 시멘틱 검색 — Outline 키워드 검색 + ChromaDB 시멘틱 검색(BGE-m3-ko) → RRF 병합, Haiku 문서 요약 → 임베딩 동기화, 30분 주기 증분 동기화, 수동 트리거 API → [상세](docs/history/2026-04-06_Outline-시멘틱-검색.md)
- **추가** [OutlineWorker] 텍스트 직접 문서 생성/수정 도구 — create_document(마크다운→위키), update_document(기존 문서 수정), 파일 없이 위키 게시 가능, 쓰기 권한 검증 포함 → [상세](docs/history/2026-04-06_Outline-텍스트-문서-생성.md)
- **수정** [BaseWorker] 핸드오프 타겟 프롬프트 추가 — is_handoff_target일 때 "할 수 있는 것만 수행, 못 하는 부분 무시" 지시로 핸드오프 루프 방지 → [상세](docs/history/2026-04-06_Outline-텍스트-문서-생성.md)

## [2026-04-03]
- **추가** [BaseWorker] 파일 컨텍스트 공유 — 모든 워커에서 업로드 파일 접근 가능, search_user_files/search_workspace_docs 자동 주입, 시스템 프롬프트에 파일 컨텍스트 자동 추가 → [상세](docs/history/2026-04-03_파일-컨텍스트-공유.md)
- **수정** [VocWikiScheduler] 서버 시작 시 이벤트 루프 블로킹 해결 — boto3/MySQL 동기 호출 ThreadPoolExecutor 격리, misfire_grace_time 축소, since 1일 오버랩으로 누락 방지, 3/1~4/3 전량 447건 백필 완료 → [상세](docs/history/2026-04-03_VOC-위키-스케줄러-안정화.md)

## [2026-04-01]
- **추가** [CalendarWorker] 캘린더 일정 관리 Worker — LFON 캘린더 API 연동(6개 도구), 내 캘린더/관심 캘린더/공개 캘린더 조회, 일정 등록/삭제, 비공개 일정 필터링, SSO 서비스 계정 인증 → [상세](docs/history/2026-04-01_캘린더-Worker.md)
- **수정** [XlsxWorker] create_workbook 반복 호출 → 빈 워크북만 생성되는 버그 수정: 워크플로우 프롬프트 추가, 에러 규칙 개선, 중복 호출 코드 가드 → [상세](docs/history/2026-04-01_XlsxWorker_create_loop_fix.md)

## [2026-03-31]
- **추가** [Auth] 자체 로그인 인증 시스템 — SSO 병행 ID/PW 로그인, JWT 인증, 이메일 기반 셀프 비밀번호 설정, 로그아웃, 사이드바 사용자 표시 → [상세](docs/history/2026-03-31_자체-로그인-인증.md)
- **추가** [ReservationWorker] 회의실/자산 예약 Worker — LFON REST API 연동(6개 도구), 전 사업장 병렬 조회 내 예약 목록, 충돌 감지 후 대안 제시, 예약 등록/취소, SSO 서비스 계정 인증, v_user_info_mapping 재사용, CSRF Origin/Referer 헤더, 에러 메시지 상세 전달 → [상세](docs/history/2026-03-31_회의실-예약-Worker.md)
- **수정** [A2AStreaming] 도구 상태 메시지 Context-Aware 개선 — 정적 메시지 → 실제 검색어/키워드 기반 동적 메시지 생성, 도구 완료 메시지 차별화, 메시지 기반 중복 억제 → [상세](docs/history/2026-03-31_Context-Aware-Tool-Status.md)
- **추가** [ITSupportWorker] WORKS 서비스데스크 VOC 자동 등록 — IT 질문 답변 후 사용자 승인 시 SSO API로 앱릿 934에 VOC 등록 + 시스템별 담당 부서원 자동 배정 + 접수/담당자지정 상태 전환, OpenAPI 폴백 → [상세](docs/history/2026-03-31_WORKS-VOC-자동등록.md)
- **수정** [IntentClassifier] Follow-up 인텐트 유지 규칙 — quick_classify 미매칭 + previous_intent 존재 시 이전 인텐트 유지 (멀티턴 대화에서 direct/clarify로 빠지는 문제 해결) → [상세](docs/history/2026-03-31_WORKS-VOC-자동등록.md)

---

## [2026-03-30]
- **추가** [VOC Wiki] IT VOC → L&F Wiki 자동 축적 시스템 — 매일 배치로 VOC 해결 사례를 LLM 분류·병합하여 시스템/주제별 위키 문서로 축적 → [상세](docs/history/2026-03-30_VOC-Wiki-자동축적.md)
- **추가** [OpenAPI] OpenAI-호환 Chat Completions API — 별도 IAM, API Key 인증, 스트리밍/논스트리밍, Sonnet/Haiku 지원, 토큰 사용량 추적 → [상세](docs/history/2026-03-30_OpenAI-호환-API-엔드포인트.md)
- **수정** [BaseWorker] 대화 요약 임계치 상향 + 프롬프트 강화 (6msg/5K→12msg/15K, 구조 보존 요약) — 옵션/선택지가 조기 요약으로 소실되는 문제 방지 → [상세](docs/history/2026-03-30_대화요약-임계치-상향.md)
- **수정** [MCPAdapter] 캐시 리프레시 행(hang) — excel_server 영구실패→TTL 60초→대량 서브프로세스 스폰→행. 블랙리스트+타임아웃+절대경로 적용 → [상세](docs/history/2026-03-30_MCP-캐시-행-수정.md)
- **수정** [Outline,Frontend] 임베드 채팅 userId anonymous 버그 — embed-chat.tsx에서 사번을 useSimpleChat에 미전달 → 로그 정상 기록 → [상세](docs/history/2026-03-30_Outline-embed-userId-버그수정.md)
- **수정** [OutlineMCP] list_collections 문서 수 부정확 — Outline API의 캐시된 documentCount 대신 실제 문서 트리 병렬 조회로 정확한 카운트 반환 → [상세](docs/history/2026-03-30_Outline-컬렉션-문서수-수정.md)

---

## [2026-03-25]
- **수정** [OutlineWorker,MCP] 위키 게시 파이프라인 통합 — 3개 도구(extract+upload×N+create) → publish_file_to_wiki 원스텝으로 통합, 이미지 병렬 업로드, 정제 모드 제거 → [상세](docs/history/2026-03-25_OutlineWiki-게시-파이프라인-통합.md)
- **추가** [OutlineWorker] 컬렉션 접근 제어 — 사번 기반 Outline DB 권한 조회로 읽기/쓰기 도구에 사용자별 컬렉션 필터링 적용 → [상세](docs/history/2026-03-25_OutlineWorker-컬렉션-접근제어.md)
- **수정** [PDFVisionService] Vision OCR 판정 로직 개선 + PPTX media_type 버그 수정 → [상세](docs/history/2026-03-25_Vision-OCR-판정로직-개선.md)
- **수정** [ChromaDB] PPTX 이미지 해시 중복 제거 + 모델 로드 안정화 (low_cpu_mem_usage)

---

## [2026-03-24]
- **추가** [OutlineWorker,MCP] 파일→위키 문서 생성 기능 — PDF/PPTX/DOCX 업로드 파일에서 텍스트+이미지 추출하여 L&F Wiki 문서 자동 게시 → [상세](docs/history/2026-03-24_OutlineWiki-파일-문서생성.md)
- **수정** [Orchestrator,IntentClassifier] HANDOFF 마커 감지 실패 + 파일 참조 인텐트 오분류 — `_extract_text` list content 처리 추가, 업로드 파일 명시 참조 시 USER_FILES 우선 → [상세](docs/history/2026-03-24_핸드오프-파일참조-인텐트-수정.md)
- **수정** [IntentClassifier] 워크스페이스 인스트럭션 기반 인텐트 분류 — Classifier 프롬프트에 instructions 앞 500자 전달, 워크스페이스 목적에 맞는 전문 Worker 라우팅 → [상세](docs/history/2026-03-24_워크스페이스-인텐트-분류-개선.md)
- **수정** [BaseWorker] 내부 DB 스키마 노출 방지 가드레일 추가 — 응답에 뷰 이름/컬럼명/SQL 쿼리 포함 금지 → [상세](docs/history/2026-03-24_워크스페이스-인텐트-분류-개선.md)

---

## [2026-03-23]
- **수정** [Orchestrator] 워크스페이스 우선 실행 + 전문 워커 폴백 — user_files 강제 오버라이드 제거, workspace-first 1순위 실행 후 NO_RESULTS 시 원래 전문 워커 자동 폴백 → [상세](docs/history/2026-03-23_워크스페이스-우선실행-폴백.md)
- **수정** [ApprovalWorker] 부서 문서함 접근 범위 수정 — dept_id 단일 필터 → v_appr_user_accessible_depts JOIN으로 변경, 소속+담당자 지정 부서 모두 검색 가능 → [상세](docs/history/2026-03-23_부서문서함-접근범위-수정.md)
- **수정** [Architecture] 공유 도구함 + 시각화 3모드 리팩토링 — VisualizationWorker 제거, shared_tool_names 4개 에이전트 분배, Recharts(데이터)+SVG(구조)+HTML위젯(복합) 3모드, HTML iframe CSS변수 테마 대응+실시간 높이 갱신, 차트 output_mode 통합, HANDOFF 마커 필터 → [상세](docs/history/2026-03-23_공유도구함_인라인SVG.md)

---

## [2026-03-20]
- **수정** [Briefing] 수신문서 접수대기 정확도 개선 — accessible_depts JOIN, reception_status=WAITING 필터, is_assigned 레거시 제거 → [상세](docs/history/2026-03-20_BriefingReceivedDocsFix.md)
- **추가** [VisualizationWorker] SVG 인포그래픽 + Mermaid 다이어그램 — SVG MCP 서버(regex 정제, DOMPurify), Mermaid 코드 블록 자동 렌더링, 시각화 3종 체계(Charts/Mermaid/SVG) → [상세](docs/history/2026-03-20_SVGVisualGenerator.md)

---

## [2026-03-19]
- **추가** [OutlineWorker + Embed] L&F Wiki 연동 — MCP 서버 5개 도구, `/embed` iframe 채팅 페이지, outline_embed 모드 인텐트 격리, postMessage 링크 연동, HANDOFF 비활성화 → [상세](docs/history/2026-03-19_OutlineWikiWorker.md)
- **추가** [PPTWorker] PPTX 생성 퀄리티 대폭 개선 — Shape 3종 추가(callout_box/kpi_card/divider), 차트 스타일(색상/라벨/범례), 레이아웃 패턴 10종, 디자인 규칙/차트 예시 프롬프트 → [상세](docs/history/2026-03-19_PPTXQualityEnhancement.md)
- **수정** [OrgChart MCP] PostgreSQL 부서ID 컬럼 대소문자 fold 에러 수정 — 계층 조회 Step1 실패로 LLM 10회 삽질 방지 → [상세](docs/history/2026-03-19_OrgChartColumnQuoting.md)
- **수정** [MailWorker] .eml 파서 스트리밍 방식 전환 — 5MB 파일 크기 제한 제거, 첨부파일 크기와 무관하게 메일 본문 추출 가능 → [상세](docs/history/2026-03-19_MailStreamingEmlParser.md)

---

## [2026-03-18]
- **수정** [Orchestrator] MCP 도구 로드 실패 시 DirectWorker 자동 폴백 — tavily-mcp 등 MCP 서버 장애 시 도구 0개로 실행되어 가짜 tool_call 태그가 노출되던 문제 방지 → [상세](docs/history/2026-03-18_ToolFallback.md)
- **수정** [Streaming] tool_call/tool_response 태그 스트리밍 노출 방지 — 상태 기반 문자 단위 필터링, 프론트엔드 sanitizeText 안전장치 → [상세](docs/history/2026-03-18_ToolCallTagFiltering.md)
- **추가** [인프라] nginx + PM2 + NSSM 기반 Blue-Green 무중단 배포 시스템 구축 — 운영/개발 환경 분리, 자동 배포(12:10/22:30), 15초 롤백 → [상세](docs/history/2026-03-18_BlueGreenDeploy.md)

---

## [2026-03-17]
- **수정** [MailWorker/ApprovalWorker] ReAct loop 토큰 폭증 해결 — 워커별 compact_keep_recent_pairs 도입(메일6/결재4), 도구별 차등 truncation(목록16K/상세6K), 결재 doc_body HTML 태그 제거 후 10K truncation → [상세](docs/history/2026-03-17_MailWorkerTokenOptimization.md)
- **추가** [Orchestrator] Cross-Worker HANDOFF 메커니즘 — 워커 간 데이터 연계 (히스토리 활용 + 선행 워커 자동 체이닝), WORKER_CAPABILITIES 레지스트리, 요약 테이블 보존 강화 → [상세](docs/history/2026-03-17_CrossWorkerHandoff.md)

---

## [2026-03-16]
- **추가** [Desktop] Tauri v2 데스크톱 앱 — 시스템 트레이 상주, Ctrl+Space 글로벌 단축키 퀵 채팅, 마크다운 렌더링(GFM 테이블), FOLLOW_UP 버튼 UI → [상세](docs/history/2026-03-16_TauriDesktopApp.md)
- **수정** [XlsxWorker] tavily_search 도구 결과 잘림 버그 수정 — XlsxWorker의 secured_ainvoke 래핑이 전역 캐시된 tavily_search에 적용되어 모든 웹검색 결과를 8,000자로 잘리고 ⚠️ 경고 메시지가 LLM에 "오류"로 해석되던 문제 해결 → [상세](docs/history/2026-03-16_TavilyTruncationBug.md)

---

## [2026-03-12]
- **추가** [Bedrock] 리전 폴백 시스템 — us-east-1 쓰로틀링 시 us-west-2로 자동 전환, cross-region→on-demand 모델 ID 변환, UTC 자정 자동 복구, 전환/복구 시 관리자 메일 알림 → [상세](docs/history/2026-03-12_RegionFallback.md)
- **수정** [XlsxWorker] 토큰 최적화 2차 — AIMessage tool_calls args 압축 추가(data 배열 300자), keep_recent 2→1, 비문자열 결과 잘림 처리로 438K→~60K 토큰 절감 → [상세](docs/history/2026-03-12_XlsxWorkerTokenOptimization2.md)
- **수정** [Upload] 한글/특수문자 파일명 PPTX 업로드 실패 수정 — 임시 파일 경로에서 원본 파일명 제거, 상대경로→절대경로 전환
- **수정** [Chat] 대용량 이미지 Bedrock 전송 실패 수정 — 5MB 초과 이미지 자동 JPEG 압축(해상도 축소+quality 하향), Pillow 기반

---

## [2026-03-11]
- **추가** [Logging] 서버 로그 파일 출력 — RotatingFileHandler + _TeeWriter로 콘솔/파일 동시 출력, tail_log.bat으로 실시간 모니터링 → [상세](docs/history/2026-03-11_FileLogging.md)
- **수정** [Intent] 결재 follow-up 인텐트 오분류 수정 — "WA전표품의" 등 결재 양식명이 acct_support로 분류되던 버그 해결, previous_intent 전달로 follow-up 판단 강화 → [상세](docs/history/2026-03-11_ApprovalFollowUpIntent.md)
- **수정** [BaseWorker] Haiku 대화 요약 기본화 — 3개 워커 중복 코드(~300줄) 제거, 모든 워커에 멀티턴 요약 적용, PPTWorker에 compact_previous_results 추가 → [상세](docs/history/2026-03-11_BaseWorkerSummarization.md)
- **수정** [XlsxWorker] ReAct loop 토큰 최적화 — 이전 step tool result 압축(200자) + 개별 결과 8,000자 제한으로 82% 토큰 절감 → [상세](docs/history/2026-03-11_XlsxWorkerTokenOptimization.md)
- **추가** [Upload] PPTX 슬라이드 이미지 OCR — 업로드된 PPT의 표/차트/그룹shape/이미지를 모두 추출, 이미지는 Vision API OCR 처리 → [상세](docs/history/2026-03-11_PPTXImageOCR.md)
- **수정** [알림] 브리핑 수신문서에 임시저장(TEMPSAVE) 문서 노출 버그 수정 — `v_appr_dept_received` 쿼리에 `appr_status != 'TEMPSAVE'` 필터 추가

---

## [2026-03-10]
- **추가** [Dashboard] 토큰 사용량 모니터링 — 모든 LLM 호출(Sonnet/Haiku)을 token_usage_log 테이블에 기록, 모델별/워커별/사용자별 대시보드 시각화 → [상세](docs/history/2026-03-10_TokenUsageMonitoring.md)
- **수정** [Intent] 게시글 제목 내 "메일" 키워드 오분류 수정 — board_guard 패턴 추가로 게시글 요청이 MAIL로 잘못 라우팅되는 버그 해결
- **수정** [OrgChart] 조직도 계층 조회 — `부서경로` 컬럼 활용, 상위 부서 검색 시 하위 부서 전체 포함 (2단계 쿼리 패턴) → [상세](docs/history/2026-03-10_OrgChartHierarchy.md)
- **추가** [Visualization] Word(DOCX) 문서 생성 기능 — VisualizationWorker에 docx_generator MCP 서버 통합, 편집 가능한 Word 문서 생성/다운로드 지원 → [상세](docs/history/2026-03-10_DocxGenerator.md)
- **추가** [Frontend] PDF/DOCX 인라인 미리보기 — 생성된 PDF(iframe)/DOCX(docx-preview) 파일을 오른쪽 패널에서 바로 미리보기 → [상세](docs/history/2026-03-10_DocumentPreview.md)
- **수정** [PDF Generator] PDF 품질 개선 — 여백/색상 DOCX와 통일, 표 텍스트 자동 줄바꿈, 코드 블록 잘림 제거, 부제목 지원 → [상세](docs/history/2026-03-10_PDFQualityImprovement.md)
- **수정** [BaseWorker] LUCID_AI_IDENTITY 기능 목록 업데이트 — Word(DOCX) 생성, 사내 게시판 검색 추가, 메일 요약/답장 초안 반영 (16→18개)
- **추가** [Observability] 요청별 토큰 사용량 추적 — LLM 호출마다 input/output 토큰 수집, chat_log_new.metadata JSON에 저장 → [상세](docs/history/2026-03-10_PromptCompression.md)
- **수정** [Prompt/Config] 프롬프트 경량화 — 메타데이터 스키마 전체 59% 압축 (55.9KB→23KB), base_worker 날짜 규칙 압축, xlsx/mail max_agent_steps 하향 → [상세](docs/history/2026-03-10_PromptCompression.md)
- **추가** [BaseWorker] Bedrock Prompt Caching — CachedChatBedrockConverse 서브클래스로 system prompt 캐싱, Agent loop 내 2회차부터 입력 토큰 90% 절감, cache 메트릭 DB 저장 → [상세](docs/history/2026-03-10_PromptCaching.md)

---

## [2026-03-09]
- **추가** [Intent] CLARIFY 인텐트 + 자동 Fallback Worker — 모호한 요청 사전 확인 + 1순위 검색 실패 시 LLM 선정 2순위 워커 자동 실행 + 양쪽 실패 시 대안 범위 제시 → [상세](docs/history/2026-03-09_ClarifyIntent.md)
- **수정** [알림] 실시간 알림 팝업 특정 사번 제한 해제 → 전체 사용자 대상으로 개방
- **수정** [Memory] 사용자 메모리 LLM 기반 압축 — key facts 상한 20→100개, 초과 시 FIFO 대신 Haiku가 중요도 판단하여 공격적 병합/삭제 → [상세](docs/history/2026-03-09_UserMemoryConsolidation.md)
- **수정** [Memory] 사용자 메모리 로딩 버그 수정 — bare list JSON 파싱 실패로 메모리가 로드되지 않던 문제 해결, 프롬프트 개선 → [상세](docs/history/2026-03-09_UserMemoryConsolidation.md)
- **수정** [NightlySummary] misfire_grace_time 설정 추가 — APScheduler 기본 1초→3600초(1시간), 이벤트 루프 지연 시 스케줄러 스킵 방지

---

## [2026-03-06]
- **추가** [Dashboard] 워크스페이스 상세 모달 — 메시지 수/문서 수 클릭 시 상세 리스트(메시지 목록, 문서 목록) 팝업 → [상세](docs/history/2026-03-06_WorkspaceDetailModal.md)
- **수정** [Board] 게시판 검색에서 JHC/L&F Plus 제외 — MCP 서버 자동 필터 + 메타데이터 + 알림 서비스 반영 → [상세](docs/history/2026-03-06_BoardExcludeJHC.md)
- **추가** [Image] 업로드 이미지 영구 보존 — 이미지를 디스크에 저장하고 채팅 히스토리에서 영구적으로 확인 가능하도록 개선 → [상세](docs/history/2026-03-06_ImagePersistence.md)
- **추가** [Archive] Output 파일 아카이브 시스템 + 업로드 폴더 구조 개선 — MCP 생성 파일을 날짜/사용자별 아카이브 복사, 업로드 파일 날짜/사용자ID별 정리 → [상세](docs/history/2026-03-06_FileArchiveSystem.md)
- **수정** [Upload] 30일 파일 보관 및 자동 정리 시스템 — 업로드 원본 파일 디스크 보관, ChromaDB 세션 30일 유지, 프론트엔드 즉시삭제 제거 → [상세](docs/history/2026-03-06_UploadRetention30Day.md)
- **수정** [Notification] 브리핑 모달 백그라운드 클릭 닫힘 방지 — `onInteractOutside` preventDefault 적용, ESC 키는 허용 유지

---

## [2026-03-05]
- **수정** [Intent] 후속 질문 인텐트 오분류 수정 — LLM 분류 시 대화 히스토리(최근 4개) 전달, FOLLOW-UP 룰 추가로 맥락 기반 분류 지원 → [상세](docs/history/2026-03-05_IntentFollowUpContext.md)
- **추가** [Branding] 커스텀 로고 적용 — 사이드바 헤더, AI 응답 아이콘(로딩:SVG/완료:PNG), 브라우저 favicon → [상세](docs/history/2026-03-05_LogoBranding.md)
- **수정** [Mail] 메일 검색 하이브리드 개선(v4) — SQL LIKE(전체 메일함 preview 검색) + Java MIME(최근 1000건 제목 매칭) 2단계 병합, 하위폴더 메일 누락 해결 → [상세](docs/history/2026-03-05_MailSearchFix.md)
- **수정** [Intent] 차트/PPT 생성 요청이 web_search로 오분류되는 문제 수정 — quick_classify에 visualization/ppt 키워드 패턴 추가, 생성 워커가 자체 tavily_search로 데이터 조사+생성 일괄 처리
- **수정** [Response] Worker 마커 텍스트 노출 버그 수정 — `<!--WORKER:name-->` 텍스트 삽입 방식을 메시지 객체 필드로 분리, 간헐적 UI 노출 근본 해결 → [상세](docs/history/2026-03-05_WorkerMarkerLeak.md)
- **수정** [Mail] 브리핑 팝업 안 읽은 메일 Inbox 하위 폴더 포함 — JSP unread 쿼리에 `Inbox.*` 하위폴더 포함, total_count 반환 추가
- **수정** [Intent] quick_classify 구조 개선 + 프롬프트 슬림화 — pairwise 충돌 체크 → scan-all 패턴, CLASSIFIER_PROMPT ~180줄→~100줄, web_search fallback 분리 → [상세](docs/history/2026-03-05_IntentClassifierRefactor.md)
- **수정** [Notification] 알림 모달 로딩 개선 — 즉시 오픈 + 타이핑 애니메이션, 전체 데이터 로딩 후 한꺼번에 표시, 건수 3건 제한 → [상세](docs/history/2026-03-05_NotificationProgressiveLoading.md)
- **수정** [MCP] MCP 서버 로딩 복원력 강화 — 개별 서버 실패 시 전체 장애 대신 해당 서버만 스킵, 실패 서버명 로그 출력
- **추가** [NightlySummary] 일일 개발 요약 스케줄러 — 매일 23시 KST CHANGELOG+history 기반 보고서 생성, HTML 메일 발송 → [상세](docs/history/2026-03-05_NightlySummaryScheduler.md)

---

## [2026-03-04]
- **추가** [PPT/Excel/PDF] 생성형 Worker 웹검색 도구 추가 — PPTWorker, XlsxWorker, VisualizationWorker에 tavily_search 추가, 시장 현황/트렌드 등 최신 데이터 조사 후 생성 → [상세](docs/history/2026-03-04_WorkerWebSearch.md)
- **추가** [Mail] 메일 전체 본문 조회/요약/답장 초안 기능 — JSP detail action, get_mail_detail MCP 도구, .eml 파일 MIME 파싱, Worker 프롬프트 요약/답장 워크플로우 → [상세](docs/history/2026-03-04_MailDetailSummarize.md)
- **수정** [Mail] 메일 검색 전략 개선 — 받은편지함 우선 조회(limit=50) → search_mail 폴백, 짧은 키워드 권장, MCP 디버그 로그에 kwargs 추가 → [상세](docs/history/2026-03-04_MailDetailSummarize.md)

---

## [2026-03-03]
- **수정** [ArtifactDetection] 파일 아티팩트 false positive 수정 — 비-엑셀 워커 응답에서 .xlsx 파일명 언급 시 잘못된 프리뷰/다운로드 링크 생성 방지, 워커 이름 기반 조건부 감지 → [상세](docs/history/2026-03-03_ArtifactDetectionFalsePositive.md)
- **추가** [FollowUp] 팔로우업 제안 기능 — AI 응답 후 맥락 기반 후속 질문 3개를 입력창 위 수평 칩으로 제안, Worker별 능력 메뉴 기반 → [상세](docs/history/2026-03-03_FollowUpSuggestions.md)
- **수정** [IntentClassifier] 메일/전자결재 인텐트 오분류 수정 — 메일 제목에 "전자결재" 포함 시 APPROVAL로 잘못 라우팅되던 문제 해결 → [상세](docs/history/2026-03-03_IntentMailApprovalDisambiguation.md)
- **추가** [ServiceHub] Lucid AI 서비스 허브 구상 — 사내 자동화/AI 서비스 통합 실행 플랫폼 아키텍처 설계 (Agent/Workspace/Trigger 3유형, VDI 데몬, REST 표준 스펙) → [상세](docs/history/2026-03-03_LucidServiceHub.md)
- **수정** [Approval] 알림 모달→전자결재 문서 접근 개선 — 참조/결재대기/수신 문서 클릭 시 출처+doc_id 포함, 선제 거부 제거 → [상세](docs/history/2026-03-03_ApprovalNoticeAccess.md)
- **수정** [PDFVision] 이미지 기반 PDF Vision OCR 휴리스틱 개선 — 텍스트 30자 미만 페이지는 is_complex 무관하게 Vision API 호출 → [상세](docs/history/2026-03-03_PDFVisionHeuristic.md)
- **추가** [ChangeLog] 자동 변경 이력 관리 시스템 도입 — CLAUDE.md 지침 + CHANGELOG.md 인덱스 + docs/history/ 상세 기록 자동화
- **추가** [Bedrock] 리전별 모델 ID 및 Inference Profile 정리 — Sonnet 4.6 테스트, 프리픽스 체계(us/apac/global/ON_DEMAND), 서울 리전 제약 사항 → [상세](docs/history/2026-03-03_BedrockRegionModelID.md)

---

## [2026-02-27]
- **추가** [FileCleanup] 범용 파일 정리 스케줄러 — PDF/PPT/차트/XLSX/업로드 5개 디렉토리 통합, APScheduler 기반 → [상세](docs/history/2026-02-27_FileCleanupScheduler.md)
- **추가** [UserMemory] 글로벌 사용자 메모리 최적화 — 불필요 fact 필터링, 신원정보 보호, 프롬프트/후처리 강화 → [상세](docs/history/2026-02-27_UserMemoryOptimization.md)
- **수정** [ServiceDashboard] 서비스 레포트 대시보드 기능 명세 — 7개 섹션 종합 리포트, 관리자/테스터 제외, 모달 드릴다운 → [상세](docs/history/2026-02-27_ServiceDashboard.md)
- **검토** [PPTWorker] Gamma API 도입 검토 — Pro 플랜 $25/월, Generate API GA, 사내 템플릿 적용 가능성 PoC 예정 → [상세](docs/history/2026-02-27_GammaAPI_PPT_Review.md)
- **삭제** [PDFCleanup] 기존 PDF 전용 정리 스케줄러 제거 (`backend/app/utils/pdf_cleanup.py`)

---

## [2026-02-25]
- **추가** [XLSXWorker] 엑셀 생성/수정 워커 — excel-mcp-server 24개 도구, 파일 Lock, Univer 프리뷰, 수식 프리컴퓨팅 → [상세](docs/history/2026-02-23_ExcelWorker.md)

---

## [2026-02-24]
- **추가** [BoardWorker] 사내 게시판 검색 워커 — 다우오피스 43개 공개 게시판 자연어 검색, 본문 상세 조회 → [상세](docs/history/2026-02-24_BoardWorker.md)

---

## [2026-02-23]
- **추가** [ApprovalWorker] 전자결재 조회 모듈 — Dual-mode 아키텍처, 9개 PostgreSQL VIEW, prepare_tools 보안 래핑 → [상세](docs/history/2026-02-23.md)
- **추가** [MailWorker] 사내 메일 조회 모듈 — 5개 MCP 도구, JSP 엔드포인트 연동, message_store 캐싱 → [상세](docs/history/2026-02-23.md)
- **추가** [ServiceReport] 서비스 레포트 대시보드 — 6개 백엔드 API + 9개 프론트엔드 컴포넌트, 날짜별/인텐트별 분석 → [상세](docs/history/2026-02-23_report.md)
- **추가** [TableCopy] 테이블 엑셀 복사 버튼 — 호버 시 TSV 복사 버튼 표시, 엑셀 붙여넣기 지원 → [상세](docs/history/2026-02-23.md)
- **수정** [IntentClassifier] 인텐트 분류기 개선 — MAIL/APPROVAL 인텐트, 워크스페이스-인식 라우팅, "결산" vs "결재" 구분 → [상세](docs/history/2026-02-23.md)
- **수정** [BaseWorker] prepare_tools() 훅, 도구 스키마 디버깅, LLM 응답 디버깅 로그 추가 → [상세](docs/history/2026-02-23.md)
- **수정** [Streaming] 메일/전자결재 도구 상태 메시지, 워크스페이스 메타데이터 전달, SQL 쿼리 로깅 → [상세](docs/history/2026-02-23.md)
- **수정** [CodeBlock] 언어 미지정 코드블록에도 복사 버튼 표시 → [상세](docs/history/2026-02-23.md)
- **삭제** [FeedbackModal] 피드백 모달 컴포넌트 제거 (`frontend/components/feedback-modal.tsx`)

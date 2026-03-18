# 변경 이력 (CHANGELOG)

> 이 파일은 Claude Code 작업 세션 중 자동으로 업데이트됩니다.
> 상세 내용은 각 항목의 [상세] 링크를 참조하세요.

---

## [2026-03-18]
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

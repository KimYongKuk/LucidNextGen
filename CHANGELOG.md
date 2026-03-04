# 변경 이력 (CHANGELOG)

> 이 파일은 Claude Code 작업 세션 중 자동으로 업데이트됩니다.
> 상세 내용은 각 항목의 [상세] 링크를 참조하세요.

---

## [2026-03-04]
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

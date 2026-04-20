# 변경 이력 (CHANGELOG)

> 이 파일은 Claude Code 작업 세션 중 자동으로 업데이트됩니다.
> 상세 내용은 각 항목의 [상세] 링크를 참조하세요.

---

## [2026-04-21]
- **추가** [XlsxWorker/xlsx_simple] 다중 시트 생성 + `modify_xlsx` 신설 — 전날 환각 방지로 4개 도구만 노출됐던 XlsxWorker에 빠졌던 2가지 유스케이스(**다중 시트 신규 생성**, **기존 파일 수정**)를 single-call 원칙 유지하며 확장. `create_xlsx`에 `sheets=[{name, headers, rows}, ...]` 배열 파라미터 추가(backward-compat, 기존 headers/rows 호출 유지). `modify_xlsx` MCP 도구 신설 — `operations` 배열로 7종 op(`update_cells`, `add_sheet`, `delete_sheet`, `rename_sheet`, `apply_formula`, `delete_rows`, `delete_columns`)를 한 번의 호출로 원자적 적용 (중간 실패 시 `wb.save` 미호출 → 디스크 원본 불변). `XlsxWorker.tool_names`에 추가, 프롬프트에 "결정 플로우"(신규/수정/업로드 파일 수정) 섹션 추가, FINAL_GUARD 감지 대상 확장(성공 시 "생성/수정되었습니다" 분기). 업로드 파일 수정 시 `_redirect_upload_to_output`이 자동 적용되어 원본 보존 + output 복사본에서 수정. E2E 단위테스트 6+4개 PASS → [상세](docs/history/2026-04-21_XlsxWorker-ModifyXlsx.md)
- **삭제** [Frontend/AppSidebar] "Delete All Chats" 휴지통 버튼 제거 — Vercel AI Chatbot 템플릿에서 그대로 남아있던 레거시 버튼. 블라스트 반경이 크고(전체 채팅 영구 삭제), 실제로 프론트가 호출하던 `DELETE /api/history`(id 없는 버전)는 백엔드 라우트에서 400 반환하는 **이미 고장난 상태**였음. 개별 삭제는 사이드바 히스토리에서 여전히 가능(`?id=` 유지). `app-sidebar.tsx`에서 버튼·AlertDialog·`handleDeleteAll`·관련 state + 미사용 import(`TrashIcon`, `AlertDialog*`, `useSWRConfig`, `unstable_serialize`, `getChatHistoryPaginationKey`, `toast`) 정리.
- **수정** [Upload/ChromaDB] 암호화 파일 업로드 소프트 실패 + 사전 감지 — 비밀번호 보호 PDF / OLE2 Compound(암호화 Office) 파일이 ChromaDB 임베딩 실패로 전체 업로드 실패 처리되던 문제. `_detect_file_encryption()` 헬퍼로 업로드 시점 사전 감지(PyPDF2 `is_encrypted` + 매직 바이트 `\xd0\xcf\x11\xe0`), 감지되면 임베딩 단계를 스킵하고 `status=completed_disk_only`로 표시. 임베딩 중 예외 발생도 동일하게 soft-fail로 전환. 프론트(multimodal + workspace-settings)에서 이 상태를 ready + info 토스트로 처리 → VOC 첨부·다운로드는 정상, RAG 검색만 불가로 안내. `failed` 상태는 디스크 저장도 실패한 진짜 장애에만 남김 → [상세](docs/history/2026-04-21_암호화파일-업로드-소프트실패.md)
- **수정** [Frontend/ChatHeader] 알림함·Agent Store·L&F WIKI 아이콘 운영자 전용으로 제한 — 개발 중이던 3개 기능이 운영 서버에 그대로 노출된 핫픽스. `isOperatorUser(userId)` 유틸 신규 추가(기본값 `A2304013`, `NEXT_PUBLIC_OPERATOR_USERS` 환경변수로 확장 가능), `chat-header.tsx`에서 해당 3개 Tooltip/Button 블록을 `{isOperator && (...)}`로 감쌈. 관리자(Shield)·데일리 브리핑(Newspaper)·테마 토글은 기존 로직 그대로 유지.

---

## [2026-04-20]
- **추가** [ITSupportWorker/WORKS VOC] VOC 자동 등록 시 파일 첨부 지원 — 내부 API 리버스 엔지니어링으로 `/api/file` 업로드 + VOC body의 `_14v07o8vj` 필드에 메타 embed하는 2단계 플로우 구현. LLM은 파일명만 넘기고 MCP가 `user_uploads/{date}/{employee_number}/` 하위에서 안전하게 resolve. 프롬프트에 업로드 파일 목록 자동 주입으로 대화 중간 업로드도 다음 턴부터 인식. 업로드 사이즈 상한 10MB→50MB 동반 상향(nginx는 이미 50MB). **후속 수정**: 1차 테스트에서 paste/drag 이미지가 `/api/upload/image`(ChromaDB 미저장, 디스크만)로 올라와 `has_session_files()`가 False 반환 → Planner가 clarify로 오라우팅 → DirectResponseWorker가 "이미지 첨부 미지원" 환각 응답하던 이슈 수정. `has_session_files(session_id, user_id)` 시그니처 확장해 ChromaDB + 디스크 둘 다 체크, 프롬프트에 업로드 경과 시간 + 🆕 마커(최근 10분 이내) 추가, UUID 파일명이어도 🆕이면 현재 대화 관련성 인정하라는 규칙 강화 → [상세](docs/history/2026-04-20_WORKS-VOC-첨부파일.md)
- **추가** [SecurityGuard] 보안관 에이전트 추가 — 악의적 입력(프롬프트 인젝션/jailbreak/데이터 탈취/권한 탈취) 탐지·차단 시스템. 3-Layer(Rule 정규식 27개 + in-memory Rate Limit + Haiku LLM 재판정, rule 의심 30+ 시만 호출 + 일일 1000회 한도) → 5-Tier 대응(PASS/WARN/BLOCK_REQUEST/TEMP_24h/PERM) → 누적 승격(WARN 5→TEMP, TEMP 3→PERM). Orchestrator Phase -1 + chat.py/chat_a2a.py 조기 게이트. 관리자 API 7개 + `/admin/report` 내 보안 탭(KPI/추이/분포/Top 위반자/차단 해제/Dry-Run 테스트/이벤트 상세 모달). TEMP/PERM 차단 시 기존 `email_service.py`로 관리자 메일 발송. 차단 사용자에게 위협 타입 + 해제 시각 공개. 신규 테이블 3개(events/blocks/llm_daily_usage, DBA 마이그레이션 필요) → [상세](docs/history/2026-04-20_Security_Guard_Agent.md)
- **추가** [XlsxWorker/xlsx_simple] 단일 합성 MCP 도구 `create_xlsx` — 같은 날 4차에 걸친 방어 코드 누적(응답 표준화 → DEDUP 제거 → 시트명 통일 → 앵커 리다이렉트)에도 LLM 환각 반복. 원인은 `excel-mcp-server`의 2-step workflow(`create_workbook` → `write_data_to_excel`)가 Sonnet 4.6의 multi-call 불안정성(filepath 변조·중복 호출·짧은 응답 환각)과 결합된 구조적 문제. 방향 전환: 방어 대신 **단순화**. `backend/app/mcp_servers/xlsx_simple/server.py` 신규(≈110줄, openpyxl 직접 호출), 도구 1개 `create_xlsx(filepath, headers, rows, sheet_name)` — 파일 생성+데이터 쓰기+저장을 single-call로 완결. `mcp_config.json`에 등록, `XlsxWorker.tool_names` 최상위 추가, 프롬프트 최상단에 "신규 생성 = create_xlsx 하나만" 원칙 명시. 4차 수정의 앵커 리다이렉트 로직은 제거(불필요). excel-mcp는 기존 파일 수정·편집용으로 유지 → [상세](docs/history/2026-04-20_XlsxSimple-Single-Tool.md)
- **수정** [XlsxWorker] 환각 방지 4-pass 수정 — 엑셀 파일이 정상 생성됨에도 Sonnet이 "서버 오류" 환각으로 실패 응답을 내보내던 구조적 문제. **1차**: `excel-mcp-server`의 짧은 성공 응답(`"Data written to Sheet"` 등)을 `_enrich_tool_result()`로 `✅ SUCCESS:` 표준 포맷(파일명/행·열/다음 단계)으로 정규화, GUARD 메시지도 동일 포맷 통일, 프롬프트 규칙 7/8 강화. **2차**: 1차 배포 후에도 재발 — 실제 근본 원인은 `_deduplicate_filepath`가 기존 파일 존재 시 조용히 `_2.xlsx`로 rename하여 **tool이 반환한 경로와 LLM이 후속 호출에 쓰는 경로가 불일치**(Sonnet은 자기 원래 경로 고수). write가 엉뚱한 파일에 쓰여 환각 유발. DEDUP 제거 + 덮어쓰기 전 `file_archive.archive_file()`로 이전 버전 백업. 설계 원칙 확립: "LLM 요청 경로 = 실제 파일 경로" (Single Source of Truth). **3차**: 2차 배포 후에도 재발 — `excel-mcp-server.create_workbook`의 기본 시트명이 **`Sheet1`**인데 프롬프트는 `sheet_name='Sheet'`를 사용 → `write_data_to_excel`이 없는 `Sheet`를 새로 생성 → `Sheet1`(빈)+`Sheet`(데이터) 공존 → LLM이 `get_workbook_metadata`로 검증 시 시트 2개 발견 → 환각. `_normalize_default_sheet_name()` 신설로 create_workbook 직후 내부적으로 `Sheet1`→`Sheet` 자동 rename (Lock 안에서 즉시 반영). 프롬프트 규칙 9("검증 과다 금지") 추가. 설계 원칙 확장: "Eventual Consistency 금지, 상태 변경은 즉시 반영". **4차**: 3차 배포 후에도 재발 — Sonnet이 tool 호출 간 filepath 일관성을 보장하지 않음. `create_workbook('랜덤데이터.xlsx')` 후 `write_data_to_excel('랜덤데이터_3.xlsx')` 처럼 접미사를 임의 추가하여 존재하지 않는 경로 에러 발생, 이후 원래 경로로 retry 성공했음에도 첫 에러를 근거로 전체 실패 환각. 세션 앵커(`session_anchor` dict) + 강제 리다이렉트(`REDIRECT_TO_ANCHOR` 18개 write 도구) 도입: create_workbook이 만든 경로를 앵커로 고정, 이후 모든 write 도구가 다른 경로를 지정해도 앵커로 자동 교정. 프롬프트 엔지니어링으로는 해결 불가능한 model-level behavior를 코드로 강제. 설계 원칙 완성: "Multi-call Invariants는 LLM의 선의에 의존하지 말고 코드로 강제" → [상세](docs/history/2026-04-20_XlsxWorker-SuccessResponse-Standardization.md)
- **수정** [예약/캘린더 인증] 운영 핫픽스 모음 — `PLANNER_ENABLED=true` 배포 후 예약/캘린더 관련 장애·취약점 대응. (1) 예약 도구 3종 gosso_cookie 주입 제외 (pydantic unexpected_keyword_argument 수정), (2) cancel_reservation 백엔드 소유자 검증 추가(프롬프트 의존 X, 60초 TTL 캐시), (3) reservation_mcp_server typing.Dict 미임포트 수정(+blue venv asyncpg 누락 수동 설치), (4) calendar 쓰기 서비스 계정 폴백 차단 시도 후 정상 케이스 파괴 확인되어 **리버트**, (5) 위젯-gw GOSSOcookie URL 전달 + use-simple-chat에 GOSSOcookie 대문자 regex 추가(효과 미확인, 무해). 추측 기반 수정 재발 방지용으로 HTTP response body 로깅 개선 권고 → [상세](docs/history/2026-04-20_예약-캘린더-인증-핫픽스.md)
- **추가** [Planner-Executor] Phase 4 — 실 Bedrock 통합 시나리오 검증 10/10 PASS — Sonnet Planner로 10개 다양한 시나리오(trivial 4 / 병렬 2 / 순차 2 / 복합 DAG 1 / confirm 1) 실행. PR파트 복합 7-task DAG를 정확히 분해(mail/corp_rag/reservation 병렬 → calendar 충돌확인 → reservation+calendar+mail 쓰기작업, 쓰기 task는 needs_confirm=true). 총 토큰 26,713 / 비용 ~$0.11 / 평균 지연 4.9초. 품질 이슈 없음 → [상세](docs/history/2026-04-20_Planner-Executor-Phase4.md)
- **추가** [Planner-Executor] Phase 3 — Executor + Synthesizer 구현 및 전 경로 통합 — `executor.py`(DAG 위상정렬 + asyncio.gather 병렬, MAX_PARALLEL=10, TIMEOUT=300s, 실패 cascade, needs_confirm=AWAITING_CONFIRM 처리), `synthesizer.py`(Haiku 기반 최종 응답 합성, is_trivial passthrough 최적화, LLM 실패 폴백), `orchestrator.py`에서 shadow를 실행 경로로 전환 (`_run_planner_executor` 메서드). `base_worker.py`에 `task_goal` 프롬프트 주입(원본 메시지 대신 sub-task 목표만 처리). 유닛 13개 PASS(Executor 6 + Synthesizer 4 + 통합 3) → [상세](docs/history/2026-04-20_Planner-Executor-Phase3.md)
- **추가** [Planner-Executor] Phase 2 — Planner 모듈 + shadow 모드 — `planner.py` 신규 (Sonnet 기반 Task DAG 분해, few-shot 5개, JSON 파싱/검증/fallback). `orchestrator.py`에 `PLANNER_ENABLED` feature flag 추가, true 시 백그라운드 shadow 실행(기존 경로 영향 0). 유닛 테스트 8/8 PASS (trivial/복합 DAG/fence stripping/JSON fail/cycle/unknown worker/LLM error/empty tasks) → [상세](docs/history/2026-04-20_Planner-Executor-Phase2.md)
- **추가** [Planner-Executor] 아키텍처 설계 + Phase 1 인프라 타입 — 현재 `orchestrator.py`의 "단일 Intent 라우터 + 1-hop HANDOFF" 구조를 진짜 오케스트레이션(계획/실행/합성 3분리)으로 업그레이드. Design doc + 인프라 타입(`Task`, `Plan`, `TaskStatus` dataclass, `Blackboard` 공유 저장소) 추가. 기존 경로 영향 없음 (pure additive, feature flag 이후 Phase에서 도입). → [설계](docs/history/2026-04-20_Planner-Executor-design.md) / [상세](docs/history/2026-04-20_Planner-Executor-Phase1.md)
- **수정** [OutlineWorker] Personal 컬렉션 본인 필터 `createdById` 버그 수정 — 본인 Personal 문서가 전부 "접근 권한 없음"으로 치환되던 진짜 원인. MCP 서버가 `createdBy`를 이름 문자열로 반환하는데 필터는 dict.get("id") 호출 → AttributeError → LangGraph ToolNode가 에러 메시지로 치환 → LLM에 44토큰 에러만 전달 → "문서 조회 오류" 응답. MCP 서버에 `createdById`(UUID) 필드 추가, 필터를 UUID 비교로 전환. 앞선 "안전 거절 회피 프롬프트" 커밋은 오진이었음(해롭지 않아 유지) → [상세](docs/history/2026-04-20_OutlineWorker-Personal-필터-createdById.md)
- **수정** [OutlineWorker] 본인 Personal 위키 문서 리포맷 거절 회피 — Sonnet이 `get_document`로 본인 Personal 문서(와이파이 비번·사내 계정 등 평문 크레덴셜 포함) 본문을 정상 수신하고도 안전 거절로 "문서 조회 오류" 위장 응답한다고 **오진**하여 시스템 프롬프트에 "거절 금지" 규칙 추가. 실제 원인은 필터 버그(위 항목)였으나 프롬프트 규칙은 안전망으로 유지 → [상세](docs/history/2026-04-20_OutlineWorker-Personal-리포맷.md)
- **수정** [MCP Adapter] 일시 실패 서버 지수 백오프 재시도 — Windows 프로세스 스폰 경쟁으로 `calendar_server, reservation_server` 등 다수 서버가 한꺼번에 transient fail → 도구 누락으로 CalendarWorker가 4개 도구만 받는 장애 발생. `_load_server_tools`에 `MAX_RETRY_ATTEMPTS=2` + `RETRY_BASE_DELAY=1.0s` 지수 백오프 재시도 추가. 영구 에러(`FileNotFoundError` 등)는 기존대로 블랙리스트 직행 → [상세](docs/history/2026-04-20_MCP-스폰-재시도.md)

---

## [2026-04-17]
- **추가** [AgentStore/Workspace/Inbox] AI Hub 격상 1차 FE 구현 — Agent Store 페이지(`/agent-store` + README 상세), Workspace 설정에 "Agents" 탭(P1 · localStorage 매핑), 헤더 알림 아이콘 3분할(📰 데일리 브리핑 / 🔔 알림함 드로어 / 📖 WIKI 외부링크), WhatsNew "새 기능"→"공지사항" 리브랜딩, capability 다중 태그 체계(💬⚡📅⏳) 확정 → [상세](docs/history/2026-04-17_AgentStore_Workspace_Inbox.md)
- **수정** [Frontend/Sidebar] 워크스페이스 컨텍스트 유지 — 워크스페이스 내 채팅 클릭 시 `/chat/[id]`로 이동하면서 `workspace_id` 쿼리가 사라져 사이드바가 전체 리스트로 되돌아가던 버그. `SidebarHistoryItem` Link에 workspace_id 쿼리 포함 + `Chat` 마운트 시 `replaceState`로 URL 동기화 → [상세](docs/history/2026-04-17_워크스페이스-컨텍스트-유지.md)
- **수정** [SAP RFC Bridge] 다중 시스템 지원 (DEV+PRD) — `SAPConnectionPool`을 시스템별 dict 구조로 전환, `.env`를 `SAP_DEV_*`/`SAP_PRD_*` 접두사 분리, `/rfc/call`·`/rfc/ping`·`/rfc/password-init`에 `system` 필드 추가, `reset_sap_password` MCP 도구와 ITSupportWorker 시스템 프롬프트에 dev/prd 선택 로직 반영, PRD IP 172.16.3.147로 보정 → [상세](docs/history/2026-04-17_SAP-RFC-Bridge-다중시스템.md)
- **수정** [PDF] `create_document_pdf` italic 폰트 미등록 버그 — `Undefined font: malgungothicI` 오류로 subtitle 포함 PDF 생성 실패 → MalgunGothic에 `I`/`BI` 스타일을 regular/bold로 폴백 등록, 2차 증상(LLM이 docx 성공에도 "전체 도구 오류" 오응답)도 함께 해소 → [상세](docs/history/2026-04-17_PDF-italic-font-fix.md)
- **수정** [IT VOC] 담당자 자동지정 직위 필터링 + 다중 부서 매핑 — `_get_dept_members()`에 `v_org_chart` JOIN, 직위 "파트장/책임"만 배정 (팀원/NULL 제외), `SYSTEM_CODE_TO_DEPT`(str) → `SYSTEM_CODE_TO_DEPTS`(tuple) 로 다중 부서 공동 담당 허용(예: 보안성 검토=보안기술팀+보안관리파트), `v_org_chart."직위"` 컬럼 추가(DBA) → [상세](docs/history/2026-04-17_VOC-담당자-직책-필터링.md)
- **추가** [Ops] NSSM 로그 수동 초기화 배치 — `C:\Services\logs\clear-logs.bat`, `Clear-Content` in-place truncate로 서비스 재시작 없이 `backend-blue/green.log` 및 error 로그 비움 (NSSM 로테이션 미설정 상태에서의 수동 운영 수단, `deploy.log` 제외)
- **수정** [Bedrock] 폴백 상태 영속화 — `_using_fallback`/`_restore_at`을 JSON 파일에 저장, 재시작(배포 포함) 후에도 KST 09:00 복구 예약 유지, Blue/Green 공용 경로 `C:/Services/LFChatbot_prod/shared/` 도입 → [상세](docs/history/2026-04-17_폴백-상태-영속화.md)
- **수정** [MCP] 동시 스폰 수 4개로 제한 — Windows 18개 서브프로세스 일괄 스폰 시 `ExceptionGroup` 경쟁 실패 방지, 세마포어 도입, MailWorker 등 메일 도구 누락 재발 방지 → [상세](docs/history/2026-04-17_MCP_concurrent_spawn_limit.md)

## [2026-04-14]
- **추가** [Widget] 그룹웨어 서비스 메뉴 플로팅 위젯 — 사번→조직 자동 판별, 조직별 메뉴 필터링, service_menu DB 테이블, 새 탭 SSO 이동 → [상세](docs/history/2026-04-14_그룹웨어-서비스-메뉴-위젯.md)
- **수정** [Fallback] Worker LLM 호출 us↔global inference profile 자동 전환 — throttling 시 prefix 전환 재시도, 모든 Bedrock 호출 경로에 적용 → [상세](docs/history/2026-04-14_Inference-Profile-자동-폴백.md)
- **추가** [Embed/GW] 그룹웨어 전용 embed 모드 — iframe 방식 위젯, groupware_embed 인텐트 필터링, GO.session() 사번 추출, userId useRef 안정화 → [상세](docs/history/2026-04-14_그룹웨어-전용-embed-모드.md)
- **수정** [Calendar] 캘린더 사용자별 SSO 인증 — 서비스 계정(wg0403) 대신 사용자 GOSSOcookie로 API 호출, 일정 등록/수정/삭제 권한 오류 해결, JSP에서 gosso 파라미터 전달 → [상세](docs/history/2026-04-14_캘린더-사용자별-SSO-인증.md)

## [2026-04-13]
- **추가** [Widget/nginx] 다우오피스 그룹웨어 플로팅 위젯 연동 — custom_index_header.jsp 활용, SSE 이벤트 매핑 수정, MutationObserver SPA 대응, 위젯 on/off 파일명 전환 운영 → [상세](docs/history/2026-04-13_그룹웨어-플로팅-위젯-연동.md)
- **추가** [ChromaDB] BM25+시멘틱 하이브리드 검색 도입 — Lot 번호/코드 검색 실패 해결, RRF 합산, BM25 캐시, 환경변수 가중치 조절 → [상세](docs/history/2026-04-13_하이브리드-검색-BM25-RRF.md)
- **수정** [OutlineSync] Webhook+청크 기반 동기화로 전면 개편 — 30분 폴링→Webhook 실시간, Haiku 요약→청크 분할(본문 전체 검색), asyncio.Queue 순차 처리(GPU OOM 해결), 4시간 폴백 delta sync → [상세](docs/history/2026-04-13_Outline-Webhook-청크-동기화.md)
- **수정** [IntentClassifier/BaseWorker] 시각화 과다 사용 억제 + PPT/XLSX 인텐트 오분류 방지 — 시각화 가이드 텍스트/마크다운 우선 원칙, PPT quick_classify 생성동사 필수화, LLM 프롬프트 문서생성 규칙 강화, 빈 파일 거짓 응답 방지 → [상세](docs/history/2026-04-13_시각화-인텐트-과다분류-수정.md)

## [2026-04-10]
- **수정** [Frontend+Backend] 이미지 공유 후 맥락 유실 수정 — message_history에 `[이미지 첨부됨]` 힌트 태그 추가 + 시스템 프롬프트에 이미지 맥락 유지 규칙 추가, AI가 이전 분석 결과를 활용하도록 유도 → [상세](docs/history/2026-04-10_이미지-맥락-유지-수정.md)

## [2026-04-08]
- **추가** [ITSupportWorker/RFC] SAP RFC Bridge + 패스워드 초기화 — Python 3.12 별도 마이크로서비스(sap-rfc-bridge)로 pyrfc 호환, Z02CMF_PASSWORD_INIT RFC 호출, login_id→사번 자동 변환, 사번 보안 주입 → [상세](docs/history/2026-04-08_SAP-RFC-Bridge-패스워드초기화.md)

## [2026-04-07]
- **수정** [IntentClassifier/DirectWorker] 워크스페이스 인텐트 오버라이드 제거 — `direct→user_files` 강제 전환 제거, DirectResponseWorker에 `search_workspace_docs` 공유 도구 추가, 워크스페이스 컨텍스트는 BaseWorker에서 모든 워커에 자동 주입 → [상세](docs/history/2026-04-07_워크스페이스-인텐트-오버라이드-제거.md)
- **추가** [설계] 화학물질 구매 검토 프로세스 자동화 — 전자결재 감지→MSDS 파싱→Outline 위키 자동 등록→검토→결재 기안 API 자동 상신, DB INSERT 0건/공식 API only → [상세](docs/화학물질_구매검토_자동화_설계.md)
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

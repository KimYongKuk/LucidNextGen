# CHANGELOG

## [2026-04-15] - 예약 item_id 할루시네이션 방지

- **수정** [ReservationMCP] get_daily_reservations 출력에 item_id 포함 — LLM이 정확한 회의실 ID 참조 가능 → [상세](../docs/history/2026-04-15_예약-item_id-할루시네이션-방지.md)
- **수정** [ReservationMCP] create_reservation 실행 전 item_id 유효성 검증 추가 — 존재하지 않는 ID 사전 차단
- **수정** [CalendarWorker] ReservationWorker를 CalendarWorker로 통합 — 일정+예약 크로스 도메인 요청 단일 워커 처리 → [상세](../docs/history/2026-04-15_캘린더-예약-워커-통합.md)

## [2026-04-14] - 공유 도구(PDF/DOCX/차트) BaseWorker 기본값 승격

- **수정** [BaseWorker] shared_tool_names 기본값을 빈 리스트에서 PDF/DOCX/차트 도구 포함으로 변경 — 모든 워커에서 문서 생성 가능 → [상세](../docs/history/2026-04-14_공유도구-BaseWorker-승격.md)
- **수정** [DirectResponseWorker] 시스템 프롬프트에 문서/차트 생성 도구 사용 지시 추가
- **수정** [XlsxWorker] 시스템 프롬프트에 공유 도구(PDF/DOCX) 안내 추가

## [2026-04-13] - AI 참조 스코프 필터링 (Outline Wiki 연동)

### feat(outline-worker): AI 참조 스코프 필터링 추가
- `_AI_REFERENCE_QUERY`: Official_Public 컬렉션 문서 + `ai_reference_documents` 테이블에 명시적 활성화된 문서(및 하위 문서)만 AI 참조 허용
- `_get_ai_referenceable_doc_ids()`: AI 참조 가능 문서 ID 캐시 조회 (TTL 5분)
- `_filter_result_by_ai_reference()`: 검색/조회 결과에서 AI 참조 비활성화 문서를 post-filter
- `search_documents`, `get_document`, `list_recent_documents`, `list_collection_documents` 도구에 AI 참조 필터 적용

### feat(outline-sync): ChromaDB 임베딩 AI 참조 스코프 적용
- `_is_ai_referenceable()`: 문서별 AI 참조 가능 여부 DB 체크 (Official_Public 소속 또는 ai_reference_documents 등록)
- `process_single_document()`에 AI 참조 체크 추가 — 참조 불가 문서는 ChromaDB에서 제거

### chore(env): OUTLINE_DATABASE_URL 환경변수 추가
- green, blue, 개발서버 `.env`에 `OUTLINE_DATABASE_URL` 추가
- `AI_REFERENCE_PUBLIC_COLLECTION` 환경변수 지원 (기본값: `Official_Public`)

# 2026-03-10 프롬프트 경량화 및 Agent Step 조정

## 개요
시스템 프롬프트 토큰 사용량을 줄이고, 과도하게 높은 max_agent_steps를 적정 수준으로 조정하여 비용 및 지연 시간을 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/metadata/MCP_GW_BOARD.md | 수정 | 214줄 → 97줄 압축 (SQL 예제 9→3개, 게시판 목록 축소) |
| backend/app/agents/workers/base_worker.py | 수정 | 날짜/cutoff 규칙 24줄 → 5줄 압축 |
| backend/app/agents/workers/xlsx_worker.py | 수정 | max_agent_steps 50 → 30 |
| backend/app/agents/workers/mail_worker.py | 수정 | max_agent_steps 30 → 24 |
| backend/metadata/MCP_GW_APPR.md | 수정 | 591줄 → 150줄 압축 (공통 컬럼 분리, FAQ 삭제, SQL 예제 축소) |
| backend/metadata/MCP_GW_WORKS_IT.md | 수정 | 217줄 → 93줄 압축 (SQL 예제 10→3개) |
| backend/metadata/MCP_GW_WORKS_ACCT.md | 수정 | 190줄 → 88줄 압축 (SQL 예제 12→3개) |
| backend/metadata/MCP_ORG_CHART.md | 수정 | 226줄 → 137줄 압축 (기본 예제 9→2개, 계층 쿼리 유지) |

## 상세 내용

### MCP_GW_BOARD.md 압축
- SQL 예제: 9개 → 3개 (키워드 검색, 기간 범위, 본문 상세 조회만 유지)
- 게시판 목록: 10행 표 → 포함/제외 2줄 요약
- 스키마: 불필요 컬럼(content_id, author_id, post_status 등) 제거
- 검색 중요도 별표 제거

### base_worker.py 날짜 규칙 압축
- 5개 절대 규칙 + 2개 금지 사항 + cutoff 대응 → 2줄 핵심 규칙으로 압축
- 의미 동일: 날짜 수정 금지, cutoff 질문 시 웹검색 안내

### max_agent_steps 조정
- xlsx: 50 → 30 (15회 도구 호출). 실 사용 패턴 분석 결과 25회 초과 사례 없음
- mail: 30 → 24 (12회 도구 호출). 목록 + 상세 5건 + 응답에 충분

## 결정 사항 및 주의점
- Board SQL 예제를 최소화했으나, LLM이 카테고리/작성자/말머리 검색을 유추할 수 있을 정도로 스키마 정보는 유지
- xlsx/mail에서 step 부족 에러 발생 시 값 상향 필요

### MCP_GW_APPR.md 압축 (591줄 → 150줄, -75%)
- 공통 컬럼(doc_id, title, form_name, drafted_at, doc_body) 상단에 한 번만 정의, 각 뷰에서 추가 컬럼만 기술
- "자주 묻는 질문 → 쿼리 매핑" 섹션 전체 삭제 (42줄) — LLM이 스키마에서 유추 가능
- SQL 예제: 뷰당 3-5개 → 1-2개로 축소 (가장 대표적인 패턴만 유지)
- 상태값 참고: 3개 표 → 인라인 텍스트로 압축
- 성능 주의사항: 3개 SQL 예제 → 1개로 축소
- 권한 범위: 12줄 → 3줄
- 컬럼 표를 markdown 테이블에서 콤마 구분 인라인 텍스트로 변환 (뷰 5-9)

### MCP_GW_WORKS_IT.md 압축 (217줄 → 93줄, -57%)
- SQL 예제: 10개 → 3개 (키워드, 시스템 필터+에러코드, 기간 검색만 유지)
- 보안 관련 Cases 4-9 전체 삭제 (동일 ILIKE 패턴)
- Cases 3-1~3-4 삭제, 날짜/범위/통계 패턴은 Case 3 아래 인라인 설명으로 대체
- 검색 중요도 별표, 이모지 제거

### MCP_GW_WORKS_ACCT.md 압축 (190줄 → 88줄, -54%)
- SQL 예제: 12개 → 3개 (키워드, 카테고리 필터, 기간 검색만 유지)
- Cases 2, 4-10, 12 삭제 (동일 ILIKE 패턴)
- 카테고리 표는 유지 (문의구분 필터에 필수)

### MCP_ORG_CHART.md 압축 (226줄 → 137줄, -39%)
- 기본 Cases 1-9 → 2개 (키워드, 집계)만 유지
- Cases 2-7, 9 삭제, 검색 패턴은 인라인 힌트로 대체
- 계층 조회 Cases 10-12 완전 보존 (Case 3-5로 번호 변경)
- 검색 중요도 별표 제거

### 요청별 토큰 사용량 추적 (신규)
- `base_worker.py`: `on_chat_model_end` 이벤트에서 `usage_metadata`의 input/output 토큰 수집
- 스트리밍 완료 후 `token_usage` 이벤트로 orchestrator → a2a_streaming에 전달
- `a2a_streaming.py`: `_internal_collected`에 `input_tokens`, `output_tokens`, `llm_call_count` 포함
- `chat.py`: `chat_log_new.metadata` JSON에 토큰 정보 저장
- 서버 로그에 실시간 출력: `[WorkerName] [TOKEN #N] in=X out=Y (cumul: ...)`
- SQL 조회: `JSON_EXTRACT(metadata, '$.input_tokens')` 등으로 워커별/일별 분석 가능

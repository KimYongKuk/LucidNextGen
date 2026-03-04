# 2026-02-24 Board Worker 모듈 (사내 게시판 검색)

## 개요

사내 게시판(다우오피스)의 게시글을 자연어로 검색하는 기능 추가. 기존 IT VOC 패턴(Generic SQL)을 따라 BoardWorker + MCP 서버를 구현. 전사/회사별 공개 게시판(43개, ~7,800건)만 대상이며, 사용자 인증(employee_number 주입)은 불필요.

**지원 시나리오:**
- 키워드 검색: "안전교육 관련 공지 찾아줘"
- 특정 게시판 조회: "전사 공지 최신글 보여줘"
- 카테고리/작성자/기간 검색: "이번 달 L&F 총무/복지에서 제휴 글 찾아줘"
- 본문 상세 조회(Step 2): "두 번째 글 내용 자세히 알려줘"

---

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/metadata/MCP_GW_BOARD.md` | **신규** | 스키마 가이드 (v_board_search + v_board_post_detail, 쿼리 템플릿) |
| `backend/app/mcp_servers/board_mcp_server.py` | **신규** | MCP 서버 (execute_board_query, 3단계 SQL 검증) |
| `backend/app/agents/workers/board_worker.py` | **신규** | BoardWorker (Sonnet, 스키마 프롬프트 주입) |
| `backend/app/agents/state.py` | 수정 | `Intent.BOARD` + `INTENT_TO_WORKER` 매핑 |
| `backend/app/agents/workers/__init__.py` | 수정 | BoardWorker 등록 |
| `backend/mcp_config.json` | 수정 | `board_server` 엔트리 |
| `backend/app/agents/intent_classifier.py` | 수정 | board 인텐트 정의 + quick_classify regex + 예시 |
| `backend/app/services/report_service.py` | 수정 | `"board": "게시판"` 라벨 |

---

## 1. MCP 서버 (`backend/app/mcp_servers/board_mcp_server.py`)

### 도구

| 도구명 | 파라미터 | 설명 |
|--------|----------|------|
| `execute_board_query` | `sql_query: str` | 게시판 SQL 실행 (SELECT만 허용) |

### SQL 검증 로직 (3단계)

1. **SELECT 전용**: `sql_query.strip().upper().startswith('SELECT')` 체크
2. **허용 대상**: `V_BOARD_SEARCH` 또는 `V_BOARD_POST_DETAIL` 포함 여부 확인
3. **위험 SQL 차단**: DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE 정규식 스캔

### 결과 포맷팅 (3가지 분기)

| 유형 | 판별 조건 | 출력 형식 |
|------|-----------|-----------|
| 본문 조회 | `post_body_text` 컬럼 존재 | 텍스트 (최대 3,000자) |
| 목록 검색 | `post_url` 컬럼 존재 | 번호 매기기 (제목, 게시판, 작성자, 날짜, URL) |
| 집계/통계 | 그 외 | 마크다운 테이블 |

### DB 연결
- PostgreSQL (TIMS DB): `192.168.100.5:5432/tims`
- asyncpg 연결 풀: `min_size=2, max_size=10, command_timeout=30`
- DB 사용자: `ai_reader` (읽기 전용)

---

## 2. BoardWorker (`backend/app/agents/workers/board_worker.py`)

### 클래스 구조

```
BoardWorker(BaseWorker)
├── name = "BoardWorker"
├── tool_names = ["execute_board_query"]
├── use_sonnet = True
└── system_prompt  ← 날짜 주입 + MCP_GW_BOARD.md 스키마 로드 + CONFIDENTIAL 래핑
```

### 특징
- **IT VOC 패턴 복제**: prepare_tools() / stream_response() 오버라이드 불필요
- **Sonnet 모델**: 다양한 SQL 생성 패턴(키워드/게시판/카테고리/작성자/기간/복합) 대응
- **스키마 캐싱**: `_board_schema_cache` 모듈 레벨 전역 변수, `_load_board_schema()` 1회 로드
- **CONFIDENTIAL 래핑**: 스키마를 사용자에게 노출하지 않음

### 시스템 프롬프트 주요 규칙
- 텍스트 응답 없이 즉시 도구 호출
- 목록 조회 시 `post_url` + `post_id` 필수 포함
- 0건 시 키워드 분리/범위 확대 후 1회 재검색
- 본문 조회(Step 2)는 사용자가 선택했을 때만

---

## 3. 스키마 가이드 (`backend/metadata/MCP_GW_BOARD.md`)

### 검색 대상

| 뷰/테이블 | 용도 | 주요 컬럼 |
|-----------|------|-----------|
| `v_board_search` | Step 1 목록 검색 | post_id, board_name, board_category, post_title, author_name, posted_at, post_url |
| `v_board_post_detail` | Step 2 본문 조회 | v_board_search 전체 + post_body_text, post_body_html, content_type |

### 검색 범위
- 전사 게시판 + 회사별 게시판만 (부서/커뮤니티 제외)
- 뷰 레벨 필터: `board_status = 'ACTIVE'`, `post_status = 'OPEN'`
- 약 7,800건, ILIKE 검색 ~32ms

### 쿼리 예제 (8가지 Case)
1. 키워드 검색 (`post_title ILIKE '%키워드%'`)
2. 특정 게시판 조회 (`board_name = '전사게시판'`)
3. 카테고리 기반 검색 (`board_name ILIKE '%IT%'`)
4. 작성자 기반 검색 (`author_name LIKE '%김명진%'`)
5. 기간 범위 검색 (`posted_at >= date_trunc(...)`)
6. 복합 검색 (카테고리 + 키워드 + 기간)
7. 카테고리 하위 게시판 (`board_category LIKE 'JHC%'`)
8. 본문 상세 조회 (`v_board_post_detail WHERE post_id = {post_id}`, post_body_text 평문)

---

## 4. 인텐트 분류

### quick_classify 규칙
- **환경변수**: `BOARD_WORKER_ENABLED` (기본값: `true`)
- **키워드 regex**: `게시판|공지사항|게시글|게시물|사내\s?공지|전사\s?공지|전사\s?게시`
- **워크스페이스 파일 존재 시**: LLM에게 위임 (기존 패턴 동일)

### LLM 분류 프롬프트
- 우선순위 5.5 (approval 다음, web_search 전)
- `corp_rag`와의 구분: 게시판 게시글 검색 → board, 사내 규정/정책 → corp_rag

---

## 5. 기존 패턴 비교

| 항목 | IT VOC | 전자결재 | **게시판** |
|------|--------|----------|-----------|
| MCP 도구 수 | 1 (execute_it_voc_query) | 2 (get_user_info + execute_query) | **1** (execute_board_query) |
| DB | PostgreSQL (TIMS) | PostgreSQL (TIMS) | **PostgreSQL (TIMS)** |
| 사용자 인증 | 불필요 | 필요 (사번 주입) | **불필요** |
| prepare_tools() | 기본 | 보안 래핑 | **기본** |
| stream_response() | 기본 | prefetch 오버라이드 | **기본** |
| 모델 | Sonnet | Sonnet | **Sonnet** |

---

## 6. 사이드 이펙트

**없음.** 변경 불필요 파일:
- `orchestrator.py` — 제네릭 라우팅 (`state.py` 매핑만으로 동작)
- `a2a_streaming.py` — 제네릭 이벤트 캡처
- `base_worker.py` — 제네릭 베이스 클래스
- `chat.py` — 사용자 인증 주입 불필요

---

## 7. 운영 참고

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `BOARD_WORKER_ENABLED` | `true` | 게시판 기능 on/off |

### 보안 설계
- Step 2 본문 조회: `go_post_contents` 테이블 직접 접근 대신 `v_board_post_detail` VIEW 사용
- `v_board_post_detail`은 `v_board_search` 기반이므로 공개 게시판(ACTIVE+OPEN)만 접근 가능
- `ai_reader` 사용자에게 3개 VIEW만 SELECT 권한 부여 (테이블 직접 접근 불가)

### 테스트 시나리오
```
"안전교육 관련 공지 찾아줘"         → 키워드 검색
"전사 공지 최신글 보여줘"           → 특정 게시판 조회
"이번 달 올라온 공지 보여줘"        → 기간 범위 검색
"두 번째 글 내용 자세히 알려줘"     → 본문 상세 조회 (Step 2)
```

# 2026-03-25 OutlineWorker 컬렉션 접근 제어

## 개요
OutlineWorker의 모든 읽기/쓰기 도구에 사용자별 컬렉션 접근 제어를 추가하여, 사용자가 Outline Wiki에서 본인이 접근 권한이 없는 컬렉션의 문서를 검색·조회·요약하지 못하도록 보안 경계를 강화했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/outline_worker.py` | 수정 | 컬렉션 접근 제어 모듈 추가, prepare_tools() 전면 개편 |

## 상세 내용

### 문제
- 기존에는 모든 Outline API 호출이 공유 서비스 계정 키(`OUTLINE_API_KEY`)로 이루어져, 챗봇 사용자 누구나 본인이 접근 권한이 없는 컬렉션의 문서도 검색·열람·요약 가능
- `extract_file_for_wiki`에만 `user_id` 기반 파일 접근 제어가 있었고, 읽기 도구에는 접근 제어가 전무

### 해결 방식: `extract_file_for_wiki` 패턴 확장
기존 파일 접근 제어 패턴(`prepare_tools()`에서 `user_id` 주입 → MCP 서버에서 범위 제한)을 모든 도구로 확장하되, MCP 서버 변경 없이 Worker 레벨에서 필터링.

### 구성 요소

#### 1. Outline PostgreSQL 연결
- `OUTLINE_DATABASE_URL` 환경변수로 활성화 (미설정 시 접근 제어 비활성화 — 하위 호환)
- `asyncpg` 연결 풀 (lazy init, min=1, max=3)

#### 2. 권한 조회 쿼리 (`_COLLECTION_ACCESS_QUERY`)
Outline DB 직접 조회로 사번(`empCode`) → 접근 가능 컬렉션 ID + 쓰기 권한 여부 반환.

**권한 판정 로직 (Outline 동일):**
- `admin` 역할 → 모든 컬렉션 접근/쓰기
- 팀 전체 공개 (`collection.permission IS NOT NULL`) + 게스트 아님
- `user_permissions` 테이블에 직접 멤버십
- `group_permissions` + `group_users`로 그룹 멤버십

**쓰기 권한 (`can_write`):**
- `admin` 역할 또는 `permission = 'read_write'` (팀/직접/그룹)

**대상 테이블:**
| Outline 모델 | 실제 테이블명 |
|-------------|-------------|
| UserMembership | `user_permissions` |
| GroupMembership | `group_permissions` |
| GroupUser | `group_users` |

#### 3. 캐시 전략
- `_collection_access_cache`: `emp_code → (readable_ids, writable_ids, timestamp)`
- TTL: 5분 (`_COLLECTION_CACHE_TTL = 300`)
- 비활성화 조건: `OUTLINE_DATABASE_URL` 미설정, `emp_code`가 빈 값/anonymous

#### 4. 도구별 접근 제어

| 도구 | 제어 방식 | 설명 |
|------|-----------|------|
| `list_collections` | post-filter | 접근 불가 컬렉션 제거, `your_permission` 필드 추가 |
| `search_documents` | pre-check + post-filter | 입력 collection_id 사전 차단 + 결과 collectionId 필터 |
| `list_recent_documents` | pre-check + post-filter | 동일 |
| `get_document` | post-filter | 응답의 collectionId 확인 후 차단 |
| `list_collection_documents` | pre-check | 입력 collection_id 사전 차단 |
| `create_wiki_document` | pre-check (쓰기) | writable 컬렉션만 허용 |
| `extract_file_for_wiki` | 기존 유지 | user_id 기반 파일 접근 제어 |
| `upload_image_to_outline` | 없음 | 스테이징 디렉토리 내 파일만 (기존 보안) |

#### 5. `_filter_result_by_access()` 함수
- JSON 결과 파싱 → 컬렉션 ID 기반 필터링 → ToolMessage 재생성
- `list_collections`: `your_permission` 필드 추가 (LLM이 문서 생성 시 쓰기 가능 컬렉션 안내)
- `get_document`: collectionId가 readable에 없으면 에러 반환 (본문 노출 차단)

## 환경변수
| 변수 | 설명 | 기본값 |
|------|------|--------|
| `OUTLINE_DATABASE_URL` | Outline PostgreSQL 연결 문자열 | (빈 값 — 접근 제어 비활성화) |

## 결정 사항 및 주의점
- **MCP 서버 미수정**: 접근 제어를 Worker의 `prepare_tools()` 래핑에서 처리 — MCP 서버에 파라미터 추가 불필요
- **하위 호환**: `OUTLINE_DATABASE_URL` 미설정 시 기존과 동일하게 동작 (필터링 없음)
- **Fail-open 정책**: DB 연결 실패 시 `None` 반환 → 필터링 스킵 (가용성 우선)
- **archived 컬렉션**: `archivedAt IS NULL` 조건으로 아카이브된 컬렉션 제외
- **캐시 TTL 5분**: 권한 변경이 즉시 반영되지 않음 (최대 5분 지연)

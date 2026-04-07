# 2026-03-19 L&F Wiki 연동 (OutlineWorker + Embed 페이지)

## 개요
L&F Wiki REST API를 연동하여 사내 위키 문서를 자연어로 검색/조회할 수 있는 OutlineWorker를 추가하고, L&F Wiki에 iframe으로 임베딩할 수 있는 `/embed` 채팅 페이지를 구현했다.

## 아키텍처

```
┌─────────────────────────────────────────────────┐
│  L&F Wiki (192.168.90.30:3003)              │
│  ┌─────────────────────────────────────────┐    │
│  │  Floating Widget (JS)                    │    │
│  │  ┌─────────────────────────────────┐     │    │
│  │  │  iframe: /embed                  │     │    │
│  │  │  ┌───────────────────────────┐   │     │    │
│  │  │  │  EmbedChat Component      │   │     │    │
│  │  │  │  chatMode: outline_embed  │   │     │    │
│  │  │  └───────────┬───────────────┘   │     │    │
│  │  └──────────────┼───────────────────┘     │    │
│  └─────────────────┼─────────▲───────────────┘    │
└────────────────────┼─────────┼────────────────────┘
                     │         │ postMessage
                     ▼         │ (lucid-navigate)
              ┌──────────┐    │
              │ FastAPI   │    │
              │ Backend   │    │
              └────┬──────┘
                   ▼
         ┌─────────────────┐
         │  Orchestrator    │
         │  outline_embed   │
         │  mode filter     │
         └────┬────────┬───┘
              │        │
    ┌─────────▼──┐  ┌──▼──────────────┐
    │ Direct     │  │ OutlineWorker   │
    │ Worker     │  │ (Sonnet)        │
    │ (인사/잡담) │  │                 │
    └────────────┘  └────┬────────────┘
                         │ MCP Tools
                         ▼
                  ┌──────────────┐
                  │ Outline MCP  │
                  │ Server       │
                  └──────┬───────┘
                         │ httpx
                         ▼
                  ┌──────────────┐
                  │ Outline API  │
                  │ REST (3003)  │
                  └──────────────┘
```

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/outline_server/server.py` | 신규 | Outline API MCP 서버 (5개 도구) |
| `backend/app/agents/workers/outline_worker.py` | 신규 | OutlineWorker (Sonnet, 토큰 압축) |
| `backend/app/agents/state.py` | 수정 | Intent.OUTLINE 추가, 매핑/설명 등록 |
| `backend/app/agents/intent_classifier.py` | 수정 | outline 인텐트 분류 (키워드 + LLM) |
| `backend/app/agents/orchestrator.py` | 수정 | outline_embed 모드 인텐트 강제 전환 |
| `backend/app/agents/workers/__init__.py` | 수정 | OutlineWorker 레지스트리 등록 |
| `backend/app/agents/workers/base_worker.py` | 수정 | outline_embed 시 HANDOFF 비활성화 |
| `backend/mcp_config.json` | 수정 | outline_server MCP 설정 추가 |
| `frontend/app/embed/page.tsx` | 신규 | Embed 메인 페이지 (postMessage 링크 처리) |
| `frontend/app/embed/layout.tsx` | 신규 | Embed 레이아웃 (DataStreamProvider) |
| `frontend/components/embed-chat.tsx` | 신규 | 경량 채팅 컴포넌트 (사이드바/모달 제거) |
| `frontend/middleware.ts` | 수정 | /embed 경로 인증 제외 |

## 상세 내용

### 1. MCP 서버 (outline_server/server.py)

- FastMCP 기반, stdio transport
- Outline REST API를 httpx로 호출 (Bearer 토큰 인증)
- DB 불필요 — HTTP API만 사용

#### MCP 도구 5개

| 도구 | Outline API | 용도 |
|------|------------|------|
| `search_documents` | `documents.search` | 키워드 문서 검색 (query, collection_id, date_filter) |
| `list_recent_documents` | `documents.list` | 최근 수정/생성 문서 목록 (sort, direction) |
| `get_document` | `documents.info` | 특정 문서 전체 내용 조회 (document_id) |
| `list_collections` | `collections.list` | 컬렉션(카테고리) 목록 |
| `list_collection_documents` | `collections.documents` | 컬렉션 내 문서 트리 (계층 구조 평탄화) |

### 2. OutlineWorker

- **Sonnet 모델** 사용 (문서 내용 종합/요약 품질)
- `compact_previous_results=True` (토큰 누적 방지)
- `compact_keep_recent_pairs=6` (최근 컨텍스트 보존)
- `max_agent_steps=24` (검색 → 다건 조회 → 종합 워크플로우)
- `prepare_tools()`에서 결과 truncation 래핑 (목록 16K, 문서 10K)

#### 바로가기 링크 생성

시스템 프롬프트에 `{outline_base_url}`을 런타임 치환하여 LLM이 위키 문서 링크를 자동 생성:

```
[문서 제목](http://192.168.90.30:3003/doc/slug-xxxxx)
```

### 3. 인텐트 분류 및 라우팅

#### Quick-Classify 키워드
`위키`, `wiki`, `outline`, `아웃라인`, `위키 문서`, `위키에서`

#### outline_embed 모드 (Orchestrator)

```python
if chat_mode == "outline_embed":
    if intent != Intent.DIRECT:
        intent = Intent.OUTLINE      # 모든 비-DIRECT → OUTLINE 강제
    else:
        if search_like_regex.match(message):
            intent = Intent.OUTLINE  # 검색성 DIRECT도 → OUTLINE
```

- **허용 워커**: OutlineWorker (위키 검색/조회) + DirectWorker (인사/잡담)
- **HANDOFF 비활성화**: `base_worker.py`에서 `chat_mode == "outline_embed"` 시 HANDOFF 지시 제거
- 메일, 결재, 웹검색, 엑셀 등 다른 워커로 절대 분기하지 않음

### 4. Embed 프론트엔드 (/embed)

L&F Wiki에 iframe으로 임베딩되는 경량 채팅 페이지.

#### 기존 채팅 대비 제거 항목

| 기능 | embed 모드 |
|------|-----------|
| 사이드바 | 제거 |
| 헤더/로고 | 제거 |
| 온보딩 모달 | 제거 |
| 검색 모달 (Cmd+K) | 제거 |
| 워크스페이스 선택 | 제거 |
| 예시 질문 카드 | 제거 |
| 파일 업로드 | 비활성화 |
| 마이크 입력 | 비활성화 |

#### 추가 기능

- **새 대화 버튼**: 사이드바 없이 세션 초기화 가능
- **postMessage 링크 처리**: Outline 내부 링크 클릭 시 부모 프레임으로 이동 요청

#### 링크 클릭 처리 (postMessage)

```
사용자가 위키 문서 링크 클릭
    ↓
/doc/xxx 또는 /collection/xxx 경로 감지
    ↓
e.preventDefault()
    ↓
window.parent.postMessage({ type: "lucid-navigate", url: "/doc/xxx" }, "*")
    ↓
Wiki 부모 JS가 수신 → SPA 라우팅 (대화 유지)
```

- **Outline 내부 링크**: postMessage로 부모 프레임에 전달 (SPA 라우팅, 대화 유지)
- **외부 링크**: `target="_blank"`로 새 탭에서 열기

#### 인증

- `middleware.ts`에서 `/embed` 경로를 인증 체크에서 제외
- 현재 인증 없이 접근 가능 (1단계)
- 향후 필요 시 `empno` 파라미터 + 암호화 토큰 방식 적용 가능

### 5. Wiki 쪽 요구사항 (플로팅 위젯 JS)

Wiki 에이전트가 구현해야 할 항목:

1. **postMessage 리스너**: `lucid-navigate` 타입 메시지 수신 → Outline SPA 라우터로 이동
2. **ESC 키 처리**: 부모 페이지에서 keydown 이벤트 → 위젯 닫기
3. **플로팅 버튼 위치**: 채팅 입력창과 겹치지 않도록 조정

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `OUTLINE_API_URL` | Outline API 엔드포인트 | `http://192.168.90.30:3003/api` |
| `OUTLINE_API_KEY` | Outline API 키 (서비스 계정) | (발급 필요) |
| `OUTLINE_WORKER_ENABLED` | 위키 기능 on/off | `true` |
| `OUTLINE_DOC_MAX_LENGTH` | 문서 본문 최대 길이 | `12000` |

## 권한 정책

- **1단계 (현재)**: 서비스 계정 API 키 1개 → 전체 컬렉션 열람
- **향후 확장**: 사용자별 Outline 토큰으로 부서별 접근 제어

## 결정 사항 및 주의점

- API 키 미설정 시 MCP 도구가 에러 메시지 반환 (서버 장애 아님)
- 문서 본문은 12,000자로 truncation (LLM 컨텍스트 효율)
- 검색 결과 최대 25건 제한 (API 부하 방지)
- `outline_embed` 모드에서 HANDOFF 비활성화 — 다른 워커로 분기 방지
- postMessage의 `type`은 `lucid-navigate`로 고정 — Wiki 쪽과 계약
- `window.location.href` 사용 시 SPA 리로드로 위젯 상태 소실 → `history.pushState` 필요 (Wiki 쪽)

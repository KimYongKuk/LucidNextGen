# Outline Wiki - LucidAI 연계 설계안

> 작성일: 2026-03-17
> 상태: 계획 단계

## 1. 배경 및 목적

### 현황
- **Outline Wiki**: 전 임직원 대상 사내 지식관리 서비스 (설계 중)
- **LucidAI 챗봇**: 사내 AI 챗봇 (운영 중) — 사내문서 RAG, VOC, 메일, 웹검색 등 통합
- 두 서비스 모두 사내 전용, 외부 반출 없음

### 목적
- 사용자 동선에 따라 **어디서든 AI + 지식에 접근** 가능하게 함
- 채팅에서 시작하는 사용자 → LucidAI에서 위키 검색
- 위키에서 시작하는 사용자 → Outline 내에서 AI 챗 활용

---

## 2. 연계 방향 (양방향)

```
┌─────────────────┐                    ┌─────────────────┐
│                 │   ① OutlineWorker  │                 │
│    LucidAI      │ ◀──── MCP ──────── │   Outline Wiki  │
│    (채팅)       │                    │   (지식관리)     │
│                 │ ──── Float Chat ──▶│                 │
│                 │   ② iframe 임베딩   │                 │
└─────────────────┘                    └─────────────────┘
```

| 방향 | 사용자 시나리오 | 구현 방식 |
|------|---------------|-----------|
| ① LucidAI → Outline | "위키에서 휴가 정책 찾아줘" | OutlineWorker + MCP Server |
| ② Outline → LucidAI | 위키 문서 보다가 AI에게 질문 | Float 챗 (iframe) |

---

## 3. 방향 ① — OutlineWorker (MCP Server)

### 3.1 아키텍처

```
사용자: "위키에서 보안 정책 관련 문서 찾아줘"
    ↓
[IntentClassifier] → Intent.WIKI
    ↓
[OutlineWorker] (Haiku)
    ↓
[OutlineMCPServer] ── HTTP ──▶ Outline REST API
    ↓
검색 결과 + 문서 내용 → 스트리밍 응답
```

### 3.2 MCP Server 도구 설계

| 도구명 | Outline API | 용도 |
|--------|-------------|------|
| `search_wiki` | `POST /api/documents.search` | 키워드/자연어 위키 검색 |
| `get_wiki_document` | `POST /api/documents.info` | 문서 전문 조회 (ID 기반) |
| `list_wiki_collections` | `POST /api/collections.list` | 컬렉션(카테고리) 목록 |
| `get_collection_documents` | `POST /api/collections.documents` | 특정 컬렉션 내 문서 목록 |

#### search_wiki (핵심 도구)

```python
@server.tool()
async def search_wiki(query: str, collection_id: str = None, limit: int = 10) -> str:
    """
    Outline 위키에서 문서를 검색합니다.
    - query: 검색어 (자연어 가능)
    - collection_id: 특정 컬렉션으로 범위 제한 (선택)
    - limit: 최대 결과 수
    """
    # POST /api/documents.search
    # 반환: 제목, 요약(context), 문서 ID, 컬렉션명
```

#### get_wiki_document

```python
@server.tool()
async def get_wiki_document(document_id: str) -> str:
    """
    문서 전문을 조회합니다. search_wiki 결과의 document_id를 사용합니다.
    """
    # POST /api/documents.info
    # 반환: 제목, 본문(Markdown), 최종 수정일, 작성자
    # 본문 길이 제한: 8,000자 (토큰 관리)
```

### 3.3 Worker 설계

```python
# backend/app/agents/workers/outline_worker.py

class OutlineWorker(BaseWorker):
    @property
    def name(self) -> str:
        return "outline_worker"

    @property
    def tool_names(self) -> list[str]:
        return ["search_wiki", "get_wiki_document",
                "list_wiki_collections", "get_collection_documents"]

    @property
    def use_sonnet(self) -> bool:
        return False  # Haiku — 검색/조회 위주

    @property
    def system_prompt(self) -> str:
        return """Outline 위키 검색 전문 에이전트입니다.
        - search_wiki로 먼저 검색하고, 필요하면 get_wiki_document로 상세 조회
        - 검색 결과를 요약하여 출처(문서 제목)와 함께 답변
        - 문서가 없으면 솔직히 "위키에 관련 문서가 없습니다" 안내
        """
```

### 3.4 Intent 분류

```python
# intent_classifier.py

class Intent(str, Enum):
    WIKI = "wiki"

# quick_classify 키워드
WIKI_KEYWORDS = r"위키|wiki|outline|사내규정|사내문서.*검색|지식.*베이스|KB"
```

> **CorpRAG vs Wiki 구분**: CorpRAG는 기존 관리자 업로드 문서(HR/AC/IT/안전), Wiki는 Outline에 임직원이 직접 작성한 지식 문서. 키워드로 대부분 구분 가능하며, 모호한 경우 LLM 분류기가 판단.

### 3.5 환경변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `OUTLINE_API_URL` | Outline 서버 주소 | `https://wiki.company.com` |
| `OUTLINE_API_KEY` | Outline API 키 (admin) | `ol_api_xxx...` |
| `OUTLINE_WORKER_ENABLED` | 기능 On/Off | `true` |

### 3.6 MCP 설정

```json
// mcp_config.json
{
  "outline_server": {
    "command": "python",
    "args": ["app/mcp_servers/outline_server.py"],
    "transport": "stdio"
  }
}
```

### 3.7 파일 구조

```
backend/app/
├── mcp_servers/
│   └── outline_server.py          # Outline MCP Server (FastMCP)
├── agents/workers/
│   └── outline_worker.py          # OutlineWorker
```

---

## 4. 방향 ② — Outline 내 Float 챗

### 4.1 개요

Outline 페이지 우하단에 Float 버튼을 배치하고, 클릭 시 LucidAI 채팅 UI를 iframe으로 표시.

### 4.2 구현 방식

Outline은 `CUSTOM_HTML` 환경변수 또는 Admin > Settings에서 커스텀 스크립트 삽입을 지원함.

```html
<!-- Outline CUSTOM_HTML에 삽입 -->
<div id="lucid-float-chat">
  <button id="lucid-float-btn" onclick="toggleLucidChat()">
    💬
  </button>
  <iframe
    id="lucid-chat-frame"
    src="https://lucid.company.com/chat/embed"
    style="display:none; width:400px; height:600px;"
  ></iframe>
</div>

<script>
function toggleLucidChat() {
  const frame = document.getElementById('lucid-chat-frame');
  frame.style.display = frame.style.display === 'none' ? 'block' : 'none';
}
</script>
```

### 4.3 고급 기능 (선택)

**현재 문서 컨텍스트 전달:**
- Outline 페이지 URL에서 문서 slug 추출
- iframe src에 query param으로 전달: `?context_doc=문서제목`
- LucidAI에서 해당 문서를 자동으로 불러와 "이 문서에 대해 질문" 모드 활성화

**인증 연동:**
- Outline SSO 세션에서 사번 추출 → iframe postMessage로 LucidAI에 전달
- 또는 공통 SSO (SAML/OIDC)로 양쪽 세션 통합

### 4.4 고려사항

| 항목 | 설명 |
|------|------|
| 인증 | 동일 도메인이면 쿠키 공유 가능, 다르면 postMessage + 토큰 방식 |
| 반응형 | 모바일에서 float 챗 크기 조절 필요 |
| CSP | Outline의 Content-Security-Policy에 LucidAI 도메인 추가 |
| 임베드용 UI | LucidAI에 `/chat/embed` 경로 — 사이드바 없는 경량 채팅 UI 필요 |

### 4.5 필요 작업 (LucidAI 측)

- `frontend/app/(chat)/chat/embed/page.tsx` — 임베드용 경량 채팅 페이지
- 사이드바/헤더 없이 채팅 영역만 렌더링
- query param으로 초기 컨텍스트 수신

---

## 5. 선택 사항 — ChromaDB 동기화

OutlineWorker와 별개로, Outline 문서를 ChromaDB에 주기적 동기화하면 **CorpRAGWorker에서도 위키 내용을 함께 검색**할 수 있음.

### 장단점

| 장점 | 단점 |
|------|------|
| 별도 인텐트 분류 없이 자연 통합 | 동기화 지연 (실시간 X) |
| 의미 검색(semantic) 가능 | 임베딩 비용 발생 |
| 기존 CorpRAG UI/UX 재활용 | 중복 저장 |

### 구현 시

```python
# backend/app/services/outline_sync_service.py

class OutlineSyncService:
    """Outline → ChromaDB 주기적 동기화"""

    async def sync_all(self):
        # 1. Outline API로 전체 문서 목록 조회
        # 2. 마지막 동기화 이후 변경된 문서만 필터
        # 3. Markdown → 청크 분할 → BGE-M3 임베딩
        # 4. ChromaDB admin 컬렉션에 upsert

    # APScheduler: 매 6시간마다 실행
```

> **판단**: OutlineWorker가 있으면 동기화는 필수는 아님. 사용자가 "사내 문서"라고 통칭할 때 위키까지 포함되길 원하면 동기화도 의미 있음. 우선순위는 낮음.

---

## 6. 구현 우선순위 및 일정

| 순서 | 작업 | 의존성 | 예상 규모 |
|------|------|--------|----------|
| **Phase 1** | OutlineMCPServer + OutlineWorker | Outline 서비스 배포 완료 | 파일 2개 + 설정 |
| **Phase 2** | IntentClassifier에 WIKI 추가 | Phase 1 | intent_classifier.py 수정 |
| **Phase 3** | Float 챗 임베드 UI | LucidAI embed 페이지 | 프론트엔드 1개 페이지 |
| **Phase 4** | Outline에 Float 스크립트 삽입 | Phase 3 + Outline 관리자 설정 | HTML/JS snippet |
| **Phase 5** | ChromaDB 동기화 (선택) | Phase 1 | 동기화 서비스 1개 |

---

## 7. 보안 고려사항

| 항목 | 방안 |
|------|------|
| **Outline API 키** | `.env`에 저장, admin 권한 (읽기 전용 용도) |
| **접근 제어** | Outline 자체 권한 체계 존중 — 비공개 문서는 API 결과에서 제외됨 (Outline 기본 동작) |
| **사번 주입** | Float 챗에서 SSO 세션 기반 자동 주입 (기존 LucidAI 방식) |
| **네트워크** | Outline ↔ LucidAI 간 통신은 사내망 내부 |
| **향후 외부 공개** | 특정 컬렉션만 외부 공개 시, OutlineWorker에서 `collection_id` 필터링 로직 추가 필요 |

---

## 8. 미결 사항

- [ ] Outline 서비스 배포 시점 확인
- [ ] Outline API 키 발급 방식 (admin key vs 서비스 계정)
- [ ] Outline 커스텀 스크립트 삽입 가능 여부 확인 (버전/설정 의존)
- [ ] 비공개 문서 접근 정책 — admin key는 모든 문서 접근 가능하므로, 사용자별 필터링 필요 여부
- [ ] Float 챗 인증 연동 방식 확정 (쿠키 공유 vs postMessage)
- [ ] CorpRAG와의 역할 구분 기준 최종 확정
- [ ] 향후 외부 읽기전용 공개 시 연계 영향 범위
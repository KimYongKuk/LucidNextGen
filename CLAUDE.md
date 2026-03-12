# LFChatbot - NextJS + FastAPI

## 프로젝트 개요
Lucid AI 챗봇 시스템으로, Next.js 프론트엔드와 FastAPI 백엔드로 구성된 전체스택 웹 애플리케이션입니다. AWS Bedrock을 활용한 AI 챗봇 서비스를 제공합니다.

## 기술 스택

### Frontend (Next.js)
- **프레임워크**: Next.js 15.4.2 with React 19.1.0
- **언어**: TypeScript
- **스타일링**: Tailwind CSS 3.4.15 with Tailwind CSS Animate
- **UI 컴포넌트**: Radix UI (Dialog, Dropdown Menu, Select, Separator, Slot, Tooltip)
- **애니메이션**: Framer Motion 12.23.6
- **아이콘**: Lucide React 0.525.0
- **AI 통합**: Vercel AI SDK 4.3.19
- **빌드 도구**: Turbopack 지원

### Backend (FastAPI)
- **프레임워크**: FastAPI 0.115.6 with Uvicorn 0.35.0
- **언어**: Python 3.x
- **데이터 검증**: Pydantic 2.11.9 with Pydantic Settings 2.7.0
- **LLM/AI**:
  - LangGraph 0.2.52 (Hierarchical Agent 아키텍처)
  - LangChain AWS 0.2.20, LangChain Core 0.3.80
  - AWS Bedrock via Boto3 1.39.4
- **MCP (Model Context Protocol)**:
  - MCP 1.22.0, FastMCP 2.13.1
  - LangChain MCP Adapters 0.1.14
- **벡터 데이터베이스**: ChromaDB 1.0.15 with Sentence Transformers 5.0.0
- **데이터베이스**: SQLAlchemy 2.0.36, PyMySQL 1.1.1, DBUtils 3.1.0 (Connection Pool)
- **문서 처리**: PyPDF2, python-docx, PyMuPDF, python-pptx, openpyxl
- **PDF/차트 생성**: fpdf2 2.8.3, matplotlib 3.9.0, pandas 2.2.0
- **웹 검색**: Tavily Python 0.7.10
- **기타**: python-dotenv, aiohttp, pycryptodome, apscheduler

## 프로젝트 구조

```
LFChatbot_NextJS_FastAPI/
├── frontend/                     # Next.js 프론트엔드
│   ├── app/                     # App Router (Next.js 13+)
│   │   ├── (auth)/              # 인증 관련 라우트
│   │   ├── (chat)/              # 채팅 관련 라우트
│   │   │   ├── api/             # API 라우트
│   │   │   │   ├── chat/        # 채팅 API
│   │   │   │   ├── history/     # 채팅 기록 API
│   │   │   │   └── suggestions/ # 제안 API
│   │   │   └── chat/[id]/       # 동적 채팅 페이지
│   │   ├── admin/               # 관리자 페이지
│   │   └── globals.css          # 글로벌 스타일
│   ├── components/              # 재사용 가능한 컴포넌트
│   │   ├── app-sidebar.tsx      # 사이드바
│   │   ├── chat.tsx             # 메인 채팅 컴포넌트
│   │   ├── message.tsx          # 메시지 컴포넌트
│   │   ├── multimodal-input.tsx # 입력 컴포넌트
│   │   ├── chart-display.tsx    # 차트 렌더링 (recharts)
│   │   ├── sidebar-workspaces.tsx  # 워크스페이스 사이드바
│   │   ├── sources-carousel.tsx    # 웹 검색 소스 캐러셀
│   │   ├── corp-sources-carousel.tsx # 사내 문서 소스 표시
│   │   ├── chat-search-modal.tsx   # 채팅 검색 모달
│   │   ├── youtube-modal.tsx       # YouTube 요약 모달
│   │   ├── onboarding/          # 온보딩 시스템
│   │   │   ├── onboarding-provider.tsx
│   │   │   ├── onboarding-modal.tsx
│   │   │   ├── onboarding-step.tsx
│   │   │   └── onboarding-progress.tsx
│   │   └── ui/                  # UI 기본 컴포넌트
│   ├── hooks/                   # React 훅
│   │   ├── use-simple-chat.ts   # 채팅 훅
│   │   └── use-debounce.ts      # 디바운스 훅
│   ├── lib/                     # 유틸리티
│   │   ├── ai/                  # AI 관련 유틸
│   │   ├── api/                 # API 클라이언트
│   │   │   ├── config.ts        # API URL 설정 (getApiUrl)
│   │   │   └── workspaces.ts    # 워크스페이스 API
│   │   ├── onboarding/          # 온보딩 설정
│   │   │   └── steps.ts         # 온보딩 단계 정의
│   │   └── types.ts             # 타입 정의
│   └── middleware.ts            # Next.js 미들웨어
│
├── backend/                      # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py              # FastAPI 앱 진입점
│   │   ├── api/                 # API 라우터
│   │   │   └── routes/
│   │   │       ├── auth.py      # 인증
│   │   │       ├── chat.py      # 채팅 (스트리밍)
│   │   │       ├── upload.py    # 파일 업로드
│   │   │       └── workspace.py # 워크스페이스
│   │   ├── adapters/            # 외부 서비스 어댑터
│   │   │   └── mcp_adapter.py   # MCP 서버 연결 어댑터
│   │   ├── agents/              # LangGraph Agent 시스템
│   │   │   ├── orchestrator.py  # 메인 오케스트레이터
│   │   │   ├── intent_classifier.py  # 인텐트 분류기
│   │   │   ├── state.py         # 상태 정의
│   │   │   ├── a2a_streaming.py # 스트리밍 로직
│   │   │   └── workers/         # 특화 Worker들
│   │   │       ├── base_worker.py
│   │   │       ├── direct_worker.py
│   │   │       ├── web_search_worker.py
│   │   │       ├── user_files_worker.py
│   │   │       ├── corp_rag_worker.py
│   │   │       ├── visualization_worker.py
│   │   │       ├── youtube_worker.py
│   │   │       ├── it_support_worker.py
│   │   │       ├── acct_support_worker.py
│   │   │       ├── mail_worker.py
│   │   │       └── url_fetch_worker.py
│   │   ├── core/                # 핵심 설정
│   │   │   ├── config.py        # 앱 설정
│   │   │   ├── database.py      # DB 연결 풀 (PooledDB)
│   │   │   └── model_config.py  # 모델 설정
│   │   ├── mcp_servers/         # MCP 도구 서버들
│   │   │   ├── pdf_generator/   # PDF 생성 MCP
│   │   │   │   └── server.py
│   │   │   ├── chart_generator/ # 차트 생성 MCP
│   │   │   │   └── server.py
│   │   │   ├── rag_server.py    # 사내 문서 RAG
│   │   │   ├── youtube_tool.py  # YouTube 요약
│   │   │   ├── works_it_mcp_server.py   # IT 지원 VOC
│   │   │   ├── works_acct_mcp_server.py # 회계 지원 VOC
│   │   │   └── mail_server/        # 메일 조회 MCP
│   │   │       └── server.py
│   │   ├── services/            # 비즈니스 로직
│   │   │   ├── bedrock_service.py       # AWS Bedrock 서비스
│   │   │   ├── chat_log_service.py      # 채팅 기록 관리 (MySQL)
│   │   │   ├── chromadb_service.py      # ChromaDB 관리
│   │   │   ├── memory_service.py        # 워크스페이스 메모리 (롤링 요약)
│   │   │   ├── pdf_vision_service.py    # PDF 비전 추출
│   │   │   ├── workspace_service.py     # 워크스페이스 관리
│   │   │   └── youtube_summary_service.py # YouTube 요약
│   │   └── utils/               # 유틸리티
│   ├── data/                    # 데이터 저장소
│   │   ├── chromadb_user/       # 사용자 업로드 벡터DB
│   │   ├── chromadb_admin/      # 관리자 문서 벡터DB
│   │   ├── pdf_output/          # 생성된 PDF 파일
│   │   └── chart_output/        # 생성된 차트 이미지
│   ├── migrations/              # DB 마이그레이션
│   │   ├── add_workspace_memory.sql  # 워크스페이스 메모리 테이블
│   │   └── change_workspace_id_to_uuid.sql  # workspace_id UUID 마이그레이션
│   ├── mcp_config.json          # MCP 서버 설정
│   └── requirements.txt         # Python 의존성
```

## 아키텍처

### LangGraph Hierarchical Agent 구조

```
사용자 요청
    ↓
[Orchestrator]
    ├── Phase 0: Workspace Memory 로드 (워크스페이스인 경우)
    ├── Phase 1: Intent Classification (Haiku - 빠른 분류)
    ↓
[Worker 선택 및 실행] (memory_context 전달)
    ├── DirectWorker: 일반 대화 (Sonnet)
    ├── WebSearchWorker: 웹 검색 (Tavily)
    ├── UserFilesWorker: 사용자 업로드 파일 검색
    ├── CorpRAGWorker: 사내 문서 검색
    ├── VisualizationWorker: PDF/차트 생성
    ├── YouTubeWorker: YouTube 요약
    ├── URLFetchWorker: URL 콘텐츠 추출 (뉴스, 블로그 등)
    ├── ITSupportWorker: IT VOC 검색
    ├── AcctSupportWorker: 회계 VOC 검색
    └── MailWorker: 사내 메일 조회
    ↓
[MCP Tools] (각 Worker가 필터링된 도구 사용)
    ↓
스트리밍 응답
    ↓
[백그라운드] 채팅 로그 저장 → 메모리 업데이트 트리거 (10메시지마다)
```

### MCP 서버 구성

| MCP 서버 | 도구 | 용도 |
|----------|------|------|
| tavily-mcp | tavily_search | 웹 검색 |
| fetch | fetch | 웹 페이지 콘텐츠 추출 |
| rag | search_hr/ac/it/safety_docs | 사내 문서 RAG |
| youtube | youtube_summarize | YouTube 요약 |
| works_it | search_it_voc, execute_it_voc_query | IT 지원 사례 |
| works_acct | search_acct_voc, execute_acct_voc_query | 회계 지원 사례 |
| pdf_generator | create_document_pdf, create_table_spec_pdf | PDF 생성 |
| chart_generator | create_line/bar/pie/multi_chart | 차트 생성 |
| mail_server | get_inbox/sent/unread_mail, search_mail, get_mail_folders, get_mail_detail | 메일 조회/요약/답장 |

### Worker별 담당 도구

| Worker | 도구 | 모델 |
|--------|------|------|
| DirectWorker | (없음) | Sonnet |
| WebSearchWorker | tavily_search | Haiku |
| UserFilesWorker | search_user_files, search_workspace_docs | Haiku |
| CorpRAGWorker | search_hr/ac/it/safety_docs | Haiku |
| VisualizationWorker | PDF 도구 + 차트 도구 | Sonnet |
| YouTubeWorker | youtube_summarize | Haiku |
| URLFetchWorker | fetch | Sonnet |
| ITSupportWorker | search_it_voc, execute_it_voc_query | Sonnet |
| AcctSupportWorker | search_acct_voc, execute_acct_voc_query | Sonnet |
| MailWorker | get_inbox/sent/unread_mail, search_mail, get_mail_folders, get_mail_detail | Sonnet |

## 주요 기능

### 1. AI 채팅 시스템
- AWS Bedrock (Claude 3.5 Sonnet/Haiku) 기반
- 스트리밍 전용 실시간 채팅
- 채팅 기록 관리 (MySQL)
- 모드별 분기:
  - **Normal 모드**: 일반 지식 + 사용자 파일 + 웹검색
  - **Corp 모드**: 사내 문서 검색 + 지원 VOC

### 2. 문서 처리 및 RAG
- PDF, DOCX, XLSX, PPTX, TXT 지원
- ChromaDB 벡터 데이터베이스
- Sentence Transformers (BGE-M3) 임베딩
- 워크스페이스별 문서 관리

### 3. 시각화 및 문서 생성
- **PDF 생성**: 마크다운 → PDF 변환 (기술 문서, 보고서)
- **차트 생성**:
  - 라인 차트 (트렌드)
  - 막대 차트 (비교)
  - 파이 차트 (비율)
  - 복합 차트 (막대+라인, 누적, 영역)

### 4. YouTube 요약
- 비디오 URL로 요약 생성
- 타임스탬프별 세그먼트
- 핵심 인사이트 추출

### 5. 웹 검색 통합
- Tavily API 기반 실시간 웹 검색
- 검색 결과 출처 표시 (소스 캐러셀 UI)

### 6. URL 콘텐츠 추출
- 웹 페이지 URL에서 콘텐츠 추출 및 요약
- 뉴스 기사, 블로그, GitHub 등 다양한 소스 지원
- mcp-server-fetch 기반 마크다운 변환

### 7. 워크스페이스 시스템
- 독립적 작업 공간 생성 (UUID 기반)
- 문서 업로드 및 벡터 검색 (ChromaDB `workspace_{uuid}` 컬렉션)
- 커스텀 시스템 프롬프트 설정
- 비동기 백그라운드 파일 업로드 (폴링 방식, 5분 타임아웃)
- **세션 보호**: 기존 workspace_id가 있는 세션은 덮어쓰기 방지 (COALESCE)
- **폴링 cleanup**: 컴포넌트 언마운트 시 자동 정리 (메모리 누수 방지)

### 8. 워크스페이스 메모리 시스템
워크스페이스 내 모든 세션의 대화 내용을 기억하는 롤링 요약 기반 장기 메모리 시스템.

**아키텍처:**
```
[사용자 요청] → [Orchestrator]
                    ↓
            workspace_id 확인
                    ↓
    [MemoryService.get_memory_context()]
                    ↓
    memory_context (요약 + 핵심사실)
                    ↓
        [Worker.build_system_prompt()]
                    ↓
    시스템 프롬프트에 메모리 주입
                    ↓
            [LLM 응답 생성]
                    ↓
        [백그라운드: 채팅 로그 저장]
                    ↓
    10개 메시지마다 롤링 요약 갱신 (Haiku)
```

**핵심 특징:**
- **롤링 요약 패턴**: 대화량과 무관하게 항상 고정 길이(~500자) 유지
- **핵심 사실 추출**: 사용자 선호도, 프로젝트 정보 등 최대 10개 유지
- **워크스페이스 범위**: 동일 워크스페이스 내 모든 세션에서 메모리 공유
- **비동기 업데이트**: 백그라운드에서 요약 갱신 (응답 지연 없음)
- **Haiku 모델 사용**: 비용 효율적인 요약 생성

**설정 상수 (memory_service.py):**
| 상수 | 값 | 설명 |
|------|-----|------|
| MEMORY_SUMMARY_THRESHOLD | 10 | N개 메시지마다 요약 업데이트 |
| MEMORY_SUMMARY_MAX_LENGTH | 500 | 요약 최대 길이 (자) |
| MEMORY_KEY_FACTS_LIMIT | 10 | 최대 핵심 사실 개수 |

**데이터베이스 테이블:**
```sql
CREATE TABLE workspace_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    workspace_id VARCHAR(36) NOT NULL,         -- UUID string
    user_id VARCHAR(50) NOT NULL,
    summary TEXT,                              -- 롤링 요약
    key_facts JSON,                            -- 핵심 사실 배열
    total_message_count INT DEFAULT 0,
    last_summary_message_count INT DEFAULT 0,
    last_summarized_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_workspace_user (workspace_id, user_id)
);
```

### 9. 온보딩 시스템
- 6단계 인터랙티브 가이드 (채팅, 파일업로드, 모드, PDF/차트, YouTube, 웹검색)
- LocalStorage 기반 완료 상태 추적
- 버전 관리로 업데이트 시 재표시
- Framer Motion 애니메이션

### 10. 채팅 검색
- Cmd+K 스타일 검색 모달
- 최근 7일 채팅 조회 / 검색어 기반 검색
- 검색어 하이라이팅

### 11. 메일 조회/요약/답장 초안
사용자의 사내 메일함을 자연어로 조회하고, 전체 본문 열람/요약/답장 초안 생성을 지원하는 기능.

**아키텍처:**
```
사번(user_id) → MailWorker 시스템 프롬프트에 사번 주입
→ LLM이 MCP 도구 호출 (employee_number=사번)
→ MCP 서버: PostgreSQL VIEW(v_mail_user_mapping) → message_store 경로
→ JSP 엔드포인트(lucid_mail.jsp) HTTP 호출 → 메일 JSON
→ (detail) SQLite full_path → .eml 파일 MIME 파싱 → 텍스트 본문
→ LLM이 자연어 응답/요약/답장 초안 생성
```

**지원 기능:**
- 받은편지함/보낸편지함 조회 (`get_inbox_mail`, `get_sent_mail`)
- 키워드 메일 검색 (`search_mail`)
- 안 읽은 메일 조회 (`get_unread_mail`)
- 메일함 목록 조회 (`get_mail_folders`)
- **메일 전체 본문 조회** (`get_mail_detail`) — .eml 파일 MIME 파싱
- **메일 요약** — LLM이 본문 기반 핵심 내용/요청 사항/액션 아이템 정리
- **답장 초안 생성** — LLM이 원본 기반 비즈니스 톤 답장 작성 (복사 사용)

**핵심 특징:**
- **보안**: 사번은 SSO 세션에서 자동 주입 (사용자 변경 불가)
- **성능**: message_store 경로 프로세스 수명 캐싱 (DB 조회 최소화)
- **On/Off**: `.env`의 `MAIL_WORKER_ENABLED=false`로 즉시 비활성화 가능
- **본문 조회**: .eml 파일 MIME 파싱 (QP/Base64, multipart 지원), 본문 8,000자 제한
- **답장 범위**: 초안 생성만 (실제 발송은 그룹웨어에서)

**PostgreSQL VIEW (DBA 생성 필요):**
```sql
CREATE VIEW v_mail_user_mapping AS
SELECT gu.employee_number, mu.message_store
FROM go_users gu
JOIN mail_user mu ON gu.login_id = mu.mail_uid
WHERE mu.message_store IS NOT NULL;

GRANT SELECT ON v_mail_user_mapping TO ai_reader;
```

**환경변수:**
| 변수 | 설명 |
|------|------|
| MAIL_API_KEY | JSP 엔드포인트 인증 키 |
| MAIL_API_URL | JSP 엔드포인트 URL |
| MAIL_WORKER_ENABLED | 메일 기능 on/off (true/false) |

## 개발 명령어

### Frontend
```bash
cd frontend
npm run dev          # 개발 서버 실행 (포트 3000)
npm run dev-turbo    # Turbopack으로 개발 서버 실행
npm run build        # 프로덕션 빌드
npm run start        # 프로덕션 서버 실행
npm run lint         # ESLint 실행
```

### Backend
```bash
cd backend
pip install -r requirements.txt  # 의존성 설치
python app/main.py               # 개발 서버 실행 (포트 8000)
start_server.bat                 # Windows용 서버 시작
```

## 환경 설정
- `.env` 파일을 통한 환경변수 관리
- AWS Bedrock 인증 정보 설정
- 데이터베이스 연결 정보 설정
- MCP 서버 설정 (`mcp_config.json`)

## 데이터베이스

### MySQL 연결 풀 (DBUtils.PooledDB)
- `database.py`에서 PooledDB를 사용한 연결 풀 관리
- 환경변수로 풀 크기 조정 가능:
  - `DB_POOL_MAX_CONNECTIONS`: 최대 연결 수 (기본값: 20)
  - `DB_POOL_MIN_CACHED`: 초기 유휴 연결 (기본값: 5)
  - `DB_POOL_MAX_CACHED`: 최대 유휴 연결 (기본값: 10)

### ChromaDB 데이터 보호
- 임베딩 모델 충돌 시 **자동 삭제 방지** (데이터 손실 방지)
- 모델 변경 시 수동 마이그레이션 필요 (관리자 확인 후 진행)

### 저장소 구성
- **ChromaDB**: 벡터 임베딩 저장 (사용자 업로드, 사내 문서)
- **MySQL**: 채팅 기록, 워크스페이스 메타데이터, 워크스페이스 메모리
- **SQLite**: ChromaDB 메타데이터

### MySQL 주요 테이블
| 테이블 | 용도 |
|--------|------|
| chat_sessions | 채팅 세션 메타데이터 |
| chat_log_new | 채팅 메시지 로그 |
| workspaces | 워크스페이스 정보 |
| workspace_memory | 워크스페이스별 롤링 요약 및 핵심 사실 |

## 배포
- Frontend: Vercel 또는 Next.js 호스팅 플랫폼
- Backend: FastAPI 서버 (Uvicorn)
- 데이터: ChromaDB 및 MySQL 인스턴스

## 자동 변경 이력 관리

코드 변경을 수반하는 작업 완료 시, 사용자가 별도로 요청하지 않아도 아래 두 파일을 자동으로 업데이트한다.

### docs/history/ (상세 기록)
- **유의미한 기능 추가/수정/삭제** 완료 시 `docs/history/YYYY-MM-DD_기능명.md` 파일을 생성 또는 업데이트한다.
- "유의미한 변경" 기준: 새 모듈/워커/API 추가, 기존 기능의 아키텍처 변경, 파일 3개 이상 수정, 중요한 버그 수정
- 사소한 변경(포맷팅, 주석, import 정리, 오타, 단일 파일 미세 수정)은 기록하지 않는다.
- 동일 날짜에 동일 기능 관련 변경이 누적되면, 기존 파일을 업데이트한다 (새 파일 생성 X).
- 템플릿:
  ```
  # YYYY-MM-DD 기능명

  ## 개요
  (1~2문장: 무엇을 왜 변경했는지)

  ## 변경 파일 요약
  | 파일 | 변경 유형 | 설명 |
  |------|-----------|------|

  ## 상세 내용
  (코드 구조, 동작 방식, 환경변수, 주요 함수/클래스 등 — 기능의 복잡도에 맞게 조절)

  ## 결정 사항 및 주의점
  (기술적 결정 이유, 알려진 제약, 향후 주의할 점)
  ```

### CHANGELOG.md (인덱스)
- docs/history/ 파일을 생성/업데이트할 때, `CHANGELOG.md`에도 해당 날짜의 한 줄 요약을 추가한다.
- 형식: `- **태그** [모듈명] 한 줄 설명 → [상세](docs/history/파일명.md)`
- 태그: **추가** (신규 기능/파일), **수정** (기존 변경), **삭제** (기능/파일 제거)
- docs/history/ 파일이 없는 사소한 변경도 한 줄 요약은 기록 가능 (링크 없이).

### 기록하지 않는 경우
- 포맷팅, 주석, import 정리, 오타 수정 등 기능 변경이 없는 경우
- 대화/질의응답만 진행하고 코드 변경이 없는 경우

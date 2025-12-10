# LFChatbot - NextJS + FastAPI

## 프로젝트 개요
LF(Lucid Fund) 챗봇 시스템으로, Next.js 프론트엔드와 FastAPI 백엔드로 구성된 전체스택 웹 애플리케이션입니다. AWS Bedrock을 활용한 AI 챗봇 서비스를 제공합니다.

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
- **프레임워크**: FastAPI 0.115.6 with Uvicorn 0.32.1
- **언어**: Python 3.x
- **데이터 검증**: Pydantic 2.11.0 with Pydantic Settings 2.7.0
- **LLM/AI**: 
  - LangChain 0.3.26 (AWS, Community, Core, Text Splitters, Chroma)
  - AWS Bedrock via Boto3 1.39.4
- **벡터 데이터베이스**: ChromaDB 1.0.15 with Sentence Transformers 5.0.0
- **데이터베이스**: 
  - SQLAlchemy 2.0.36
  - PyMySQL 1.1.1, MySQL Connector Python 9.3.0, MariaDB
- **자연어 SQL**: Vanna.ai with MySQL support
- **문서 처리**: PyPDF2, python-docx, PyMuPDF, openpyxl
- **인증**: Python-JOSE with Cryptography, Passlib with bcrypt
- **기타**: python-dotenv, fastapi-cors, structlog

## 프로젝트 구조

```
LFChatbot_NextJS_FastAPI/
├── frontend/                     # Next.js 프론트엔드
│   ├── src/
│   │   ├── app/                 # App Router
│   │   │   ├── globals.css      # 글로벌 스타일
│   │   │   ├── layout.tsx       # 루트 레이아웃
│   │   │   ├── page.tsx         # 메인 페이지
│   │   │   └── login/           # 로그인 페이지
│   │   ├── components/          # 재사용 가능한 컴포넌트
│   │   │   ├── app-sidebar.tsx  # 사이드바
│   │   │   ├── chat/            # 채팅 관련 컴포넌트
│   │   │   ├── greeting.tsx     # 인사말 컴포넌트
│   │   │   ├── header.tsx       # 헤더
│   │   │   ├── mode-selector.tsx # 모드 선택기
│   │   │   └── ui/              # UI 기본 컴포넌트
│   │   ├── hooks/               # React 훅
│   │   ├── lib/                 # 유틸리티 함수
│   │   └── middleware.ts        # Next.js 미들웨어
│   ├── public/                  # 정적 파일
│   ├── package.json
│   └── 설정 파일들 (next.config.ts, tailwind.config.ts, tsconfig.json)
│
├── backend/                      # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py              # FastAPI 앱 진입점
│   │   ├── api/                 # API 라우터
│   │   │   ├── api.py           # API 통합
│   │   │   └── routes/          # 라우트 정의
│   │   │       ├── auth.py      # 인증
│   │   │       ├── chat.py      # 채팅 (스트리밍 전용)
│   │   │       ├── upload.py    # 파일 업로드
│   │   │       ├── vanna_sql.py # SQL 자연어 처리
│   │   │       └── vector_db.py # 벡터 데이터베이스
│   │   ├── core/                # 핵심 설정
│   │   │   ├── config.py        # 앱 설정
│   │   │   └── database.py      # 데이터베이스 설정
│   │   ├── models/              # Pydantic 모델
│   │   ├── services/            # 비즈니스 로직
│   │   │   ├── bedrock_service.py       # AWS Bedrock 서비스
│   │   │   ├── chat_history_service.py  # 채팅 기록 관리 (MySQL)
│   │   │   ├── query_router.py          # 쿼리 라우팅 (Corp 모드)
│   │   │   ├── user_upload_service.py   # 사용자 파일 업로드 및 벡터 검색
│   │   │   ├── upload_embedding.py      # 임베딩 업로드
│   │   │   ├── vanna_service.py         # Vanna SQL 서비스
│   │   │   ├── vector_service.py        # 벡터 서비스 (사내 문서)
│   │   │   └── web_search_service.py    # 웹 검색
│   │   └── utils/               # 유틸리티
│   ├── data/                    # 데이터 저장소
│   │   ├── assets/              # 정적 자산
│   │   ├── chatdata/            # 채팅 데이터 (ChromaDB)
│   │   ├── chdata/              # 사내 문서 데이터
│   │   ├── user_upload_data/    # 사용자 업로드 (ChromaDB)
│   │   └── vanna_chromadb/      # Vanna ChromaDB
│   ├── temp_uploads/            # 임시 업로드 파일
│   ├── tests/                   # 테스트 코드
│   ├── archived_code/           # Deprecated 코드 (마이크로서비스 등)
│   ├── requirements.txt         # Python 의존성
│   └── start_server.bat         # 서버 시작 스크립트
```

## 아키텍처

### 단일 통합 백엔드 구조 (Windows)
ChromaDB 1.0.15가 Windows에서 **정상 작동**하므로, 마이크로서비스 없이 **단일 FastAPI 백엔드**로 통합되었습니다.

**주요 구성 요소:**
1. **Frontend (Next.js)** - 포트 3000
   - React 19 기반 UI
   - Vercel AI SDK를 통한 스트리밍 채팅
   - Tailwind CSS + Shadcn UI

2. **Backend (FastAPI)** - 포트 8000
   - 채팅 API (스트리밍 전용)
   - 파일 업로드 및 벡터 검색
   - AWS Bedrock 통합
   - ChromaDB 직접 관리
   - MySQL 채팅 이력 저장

**기술 스택:**
- ChromaDB 1.0.15 (Windows 네이티브)
- Sentence Transformers (BGE-M3)
- LangChain (문서 처리, 청킹)
- AWS Bedrock (Claude 3.5 Sonnet)
- Vanna.ai (자연어 SQL)

## 주요 기능

### 1. AI 채팅 시스템
- AWS Bedrock을 통한 LLM 통합
- **스트리밍 전용** 실시간 채팅 인터페이스
- 채팅 기록 관리 및 저장 (MySQL)
- 모드별 분기 처리:
  - **Normal 모드**: 일반 지식 + 사용자 파일 + 웹검색
  - **Corp 모드**: 사내 문서 검색 + DB 쿼리

### 2. 문서 처리 및 임베딩
- PDF, DOCX, XLSX, TXT 문서 형식 지원
- ChromaDB를 활용한 벡터 데이터베이스
- Sentence Transformers (BGE-M3) 임베딩
- **마이크로서비스 기반** 사용자 업로드 문서 처리

### 3. 자연어 SQL 쿼리
- Vanna.ai를 활용한 자연어-SQL 변환
- MySQL/MariaDB 연동
- `[DB]` 접두사로 DB 쿼리 모드 활성화

### 4. 인증 및 보안
- JWT 기반 인증 시스템
- CORS 설정
- 보안 헤더 및 미들웨어

### 5. 웹 검색 통합
- 키워드 기반 자동 웹검색 트리거
- 검색 결과를 컨텍스트에 통합
- 최신 정보 제공

## 개발 명령어

### Frontend
```bash
cd frontend
npm run dev          # 개발 서버 실행
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

**참고:** ChromaDB 1.0.15는 Windows에서 정상 작동하므로 별도의 마이크로서비스가 필요 없습니다.

## 환경 설정
- `.env` 파일을 통한 환경변수 관리
- AWS Bedrock 인증 정보 설정
- 데이터베이스 연결 정보 설정
- ChromaDB 데이터 경로 설정

## 데이터베이스
- **ChromaDB**: 벡터 임베딩 저장 (채팅, 사용자 업로드, Vanna용)
- **MySQL/MariaDB**: 관계형 데이터 저장
- **SQLite**: ChromaDB 메타데이터 저장

## 테스트
- Backend: pytest를 활용한 단위 테스트 및 통합 테스트
- 테스트 코드 위치: `backend/tests/`
- API 엔드포인트, 채팅 로직, 웹 검색, ChromaDB 통합 테스트 포함
- 마이크로서비스 연결 테스트 포함

**테스트 실행:**
```bash
cd backend
pytest tests/ -v
```

## 배포
- Frontend: Vercel 또는 다른 Next.js 호스팅 플랫폼
- Backend: FastAPI 서버 (Uvicorn)
- 데이터: ChromaDB 및 MySQL/MariaDB 인스턴스
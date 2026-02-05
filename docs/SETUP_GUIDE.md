# LFChatbot 셋업 가이드

새 PC에서 프로젝트를 clone 받은 후 필요한 설정 가이드입니다.

## 1. 기본 환경 설치

### 필수 소프트웨어

| 소프트웨어 | 버전 | 용도 |
|-----------|------|------|
| Python | 3.11+ | Backend 런타임 |
| Node.js | 18+ | Frontend 런타임 |
| MySQL | 8.0+ | 데이터베이스 |
| Git | 최신 | 버전 관리 |

---

## 2. Backend 설정

### 2.1 가상환경 및 의존성

```bash
cd backend

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2.2 환경변수 설정

```bash
# .env 파일 생성
copy .env.example .env   # Windows
cp .env.example .env     # Mac/Linux
```

**.env 파일 수정:**

```env
# AWS Bedrock (필수 - Claude LLM 사용)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# MySQL (필수)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=chatbot_db

# CORS (Frontend 주소)
ALLOWED_ORIGINS=http://localhost:3000
```

### 2.3 MCP 서버 설정

```bash
# mcp_config.json 생성
copy mcp_config.example.json mcp_config.json   # Windows
cp mcp_config.example.json mcp_config.json     # Mac/Linux
```

**mcp_config.json에서 API 키 설정:**

```json
{
  "mcpServers": {
    "tavily-mcp": {
      "env": {
        "TAVILY_API_KEY": "실제_TAVILY_API_키"
      }
    },
    "perplexity": {
      "env": {
        "PERPLEXITY_API_KEY": "실제_PERPLEXITY_API_키"
      },
      "enabled": false  // 선택사항, 필요시 true로 변경
    }
  }
}
```

---

## 3. Frontend 설정

### 3.1 의존성 설치

```bash
cd frontend

# npm 사용
npm install

# 또는 pnpm 사용
pnpm install
```

### 3.2 환경변수 설정

```bash
# .env.local 파일 생성
copy .env.example .env.local   # Windows
cp .env.example .env.local     # Mac/Linux
```

**.env.local 파일 수정:**

```env
# 인증 시크릿 (필수) - 32자 이상 랜덤 문자열
# 생성: https://generate-secret.vercel.app/32
AUTH_SECRET=your_random_secret_key_here

# 아래는 로컬 개발시 선택사항 (Vercel 배포시 필요)
# AI_GATEWAY_API_KEY=
# BLOB_READ_WRITE_TOKEN=
# POSTGRES_URL=
# REDIS_URL=
```

---

## 4. 데이터베이스 초기화

### 4.1 MySQL 데이터베이스 생성

```sql
-- MySQL에 접속하여 실행
CREATE DATABASE chatbot_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 4.2 마이그레이션 실행

```bash
cd backend

# 기본 마이그레이션
python run_migration.py

# YouTube 요약 테이블
python migrations/add_youtube_summaries.py

# (선택) 피드백 테이블 - SQL 직접 실행
mysql -u root -p chatbot_db < migrations/create_anonymous_feedback.sql
```

---

## 5. 실행

### 개발 서버 실행

```bash
# 터미널 1: Backend
cd backend
python app/main.py
# → http://localhost:8000

# 터미널 2: Frontend
cd frontend
npm run dev
# → http://localhost:3000
```

### 접속 확인

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs (Swagger UI)

---

## 6. 필요한 API 키 목록

| 서비스 | 환경변수 | 필수 여부 | 용도 |
|--------|----------|-----------|------|
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | **필수** | Claude LLM |
| Tavily | `TAVILY_API_KEY` (mcp_config.json) | **필수** | 웹 검색 |
| Perplexity | `PERPLEXITY_API_KEY` (mcp_config.json) | 선택 | 웹 검색 대안 |

---

## 7. 폴더 구조 (자동 생성됨)

다음 폴더들은 런타임에 자동 생성되며 `.gitignore`에 포함되어 있습니다:

```
backend/
├── data/
│   ├── chromadb_user/    # 사용자 업로드 벡터DB
│   ├── chromadb_admin/   # 관리자 문서 벡터DB
│   ├── pdf_output/       # 생성된 PDF 파일
│   └── chart_output/     # 생성된 차트 이미지
└── venv/                 # Python 가상환경
```

---

## 8. 트러블슈팅

### ChromaDB 오류

```bash
# SQLite 버전 문제 발생시
pip install pysqlite3-binary
```

### Node.js 메모리 오류

```bash
# 환경변수 설정
set NODE_OPTIONS=--max-old-space-size=4096   # Windows
export NODE_OPTIONS=--max-old-space-size=4096  # Mac/Linux
```

### AWS Bedrock 인증 오류

- AWS CLI 설치 및 `aws configure` 실행
- 또는 `.env`에 직접 자격증명 설정

---

## 9. 추가 문서

- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - DB 스키마 정의
- [CLAUDE.md](../CLAUDE.md) - 프로젝트 전체 구조
- [ARCHITECTURE.md](../ARCHITECTURE.md) - 아키텍처 설명

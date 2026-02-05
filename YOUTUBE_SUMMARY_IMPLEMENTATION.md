# 유튜브 요약 기능 구현 완료

## 📋 구현 개요

사용자가 채팅 중 유튜브 링크를 전달하면, LangGraph Agent가 자동으로 `youtube_summarize` 도구를 호출하여 n8n webhook을 통해 비디오 요약을 받아옵니다. 요약 결과는 MariaDB에 저장되어 캐싱되며, 프론트엔드 모달로 표시됩니다.

## ✅ 구현 완료 항목

### 백엔드 (Phase 1)

1. **DB 마이그레이션** ✓
   - [backend/migrations/add_youtube_summaries.py](backend/migrations/add_youtube_summaries.py)
   - `youtube_summaries` 테이블 생성
   - video_id (UNIQUE), title, summary, insight, keywords, segments (JSON)

2. **YouTube Summary Service** ✓
   - [backend/app/services/youtube_summary_service.py](backend/app/services/youtube_summary_service.py)
   - URL 파싱 (video_id 추출)
   - n8n webhook 호출 (15초 타임아웃)
   - MariaDB CRUD 작업
   - 캐싱 로직 (중복 요청 방지)

3. **YouTube Tool (MCP Server)** ✓
   - [backend/app/mcp_servers/youtube_tool.py](backend/app/mcp_servers/youtube_tool.py)
   - FastMCP 기반 도구 구현
   - LangGraph Agent와 통합

4. **MCP Config 등록** ✓
   - [backend/mcp_config.json](backend/mcp_config.json)
   - "youtube" 서버 추가

5. **Chat Route 수정** ✓
   - [backend/app/api/routes/chat.py](backend/app/api/routes/chat.py)
   - `youtube_summary` 메타데이터 수집
   - SSE 스트리밍으로 프론트엔드에 전송
   - DB 저장 시 메타데이터 포함

6. **환경 변수** ✓
   - [backend/.env](backend/.env)
   - `N8N_YOUTUBE_WEBHOOK_URL=http://localhost:5678/webhook/youtube-summary`
   - `N8N_WEBHOOK_TIMEOUT=15`

### 프론트엔드 (Phase 2)

7. **타입 정의** ✓
   - [frontend/lib/types.ts](frontend/lib/types.ts)
   - `YoutubeSummary`, `YoutubeSegment` 인터페이스
   - `CustomUIDataTypes`에 `youtube-summary` 추가

8. **YouTube Summary Modal** ✓
   - [frontend/components/youtube-summary-modal.tsx](frontend/components/youtube-summary-modal.tsx)
   - Key Insight, Summary, Video Segments 표시
   - 타임스탬프 클릭 시 유튜브로 이동 (t=초)
   - Radix UI Dialog 사용

9. **Message 컴포넌트** ✓
   - [frontend/components/message.tsx](frontend/components/message.tsx)
   - `youtube-summary` 타입 렌더링
   - 클릭 시 모달 오픈

10. **Chat Hook** ✓
    - [frontend/hooks/use-simple-chat.ts](frontend/hooks/use-simple-chat.ts)
    - `youtube_summary` 이벤트 처리
    - 스트리밍 중 실시간 업데이트
    - 완료 후 최종 메시지에 포함

## 🔄 데이터 플로우

```
1. 사용자: "이 영상 요약해줘 https://youtu.be/l_rCh7mc_ZE"
2. LangGraph Agent: youtube_summarize 도구 호출
3. YouTube Summary Service:
   - DB 캐시 확인 (video_id로 조회)
   - 캐시 미스 → n8n webhook 호출
   - n8n 응답 수신 (10초 이내)
   - MariaDB에 저장
   - 결과 반환
4. Chat Route:
   - Tool 결과를 파싱
   - SSE로 프론트엔드에 스트리밍
   - DB에 메타데이터 저장
5. Frontend:
   - `youtube_summary` 이벤트 수신
   - 메시지에 youtube-summary part 추가
   - 클릭 시 모달 오픈

```

## 📊 데이터베이스 스키마

```sql
CREATE TABLE youtube_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    video_id VARCHAR(20) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    original_link VARCHAR(500) NOT NULL,
    summary TEXT NOT NULL,
    insight TEXT,
    keywords JSON,
    segments JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    user_id VARCHAR(100),

    INDEX idx_video_id (video_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);
```

## 🔧 n8n Webhook 규격

**Endpoint**: `POST http://localhost:5678/webhook/youtube-summary`

**Request**:
```json
{
  "video_id": "l_rCh7mc_ZE",
  "url": "https://youtu.be/l_rCh7mc_ZE"
}
```

**Response**:
```json
{
  "title": "과일·채소·식품 안전 관리...",
  "original_link": "https://youtu.be/l_rCh7mc_ZE",
  "video_id": "l_rCh7mc_ZE",
  "summary": "고려대 이광일 교수가...",
  "insight": "과학적 근거에 기반한...",
  "keywords": ["농약 제거", "곰팡이 감염", ...],
  "segments": [
    {
      "start_time": 0,
      "title": "과일 농약 제거 방법",
      "content": "농약은 과일 꼭지 부분에 집중됨..."
    }
  ]
}
```

## 🚀 테스트 가이드

### 1. 시작 전 체크리스트
- [ ] n8n 서버가 `http://localhost:5678`에서 실행 중
- [ ] n8n webhook 엔드포인트 `/webhook/youtube-summary` 생성 완료
- [ ] MariaDB 서버 실행 중
- [ ] 백엔드 `.env` 파일에 n8n URL 설정 확인

### 2. 백엔드 서버 재시작
```bash
cd backend
python app/main.py
```

**확인사항**:
- MCP Adapter 초기화 성공
- `youtube` 도구가 로드되었는지 확인

### 3. 기본 테스트

#### 테스트 1: n8n Webhook 수동 테스트
```bash
curl -X POST http://localhost:5678/webhook/youtube-summary \
  -H "Content-Type: application/json" \
  -d '{"video_id": "l_rCh7mc_ZE", "url": "https://youtu.be/l_rCh7mc_ZE"}'
```

**예상 결과**: JSON 응답 (제목, 요약, 키워드, 세그먼트)

#### 테스트 2: 챗봇에서 유튜브 링크 전송
1. 프론트엔드 접속
2. 채팅 입력: `이 영상 요약해줘 https://youtu.be/l_rCh7mc_ZE`
3. Agent가 `youtube_summarize` 도구 호출
4. 요약 카드 표시 확인
5. 카드 클릭 → 모달 오픈 확인

#### 테스트 3: 캐싱 동작 확인
1. 같은 비디오 URL로 다시 요청
2. 콘솔에 `[CACHE HIT]` 로그 확인
3. 즉시 응답 (n8n 호출 없음)

#### 테스트 4: DB 저장 확인
```sql
SELECT * FROM youtube_summaries ORDER BY created_at DESC LIMIT 1;
```

### 4. 에러 시나리오 테스트

#### 테스트 5: 잘못된 URL
- 입력: `요약해줘 https://invalid-url.com`
- 예상: 에러 메시지 "유효하지 않은 유튜브 URL입니다"

#### 테스트 6: n8n 서버 다운
- n8n 중지 후 요청
- 예상: 타임아웃 에러 메시지

## 📝 주요 파일 목록

### 생성된 파일
1. `backend/migrations/add_youtube_summaries.py`
2. `backend/app/services/youtube_summary_service.py`
3. `backend/app/mcp_servers/youtube_tool.py`
4. `frontend/components/youtube-summary-modal.tsx`

### 수정된 파일
1. `backend/mcp_config.json`
2. `backend/app/api/routes/chat.py`
3. `backend/.env`
4. `frontend/lib/types.ts`
5. `frontend/components/message.tsx`
6. `frontend/hooks/use-simple-chat.ts`

## 🎨 UI 특징

### 요약 카드 (Message)
- 파란색 테두리 박스
- 비디오 아이콘
- 제목 표시 (2줄 제한)
- "클릭하여 자세히 보기" 안내

### 요약 모달 (Dialog)
1. **헤더**: 비디오 제목 + 유튜브 링크
2. **키워드**: 태그 형태로 표시 (#농약제거, #곰팡이감염)
3. **Key Insight**: 노란색 강조 박스
4. **SUMMARY**: 회색 박스, 전체 요약
5. **VIDEO SEGMENTS**:
   - 타임스탬프 버튼 (클릭 시 유튜브로 이동)
   - 세그먼트 제목 + 내용

## 🔒 보안 고려사항

1. **URL 검증**: 유튜브 도메인만 허용
2. **SQL Injection 방지**: Parameterized Query 사용
3. **Rate Limiting**: 필요시 사용자당 분당 요청 제한 추가 권장
4. **n8n Webhook 인증**: 필요시 토큰 인증 추가 권장

## 🚀 향후 확장 가능성

1. **캐시 만료 정책**: 오래된 요약 재생성
2. **사용자별 요약 이력**: 조회 페이지 추가
3. **북마크 기능**: 중요한 요약 저장
4. **공유 기능**: 다른 사용자와 요약 공유
5. **ChromaDB 통합**: 요약을 임베딩하여 RAG 컨텍스트로 활용

## 📞 문제 해결

### 문제 1: MCP Adapter가 youtube 도구를 로드하지 못함
**해결**: 백엔드 서버 재시작, `mcp_config.json` 문법 오류 확인

### 문제 2: n8n webhook 호출 실패
**해결**: n8n 서버 실행 확인, `.env`의 URL 확인, 방화벽 확인

### 문제 3: 모달이 열리지 않음
**해결**: 브라우저 콘솔 확인, `youtube-summary` 타입 데이터 수신 여부 확인

### 문제 4: DB 저장 실패
**해결**: MariaDB 서버 확인, 테이블 존재 여부 확인, 권한 확인

## ✨ 완료 상태

모든 구현이 완료되었습니다! 🎉

- ✅ 백엔드: DB, Service, Tool, MCP Config, Chat Route
- ✅ 프론트엔드: 타입, 모달, 메시지 렌더링, Hook
- ✅ 환경 설정: .env 추가
- ✅ 문서: 구현 가이드 작성

다음 단계: n8n webhook 구현 후 통합 테스트 진행

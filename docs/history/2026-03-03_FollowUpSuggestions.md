# 2026-03-03 팔로우업 제안 (Follow-Up Suggestions)

## 개요
AI 응답 완료 후, 맥락에 맞는 후속 질문 3개를 입력창 위에 수평 칩 형태로 제안하는 기능 추가. Worker별 능력 메뉴 기반으로 LLM이 구체적/실행 가능한 제안을 생성한다.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/base_worker.py` | 수정 | WORKER_FOLLOW_UP_CAPABILITIES 딕셔너리 + 팔로우업 프롬프트 추가 |
| `backend/app/agents/a2a_streaming.py` | 수정 | HTML 마커 파싱, `follow_up_suggestions` SSE 이벤트 emit, DB 텍스트 마커 strip |
| `frontend/hooks/use-simple-chat.ts` | 수정 | SSE 이벤트 수집, `followUpSuggestions` 상태, 마커 strip, 항상 finalParts 구성 |
| `frontend/components/follow-up-suggestions.tsx` | 추가 | 수평 칩 UI (Suggestion 재사용, AnimatePresence) |
| `frontend/components/chat.tsx` | 수정 | sticky 영역 flex-col 변경, FollowUpSuggestions 렌더링 |

## 상세 내용

### 아키텍처
```
Worker system prompt에 팔로우업 지시 + 능력 메뉴
    ↓
LLM이 응답 끝에 <!--FOLLOW_UP:["s1","s2","s3"]--> 마커 포함
    ↓
a2a_streaming.py: regex 파싱 → SSE 이벤트 전송 + DB 텍스트에서 마커 제거
    ↓
use-simple-chat.ts: SSE 수집 → followUpSuggestions state
    ↓
chat.tsx: 입력창 위 플로팅 칩 (status=ready && !input.trim())
```

### Worker별 능력 메뉴 (WORKER_FOLLOW_UP_CAPABILITIES)
각 Worker에 3가지 카테고리 정의:
- **Deepen**: 같은 Worker로 주제 심화
- **Transform**: 다른 Worker로 산출물 변환 (PDF/PPT/엑셀/차트)
- **Explore**: 관련 주제 확장 (웹 검색, 사내 문서 등)

15개 Worker 매핑: DirectResponse, WebSearch, UserFiles, CorpRAG, Visualization, YouTube, URLFetch, ITSupport, AcctSupport, Mail, Approval, PPT, Xlsx, Board + DEFAULT 폴백

### 마커 형식
```
<!--FOLLOW_UP:["김민지 다른 기안 문서 조회","결재 내용 PDF 정리","최근 1주 결재현황 요약"]-->
```
- HTML 주석이므로 마크다운 렌더링 시 보이지 않음
- 백엔드: DB 저장 전 항상 제거
- 프론트엔드: complete 시 최종 텍스트에서 제거

### UI 동작
- 표시 조건: `status === 'ready' && !input.trim() && suggestions !== null`
- 숨김: 사용자 타이핑 시, 제안 클릭 시, 새 메시지 전송 시
- 스타일: text-xs 수평 칩, max-w-[250px] truncate, Framer Motion fade-in

### 제안 생략 기준 (LLM 판단)
- 간단한 인사 응답
- 오류 응답/도구 실패
- 후속 질문이 자연스럽지 않은 단순 확인 응답

## 결정 사항 및 주의점
- **LLM 단일 레이어**: 제안 생략 판단은 LLM 프롬프트에만 위임 (백엔드 필터링 없음)
- **3개 고정**: 파싱 시 `len == 3` 엄격 체크 (2개/4개면 전체 무시)
- **파싱 실패 silent fail**: 마커 없거나 형식 오류 시 제안 없이 정상 완료 (로그만 출력)
- **프롬프트 토큰 추가**: ~250자 (약 15토큰) — 무시 가능 수준
- **finalParts 변경**: 기존 조건부 구성 → 항상 구성으로 단순화 (기능 동일)

# 2026-03-09 CLARIFY 인텐트 + 자동 Fallback Worker

## 개요
모호한 조회 요청 대응을 위한 2중 안전망:
1. **CLARIFY 인텐트** — 어디서 찾아야 할지 완전히 모호한 요청 시 사용자에게 사전 확인
2. **자동 Fallback** — 1순위 워커가 검색 결과 없으면 LLM이 선정한 2순위 워커를 자동 실행

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/state.py | 수정 | `Intent.CLARIFY` enum 추가, INTENT_TO_WORKER에 DirectResponseWorker 매핑 |
| backend/app/agents/intent_classifier.py | 수정 | 1순위+2순위 인텐트 반환 (`Tuple[Intent, Optional[Intent]]`), clarify 인텐트, 프롬프트 응답 형식 변경 |
| backend/app/agents/orchestrator.py | 수정 | Phase 5 fallback 로직 — NO_RESULTS 감지 시 2순위 워커 자동 실행, `_extract_text()` 헬퍼 |
| backend/app/agents/workers/base_worker.py | 수정 | `<!--NO_RESULTS-->` 마커 지시, `is_final_attempt` 조건부 대안 제시, clarify_mode 처리 |
| backend/app/agents/a2a_streaming.py | 수정 | NO_RESULTS 마커 strip, fallback intent_classified 이벤트 처리 |

## 상세 내용

### 1. 분류기: 1순위 + 2순위 인텐트 반환
- LLM 프롬프트가 "approval,board" 형식으로 primary + fallback 반환
- `classify()` 반환값: `Tuple[Intent, Optional[Intent]]`
- quick_classify (규칙 기반)는 항상 `(intent, None)` — 확실한 패턴이므로 fallback 불필요
- `_parse_intent()`, `_apply_overrides()` 헬퍼 메서드로 리팩토링

### 2. NO_RESULTS 마커 기반 감지
- 워커가 검색 결과를 못 찾으면 응답 첫 줄에 `<!--NO_RESULTS-->` 마커 출력
- 자연어 패턴 매칭보다 신뢰성 높음 (구조화된 시그널)
- a2a_streaming.py에서 DB 저장 전 마커 제거

### 3. 조건부 대안 제시
- **1순위 워커** (`is_final_attempt=False`): 마커만 출력, 대안 목록 제시 안 함 → 시스템이 자동 fallback
- **2순위 워커** (`is_final_attempt=True`): 마커 + 남은 대안 범위 목록 제시 (이미 검색한 범위 제외)

### 4. Fallback 워커 선정 기준
- **LLM 맥락 기반** 선정 (정적 맵이 아님)
- 예: "WA정산 관련 건" → primary=approval, secondary=acct_support (LLM이 회계 키워드 인식)
- 예: "OO 프로젝트 현황" → primary=board, secondary=web_search

### 동작 흐름

**Case 1: 1순위 실패 → 2순위 성공**
```
"WA정산 관련 건 조회" → [approval] 결과 없음 (NO_RESULTS)
  → 구분선 "다른 곳에서도 찾아보겠습니다..."
  → [acct_support] VOC 검색 → 결과 있음 → 정상 응답
```

**Case 2: 양쪽 모두 실패**
```
"OO 건 확인" → [board] 결과 없음 → [web_search] 결과 없음
  → is_final_attempt=True → "다른 곳에서 찾아볼까요? 전자결재/메일/사내문서/VOC..."
```

**Case 3: 1순위 성공 (대부분)**
```
"결재 대기 건 확인" → [approval] 결과 있음 → 정상 응답 (fallback 스킵)
```

## 결정 사항 및 주의점
- Fallback은 **최대 1회** (2순위만, 3순위 없음)
- `FALLBACK_ELIGIBLE_INTENTS`: approval, board, corp_rag, it_support, acct_support, web_search
- MailWorker는 fallback 대상 아님 (개인 데이터)
- quick_classify 결과는 secondary=None → fallback 없음
- 첫 워커 응답은 이미 스트리밍 → 구분선으로 분리
- 프론트엔드 변경 없음 (기존 SSE 처리 그대로)

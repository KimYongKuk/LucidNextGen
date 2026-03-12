# 2026-03-11 XlsxWorker 토큰 최적화

## 개요
XlsxWorker의 ReAct agent loop에서 input 토큰이 기하급수적으로 누적되는 구조적 문제를 해결. 이전 step의 tool result를 축약하고, 개별 tool result 길이를 제한하여 **예상 82% 토큰 절감**.

## 배경
- 사용자 A2503003이 XlsxWorker 5회 호출로 input 토큰 200만 소모 (콜당 평균 40만)
- 원인: LangGraph ReAct loop에서 매 LLM 호출마다 이전 모든 tool result가 누적
- Bedrock Prompt Caching은 system prompt(3K, 전체의 2%)만 커버하여 효과 미미

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/base_worker.py` | 수정 | `_compact_tool_messages()` 함수 + `compact_previous_results` 프로퍼티 + state_modifier 분기 |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `_truncate_tool_result()` 함수 + `compact_previous_results=True` + secured_ainvoke 수정 |

## 상세 내용

### Approach A: 개별 Tool Result 길이 제한 (`_truncate_tool_result`)
- `TOOL_RESULT_MAX_CHARS = 8000` (약 2,000 토큰)
- 극단적 대량 데이터 방어 (예: 500행 엑셀 읽기 → 50K자 결과)
- `read_data_from_excel` 잘릴 시 "apply_formula 사용" 안내로 정확성 유지
- XlsxWorker의 `secured_ainvoke` 내 단일 return path로 적용

### Approach B: 이전 Step Tool Result 압축 (`_compact_tool_messages`)
- `COMPACT_KEEP_RECENT_PAIRS = 2`: 최근 2개 tool call 쌍은 원본 유지
- `COMPACT_SUMMARY_MAX_CHARS = 200`: 이전 쌍의 ToolMessage content를 200자로 축약
- **tool_call_id 페어링 유지** — 메시지 자체를 삭제하지 않고 content만 교체
- `state_modifier`를 string → callable로 전환하여 매 LLM 호출 전 압축 실행

### 동작 흐름
```
LLM Call #1: system(3K) + user(1K) = 4K
  → tool result 50K → A가 8K로 잘름
LLM Call #2: system(3K) + user(1K) + AI#1(0.5K) + tool#1(8K) = 12.5K
LLM Call #3: system(3K) + user(1K) + [tool#1 압축→0.2K] + AI#2(0.5K) + tool#2(0.5K) = 5.2K
  (기존: 13K → 60% 절감)
Call #10: system(3K) + user(1K) + [8쌍 압축→1.6K] + 최근2쌍(9K) = 14.6K
  (기존: 84K → 83% 절감)
```

### 적용 범위
- `compact_previous_results` 프로퍼티 기본값 `False` → XlsxWorker만 `True`로 오버라이드
- 다른 Worker에 영향 없음

## 결정 사항 및 주의점
- **COMPACT_SUMMARY_MAX_CHARS=200**: 헤더+1~2행 수준. LLM이 이전 데이터 구조를 파악 가능하되 토큰 절감 극대화. 사용자 피드백에 따라 500~1000으로 상향 가능
- **COMPACT_KEEP_RECENT_PAIRS=2**: 직전 2개 작업 맥락 유지. 3단계 이전 작업은 축약됨
- **AIMessage 원본 유지**: LLM이 "뭘 했는지"는 기억하되 "결과 데이터"만 축약
- **다른 Worker 확장**: PPTWorker 등에도 `compact_previous_results=True` 추가 가능

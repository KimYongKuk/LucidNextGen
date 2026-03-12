# 2026-03-12 XlsxWorker 토큰 최적화 2차

## 개요
XlsxWorker의 ReAct loop에서 AIMessage tool_calls args(특히 write_data_to_excel의 대량 data 배열)가 압축되지 않아 input tokens가 438K까지 폭증하는 문제 해결. AIMessage args 압축 + 비문자열 결과 잘림 처리 추가.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/base_worker.py | 수정 | `_compact_tool_messages`에 AIMessage tool_calls args 압축 추가, `COMPACT_KEEP_RECENT_PAIRS` 2→1 |
| backend/app/agents/workers/xlsx_worker.py | 수정 | `_truncate_tool_result`가 모든 타입 처리하도록 개선 |

## 상세 내용

### 문제 분석
- 사용자 A2306023의 token_usage_log에서 XlsxWorker INPUT_TOKENS가 최대 438,161까지 발생
- 원인 1: `write_data_to_excel(data=[[수백행 데이터]])` 호출의 AIMessage가 tool_calls.args에 전체 데이터를 저장하며, `_compact_tool_messages`는 ToolMessage.content만 압축하고 AIMessage args는 미처리
- 원인 2: `_truncate_tool_result`가 `isinstance(result, str)` 체크로 비문자열 결과를 통과시킴

### 수정 사항

1. **`_compact_tool_call_args()` 함수 신규 추가**
   - AIMessage의 tool_calls args 중 큰 값을 요약으로 대체
   - `List[List]` (data 배열): `"[1000행 x 5열 데이터 생략]"`
   - `List[Dict]`: `"[10개 dict 항목 생략]"`
   - 긴 문자열: 300자로 잘림
   - `COMPACT_ARGS_MAX_CHARS = 300` 상수 추가

2. **`_compact_tool_messages()` 강화**
   - 기존: ToolMessage.content만 압축
   - 변경: ToolMessage.content + AIMessage tool_calls args 모두 압축
   - `compact_ai_indices` 세트 추가로 이전 AIMessage 식별
   - 로그에 `AIMsg_args=N개` 추가

3. **`COMPACT_KEEP_RECENT_PAIRS` 2→1**
   - 최근 1개 tool call 쌍만 원본 유지 (더 공격적 압축)

4. **`_truncate_tool_result()` 타입 안전성**
   - `str`, `ToolMessage` (content 속성), 기타 타입 모두 문자열 변환 후 잘라냄

### 예상 효과
- 438K 토큰 시나리오에서 ~50-80K로 80%+ 절감
- write_data_to_excel의 대형 data 배열이 이후 LLM 호출에서 300자로 압축

## 결정 사항 및 주의점
- `COMPACT_KEEP_RECENT_PAIRS=1`로 줄여 최신 tool call만 원본 유지 — LLM이 직전 결과만 정확히 보면 충분
- AIMessage 압축 시 tool_call_id는 보존하여 LangGraph ValidationError 방지
- 비문자열 결과가 원래 타입을 잃을 수 있지만, LangGraph ToolNode가 최종적으로 string으로 변환하므로 문제없음

# 2026-03-16 tavily_search 도구 결과 잘림 버그 수정

## 개요
XlsxWorker의 `secured_ainvoke` 래핑이 전역 캐시된 `tavily_search` 도구에 적용되어, 모든 웹검색 결과가 8,000자로 잘리고 ⚠️ 경고 메시지가 LLM에 "오류"로 해석되어 "검색 도구에 일시적인 오류가 발생했습니다"라고 응답하던 버그를 수정.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/xlsx_worker.py | 수정 | tavily_search 래핑 제외 + 이전 래핑 원복 로직 + _truncate_tool_result 방어 |

## 상세 내용

### 원인 분석
1. XlsxWorker의 `tool_names`에 `tavily_search`가 포함됨 (시장 데이터 검색용)
2. `prepare_tools()`가 모든 필터된 도구에 `secured_ainvoke`를 `object.__setattr__`로 in-place 래핑
3. MCP 도구는 전역 캐시 (TTL 1시간) → 래핑된 tavily_search가 모든 Worker에 영향
4. `_truncate_tool_result`가 tavily 검색 결과(~9,600자)를 8,000자로 자르며 `⚠️ 결과가 길어...` 메시지 추가
5. LLM이 ⚠️ 경고를 "도구 오류"로 해석 → "검색 도구에 일시적인 오류가 발생했습니다" 응답

### 수정 내용
1. **`prepare_tools()`에서 tavily_search 래핑 제외**: `SKIP_WRAPPING` frozenset으로 외부 도구 제외
2. **이전 래핑 원복**: 이미 래핑된 경우 `_unwrapped_ainvoke`로 복원 (서버 재시작 없이 즉시 적용)
3. **`_truncate_tool_result` 방어**: tavily_search인 경우 원본 반환 (이중 안전장치)

### 영향 범위
- XlsxWorker 내에서 tavily_search 사용 시: filepath 검증/lock/truncation 없이 원본 ainvoke 직접 호출
- 다른 Worker의 tavily_search: 래핑 오염 해소, 검색 결과 전문 전달

## 결정 사항 및 주의점
- tavily_search는 filepath 파라미터가 없으므로 보안 래핑(경로 검증/lock)이 불필요
- 향후 XlsxWorker에 외부 도구를 추가할 때 `SKIP_WRAPPING`에도 등록 필요
- MCP 전역 캐시의 in-place 수정은 Worker 간 상호 영향이 있으므로, 래핑 시 도구 범위를 항상 확인할 것

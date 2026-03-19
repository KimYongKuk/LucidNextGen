# 2026-03-18 MCP 도구 로드 실패 시 DirectWorker 자동 폴백

## 개요
tavily-mcp 등 MCP 서버가 프로덕션에서 간헐적으로 로드 실패하면, WebSearchWorker가 도구 0개로 실행되어 LLM이 가짜 `<tool_call>` 태그를 텍스트로 생성하는 문제가 발생했다. Orchestrator의 Worker Dispatch 단계에서 도구 가용성을 체크하고, 도구가 없으면 DirectWorker로 안전하게 폴백하도록 수정했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/orchestrator.py` | 수정 | Phase 2에서 도구 가용성 체크 + DirectWorker 폴백 로직 추가 |
| `backend/mcp_config.json` | 수정 | tavily-mcp `@latest` → `@0.2.18` 버전 고정 (이전 커밋) |

## 상세 내용

### 문제 상황
1. 프로덕션에서 `tavily-mcp` NPX 실행이 간헐적 실패 (`ExceptionGroup`)
2. MCP Adapter는 개별 서버 실패를 잡아 빈 리스트 반환 (정상 동작)
3. WebSearchWorker가 `filtered_tools=[]`로 실행됨
4. LLM 프롬프트는 "tavily_search를 사용하라"고 지시 → 도구가 없으니 가짜 tool 태그를 텍스트로 출력
5. 스트리밍 필터가 대부분 잡지만, 엣지케이스에서 코드 구조가 사용자에게 노출

### 해결 방식
```python
# Phase 2: Worker Dispatch (+ 도구 가용성 체크)
if worker.tool_names:
    available = worker.filter_tools(all_tools)
    if not available:
        worker_name = "DirectResponseWorker"
        worker = get_worker(worker_name)
        # intent_classified 이벤트 재전송 (tool_fallback 플래그)
```

- `worker.tool_names`가 있는 Worker만 체크 (DirectWorker는 도구 불필요이므로 스킵)
- 도구가 0개면 `DirectResponseWorker`로 교체
- 프론트엔드에 `tool_fallback: true` 플래그가 포함된 `intent_classified` 이벤트 재전송

### tavily-mcp 버전 고정
- `@latest` → `@0.2.18` 고정으로 NPX 다운로드 불안정성 감소
- `@latest`는 매번 npm registry를 조회하여 네트워크 타임아웃 위험

## 결정 사항 및 주의점
- 폴백은 Worker Dispatch(Phase 2) 단계에서 발생하므로, 이후 Phase 3~6은 정상 흐름으로 진행
- DirectWorker로 폴백되면 웹검색 없이 LLM 자체 지식으로 응답 (사용자에게 별도 안내 없음)
- tavily-mcp 버전 업그레이드 시 mcp_config.json의 버전 번호를 수동으로 변경해야 함

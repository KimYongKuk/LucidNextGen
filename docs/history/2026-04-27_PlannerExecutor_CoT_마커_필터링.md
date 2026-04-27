# 2026-04-27 Planner-Executor CoT task_thinking 마커 필터링

## 개요
Planner-Executor 경로에서 워커 LLM이 응답 끝에 출력하는 `<!--FOLLOW_UP:[...]-->`, `<!--HANDOFF:...-->`, `<!--NO_RESULTS-->` 같은 HTML 주석 마커와 모델이 가끔 텍스트로 흘리는 `<tool_call>`/`<function_calls>` 태그가 **task_thinking CoT 타임라인에 그대로 노출**되던 문제를 해결한다. 메인 본문 SSE 스트림은 이미 동일 태그를 청크 경계 안전 필터로 제거하고 있었으나 `task_thinking` 변환 경로에는 동일 필터가 적용되지 않아 사용자가 보는 CoT 타임라인이 지저분해 보였다.

작업 범위는 사용자 요청에 따라 **CoT 노이즈 제거에만 한정**하고, Narrator(Haiku 1줄 내레이션)·Heartbeat·rule-based tool_status 등 작업 중 UX 멘트 다양성은 유지한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/executor.py | 수정 | `_StreamTagFilter` 클래스 추가 + execute() 내 task_id별 필터 dict로 task_thinking 출력에 적용 |

## 상세 내용

### 문제
워커의 시스템 프롬프트(`base_worker.py:1031-1060`)는 모든 워커에게 응답 끝에 `<!--FOLLOW_UP:["제안1","제안2","제안3"]-->` 마커를, HANDOFF 가능한 경우 응답 시작에 `<!--HANDOFF:인텐트-->`를 출력하도록 강제한다. 결과 없음을 알리는 `<!--NO_RESULTS-->`도 동일 패턴.

메인 본문 SSE 스트림은 `a2a_streaming.py:749-795`에서 청크 경계에 걸친 마커도 안전하게 제거하는 점진적 필터(`<` 등장 시 버퍼링 → 매칭/길이 초과 시 처리)를 갖고 있어 사용자가 보는 답변에는 마커가 남지 않는다.

그러나 Planner-Executor 경로의 `task_thinking` 이벤트는 `executor.py:166-174`에서 워커의 `on_chat_model_stream` 청크를 **그대로 yield**한다. 워커 LLM은 도구 호출 reasoning + 최종 답변 + FOLLOW_UP 마커를 같은 스트림으로 토해내므로, CoT 타임라인에 마커가 그대로 보였다. 프론트의 `use-simple-chat.ts:410-435`가 `executor_done` 시점에 사후 정제하지만 **스트리밍 진행 중에는 노출**된다.

### 해결
`_StreamTagFilter` 클래스를 executor.py 상단에 추가:

- 태그 집합은 메인 본문 필터와 동일 (`<!--`/`-->`, `<tool_call>`/`</tool_call>`, `<tool_response>`/`</tool_response>`, `<function_calls>`/`</function_calls>`, `<function_result>`/`</function_result>`)
- `feed(text)` 메서드: 청크를 받아 안전한 텍스트만 반환, 태그 내부 텍스트는 폐기, 청크 경계에 걸친 태그는 다음 청크에서 매칭
- `flush()` 메서드: 스트림 종료 시 남은 안전 텍스트 반환 (태그 내부였으면 빈 문자열)
- 종료 태그 없이 50,000자 초과 시 안전장치 발동

execute() 내부에 `tag_filters: Dict[str, _StreamTagFilter]` 를 task_id 키로 유지하고 세 지점에 적용:

1. **드레인 루프** (`executor.py:166-185`): on_chat_model_stream 텍스트를 task_thinking으로 변환하기 전에 `tf.feed(text)` 통과
2. **마지막 flush 루프** (`executor.py:198-219`): 동일 변환 + 필터링 적용 (이전엔 그냥 yield)
3. **execute() 종료 직전** (`executor.py:227-235`): 모든 필터의 `flush()` 호출하여 남은 안전 텍스트 방출 (태그 외부 잔여 버퍼만)

### 보존한 부분 (의도적)
- `narrator.py`: Haiku 기반 도구 호출 1줄 내레이션 (`🔍 'PR파트' 관련 메일을 찾아보는 중...`) — UX 가치 유지
- `a2a_streaming.py:206-252` rule-based tool_status (정적 + 동적) — 도구별 다양성 유지
- heartbeat 메시지 — 긴 작업 중 사용자 피드백 유지
- 프론트 `use-simple-chat.ts:410-435` `executor_done` 사후 정제 — 청크 경계에 걸려 빠져나간 마커 잔재용 안전망으로 그대로 둠

## 결정 사항 및 주의점

- **메인 본문 필터와 코드 중복**: a2a_streaming.py와 executor.py가 동일 태그 집합·청크 처리 로직을 갖게 됐다. 추후 공통 모듈로 추출 가능하나 이번 변경은 범위를 좁혀 executor.py 내부에만 클래스를 두었다(파일 간 의존 추가 회피).
- **워커 final 답변 자체도 task_thinking으로 흐름**: 본 변경은 마커만 제거할 뿐, 워커가 메인 답변과 동일한 텍스트를 task_thinking으로도 흘리는 구조 자체는 그대로다. CoT 타임라인이 답변과 거의 같은 내용을 보여주는 부분은 별도 토의 후 결정 예정.
- **Planner LLM 호출로 인한 latency**: 단순 요청에서도 Sonnet Planner를 한 번 더 부르는 오버헤드(~1초)는 본 변경으로 다루지 않는다. Planner 우회 옵션은 별도 작업 항목.
- **PLANNER_ENABLED=false 환경**: 본 변경은 Planner-Executor 경로에서만 효과. 기존 intent_classifier 직행 경로는 a2a_streaming.py의 메인 본문 필터가 이미 마커를 처리하므로 영향 없음.

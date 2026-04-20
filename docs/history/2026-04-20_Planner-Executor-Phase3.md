# 2026-04-20 Planner-Executor Phase 3 — Executor + Synthesizer + 전 경로 통합

## 개요

[Phase 2](2026-04-20_Planner-Executor-Phase2.md)에서 shadow-mode로 Planner를 관찰하던 상태를 넘어, **Executor(DAG 실행)** 와 **Synthesizer(응답 합성)** 를 신규 구현하고 orchestrator에서 전 경로를 연결한다. `PLANNER_ENABLED=true`일 때 **복합 요청은 신 경로**(Planner→Executor→Synthesizer)를 실행하고, **단순 요청/Planner 실패는 레거시 경로**(intent_classifier→Worker)로 폴백한다.

기존 동작은 **flag off 시 완전 동일** — 신 경로는 코드에 존재만 하고 비활성.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/executor.py` | 신규 | DAG 위상정렬 + asyncio.gather 병렬 실행 + 의존성 주입 + 실패 cascade + needs_confirm 분기 |
| `backend/app/agents/synthesizer.py` | 신규 | Haiku 기반 Blackboard → 사용자 응답 합성 + is_trivial passthrough + 실패 폴백 |
| `backend/app/agents/workers/base_worker.py` | 수정 | `build_system_prompt`에 `task_goal` / `task_id` / `task_dependencies` 주입 섹션 추가 |
| `backend/app/agents/orchestrator.py` | 수정 | `_planner_shadow_run` 제거 → `_run_planner_executor` 도입 (전 경로 오케스트레이션). `PLANNER_ENABLED=true` 시 신 경로 우선 시도, 폴백 시 레거시 경로 실행 |
| `backend/app/agents/planner.py` | 수정 | LLM 설정을 `get_worker_config(use_sonnet=True)` 로 변경 (Haiku → Sonnet 명시화) |

## 상세 내용

### Executor (executor.py)

```python
class Executor:
    def __init__(self, max_parallel=10, task_timeout=300): ...

    async def execute(self, plan, context, all_tools, blackboard,
                      memory_context, user_memory_context) -> AsyncIterator[Event]:
        """DAG 순회하며 이벤트 스트림 반환"""
```

**알고리즘 (메인 루프):**

1. `plan.get_ready_tasks(completed_ids)`로 의존성 만족된 PENDING task 찾기
2. 의존 중 SKIPPED/FAILED 있으면 해당 task도 SKIPPED cascade
3. `needs_confirm=True` task는 실행 안 하고 `AWAITING_CONFIRM` 상태 전환 → `task_awaiting_confirm` 이벤트
4. 나머지 ready task들을 `MAX_PARALLEL_TASKS=10` 상한으로 wave 분할
5. 각 task를 `_run_task` 코루틴으로 동시 실행 (asyncio.create_task)
6. queue 기반 이벤트 드레인: 워커의 스트림 이벤트를 `_task_id` 래핑해 yield
7. 모든 wave 완료까지 반복. 진행 가능한 task 없으면 종료
8. `executor_done` 이벤트 (통계 포함) 최종 yield

**이벤트 타입:**

- `task_started` {task_id, worker, goal}
- `task_completed` {task_id, elapsed_ms, result_preview}
- `task_failed` {task_id, error, elapsed_ms}
- `task_skipped` {task_id, reason}
- `task_awaiting_confirm` {task_id, worker, goal}
- `executor_done` {total_ms, stats, has_awaiting_confirm}
- 워커 내부 이벤트(`on_chat_model_stream` 등) → `_task_id` 필드 추가하여 passthrough

**핵심 설정값 (HITL 승인 2026-04-20):**

- `MAX_PARALLEL_TASKS = 10` — 동시 실행 상한
- `TASK_TIMEOUT_SECONDS = 300` — 개별 task 타임아웃 (5분)

**의존성 주입:**

`_run_task`가 `task.depends`에 나열된 선행 task의 결과를 Blackboard에서 읽어 `context["task_dependencies"] = {task_id: result}` 로 워커에 전달. 워커 프롬프트는 `base_worker.py`에서 이를 "선행 작업 결과" 섹션으로 노출.

### Synthesizer (synthesizer.py)

```python
class Synthesizer:
    async def synthesize(self, original_message, plan, blackboard, context) -> AsyncIterator[Event]:
        """Blackboard 결과를 합성하여 on_chat_model_stream 이벤트 yield"""
```

**핵심 설계:**

- **Trivial passthrough**: `plan.is_trivial=True + 단일 DONE task`이면 LLM 호출 생략, 워커 결과를 그대로 스트림 (토큰 절약)
- **프롬프트 빌드**: 사용자 원본 메시지 + Plan rationale + task별 상태/결과를 마크다운으로 조합해 Haiku에 전달
- **승인 대기 처리**: AWAITING_CONFIRM task가 있으면 "아래 내용으로 진행할까요?" 문구 강제
- **모델**: Haiku (`get_orchestrator_config()`), max_tokens=4096, temperature=0.3
- **실패 폴백**: Haiku 스트림 예외 시 `_build_fallback_text`로 raw task 결과 덤프 (최후 안전망)

**출력 이벤트 형식:**

```python
{"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content=...)}}
```

워커와 동일 형식 → 프론트엔드/chat.py의 기존 처리 로직 재사용.

### Base Worker (task_goal 주입)

```python
# build_system_prompt 내부:
task_goal = context.get("task_goal")
if task_goal:
    prompt += f"""
## TASK GOAL (최우선 지시) — Task ID: {task_id}

**{task_goal}**

이 목표만 달성하세요. 사용자 원본 메시지에 다른 요청이 있어도 **무시**하세요 —
다른 부분은 다른 워커가 병렬/순차로 처리 중입니다.
...
## 선행 작업 결과
- [t1] 메일 본문...
- [t2] 조직도 결과...
"""
```

**효과:**

- Planner가 분해한 sub-task만 집중 수행 → MailWorker가 "회의실 예약 못 해요" 하고 거부하는 문제 근본 해결
- `task_dependencies`를 프롬프트에 섹션으로 넣어 후속 task가 선행 결과 참조 가능

### Orchestrator 통합

```python
async def stream(self, ...):
    # Phase 0a/0b: 메모리 로드 (기존)
    ...
    # Phase 1.0: Planner-Executor 시도
    if _planner_enabled():
        used_new = False
        async for ev in self._run_planner_executor(...):
            if ev is None:
                break   # fallback signal
            used_new = True
            yield ev
        if used_new:
            return   # 신 경로 완료, 레거시 스킵
    # Phase 1+: 레거시 경로 (기존 그대로)
```

`_run_planner_executor`는 다음 조건에서 `None` sentinel을 yield하여 호출자가 레거시로 폴백하도록 신호:

- `PlannerFallback` 예외 (JSON 파싱 실패, DAG 검증 실패 등)
- Planner의 LLM 호출 예외
- `plan.is_trivial=True` (단순 요청은 레거시가 더 효율적)

## 검증

### 유닛 테스트

**Executor (6/6 PASS):**

1. 병렬 실행 — 독립 2 task가 실제로 병렬 (0.1s 병렬 vs 0.2s 순차)
2. 순차 의존성 — t2 depends t1이면 t1 완료 후 t2 시작
3. 실패 cascade — t1 FAILED → t2 SKIPPED
4. needs_confirm — AWAITING_CONFIRM 전환, 실행 안 됨, Blackboard 미기록
5. 의존성 주입 — t2 context에 `task_dependencies = {"t1": "t1 결과"}` 확인
6. Fan-in — t4 depends on t1/t2/t3, 3개 병렬 완료 후 t4 시작

**Synthesizer (4/4 PASS):**

1. Trivial passthrough — LLM 호출 없이 워커 결과 그대로 스트림
2. Fallback 텍스트 — DONE/FAILED/AWAITING_CONFIRM 모두 포함
3. 프롬프트 구조 — 원본 메시지/rationale/task 결과/승인 지시 포함
4. LLM 예외 → 폴백 텍스트로 대체

**통합 (3/3 PASS):**

1. `PLANNER_ENABLED=false` → Planner 호출 0회, 레거시 경로 동일 동작
2. `PLANNER_ENABLED=true + is_trivial=True` → 레거시 classifier 호출됨
3. `PLANNER_ENABLED=true + 복합 plan` → 신 경로 실행, classifier 호출 안 됨, task_started/executor_done/합성 이벤트 모두 emit

### 회귀 영향

- `PLANNER_ENABLED=false`(기본값)에서 기존 14개 워커 + HANDOFF + NO_RESULTS fallback 로직 완전 유지
- `task_goal` 프롬프트는 context에 `task_goal`이 있을 때만 추가되므로 레거시 경로에선 주입되지 않음

## 결정 사항 및 주의점

### 왜 Executor 안에서 queue를 쓰는가

각 task는 워커를 호출하며 스트림 이벤트를 생성. 여러 task가 병렬이면 이벤트 순서가 섞일 수 있음. queue로 드레인하면 FIFO 순서가 보장되고, `_task_id` 래핑으로 어느 task 이벤트인지 구분 가능. 프론트가 task별로 UI를 쪼개 보여줄 확장성 확보 (현재는 그냥 합쳐서 출력 가능).

### needs_confirm의 현재 단순화된 UX

- Executor는 AWAITING_CONFIRM에서 **실행 중단**하고 Synthesizer가 "진행할까요?" 안내
- 사용자가 다음 턴에 "응" 하면 → **현재 turn 내에서는 처리 안 함**. 이 부분은 Phase 4에서 구체화 (멀티턴 상태 저장, plan resume 메커니즘 필요)
- 임시 해결: 사용자가 "응"이라고 답하면, 그 메시지로 새 Plan이 생성되어 **이전 맥락 없이 다시 실행**됨. 완벽하진 않으나 Phase 3 수용 범위.

### 실패 task의 Blackboard 기록

- 타임아웃 시 부분 결과라도 `[TIMEOUT, 부분결과]` 접두로 Blackboard 저장 → 후속 task가 일부라도 참고 가능
- 완전 실패(예외)는 Blackboard 미기록. `t.error`에 원인 보존.

### Synthesizer 토큰 소비 방지책

- is_trivial + 단일 DONE = LLM 호출 스킵 (가장 큰 최적화)
- 개별 task 결과가 4000자 초과 시 잘라서 프롬프트에 전달
- temperature=0.3으로 결정적에 가깝게

### 이벤트 호환성

- 워커 생성 이벤트 `on_chat_model_stream` 형식을 Executor/Synthesizer 모두 동일 사용
- chat.py / use-simple-chat.ts는 **이벤트 구조상 수정 불필요**
- 단, `task_*` 신규 이벤트 타입은 프론트에서 현재 무시됨 — 필요 시 Phase 4에서 UI 바인딩 추가

### Planner가 Sonnet 사용 (중요)

Phase 2 문서에선 `get_orchestrator_config()`(Haiku) 재사용했으나, **Phase 3에서 `get_worker_config(use_sonnet=True)`로 변경**.

이유: Task DAG 분해는 intent 1개 분류보다 훨씬 복잡한 reasoning. Haiku로는 복합 의존성 추론/타임 계산 정확도가 떨어질 가능성. `WORKER_SONNET_MODEL_ID` 환경변수로 제어.

비용: Planner 호출당 input ~4K(프롬프트+few-shot) + output ~500토큰. Sonnet 기준 요청당 ~$0.015 추가. 복합 요청 비율이 낮으면 수용 가능. 관찰 후 필요 시 2-tier (Haiku 먼저 trivial 판정, Sonnet에 복합만 위임) 구조 검토.

## 후속 작업 (Phase 4 이후)

1. **로컬 통합 테스트 시나리오 10개** — 설계 문서의 시나리오 목록 실행
2. **needs_confirm 멀티턴 재개** — plan_id + awaiting_tasks를 chat_sessions에 저장, 다음 턴 "응"에 재개 트리거
3. **프론트 task_* 이벤트 UI** — 병렬 task 진행 상황 시각화
4. **성능 측정** — Planner/Executor/Synthesizer 각 구간 레이턴시와 전체 end-to-end, 기존 경로 대비 비교
5. **Phase 5 — green 실트래픽 검증** — `PLANNER_ENABLED=true` 활성화 후 로그 모니터링

# 2026-04-20 Planner-Executor 아키텍처 설계 (Design Doc)

## 개요

현재 `orchestrator.py`는 이름상 오케스트레이터이나 실제로는 **단일 Intent → 단일 Worker 디스패처 + 1-hop HANDOFF 땜빵** 수준이다. 복합 요청(예: "메일 내용 확인하고 회의실 예약하고 캘린더 등록하고 아젠다 메일 초안 작성")이 올 때 Intent classifier가 단일 intent만 선택 → Worker 하나로 처리 시도 → 도구 부재/HANDOFF 거부/MCP 실패 등으로 연쇄 붕괴하는 장애가 반복 관측됨 (운영 로그 2026-04-20 09:25, 09:37).

본 문서는 **진짜 orchestration 패턴**인 **Planner-Executor 분리 아키텍처**로 업그레이드하는 설계 결정과 마이그레이션 경로를 기록한다.

## 배경 — 현재 구조의 한계

### 관측된 장애 시나리오

**Case 1 (09:25)**: "PR파트 메일 건 관련 다음 주 수요일 14시 회의실+캘린더+아젠다 메일"
- Quick classifier: `[mail, reservation, calendar]` 3개 매칭
- LLM: `calendar` 단독 선택 (mail 드롭)
- CalendarWorker 실행 → 메일 도구 없음 → 충돌 감지 후 "어떻게 할까요?" 되물음 → 전체 중단

**Case 2 (09:37)**: 동일 유형 + MCP 스폰 실패 중첩
- 캐시 refresh 시 5개 서버(calendar, reservation 포함) 일시 실패
- CalendarWorker가 4개 도구만 수령 (22개 중 18개 누락)
- `<!--HANDOFF:mail-->` 방출 → MailWorker 거부 → CalendarWorker 재실행 시 도구 여전히 없음 → 무한 HANDOFF 후 무응답

### 근본 원인 4가지

1. **Task 분해 부재**: Intent classifier는 `Intent` enum 하나만 반환. 복합 요청을 sub-task로 쪼개는 계층이 없음.
2. **Scope isolation 부재**: HANDOFF target 워커가 **원본 메시지 전체**를 받음 → 자기 역할을 잘못 해석 (MailWorker가 "회의실 예약 못 해요" 거부)
3. **병렬성 부재**: 독립적 sub-task (메일 조회 ∥ 회의실 조회 ∥ 조직도 조회)를 순차적으로만 처리
4. **State 공유 부재**: 선행 결과를 `AIMessage` 히스토리 주입으로 전달 → 토큰 낭비 + 오독 위험

## 제안 아키텍처

### 개념 계층

```
Coordinator (얇은 진입점)
  ├─ Planner     — 요청 → Task DAG (LLM, stateless)
  ├─ Executor    — DAG 실행, 병렬/순차 스케줄링
  ├─ Synthesizer — Blackboard 결과 → 사용자 응답 합성
  └─ Blackboard  — Task 결과 공유 저장소 (in-memory dict)

Worker (실행 단위) — 기존 workers/ 재사용, goal 기반 실행으로 인터페이스만 소폭 변경
Tool (원자 액션) — 기존 MCP tools 그대로
```

### 데이터 구조

#### Task

```python
@dataclass
class Task:
    id: str                      # "t1", "t2" ...
    worker: str                  # WORKER_REGISTRY key (예: "mail", "calendar")
    goal: str                    # 워커가 받을 단일 목표 (한 줄 한국어)
    depends: List[str] = []      # 선행 task id 목록
    needs_confirm: bool = False  # True면 실행 전 사용자 승인 필요
    status: TaskStatus = PENDING # PENDING | RUNNING | DONE | FAILED | SKIPPED | AWAITING_CONFIRM
    result: Optional[str] = None # Worker의 출력 텍스트 (완료 후 채워짐)
    error: Optional[str] = None  # 실패 시 에러 메시지
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
```

#### Plan

```python
@dataclass
class Plan:
    tasks: List[Task]
    rationale: str               # Planner가 왜 이렇게 쪼갰는지 (디버그/로그용)
    is_trivial: bool = False     # 단순 단일 task면 True (기존 경로로 우회 가능)
```

#### Blackboard

```python
class Blackboard:
    """Task 실행 결과 공유 저장소 (요청 생명주기 동안만 유효)"""

    def __init__(self):
        self._results: Dict[str, str] = {}  # task_id → result text
        self._metadata: Dict[str, Any] = {}  # 구조화 데이터 (필요시)
        self._lock = asyncio.Lock()

    async def put(self, task_id: str, result: str, metadata: Optional[Dict] = None): ...
    async def get(self, task_id: str) -> Optional[str]: ...
    async def get_dependencies(self, task: Task) -> Dict[str, str]:
        """task.depends에 나열된 id들의 결과를 {id: result} 맵으로 반환"""
```

### 실행 흐름 예시

사용자 요청: *"'PR파트 검색엔진' 메일 건 관련하여 다음 주 수요일 14시 최지원,장욱진과 본사 회의실 예약하고, 캘린더 등록 후 아젠다 메일 작성해줘"*

**1) Planner 출력:**

```json
{
  "rationale": "메일 조회/조직도 확인/회의실 검색은 독립적 → 병렬. 일정 등록과 회의실 예약은 참석자 확인 + 빈 회의실 확인 후 실행. 아젠다 작성은 메일 본문 필요.",
  "is_trivial": false,
  "tasks": [
    {"id":"t1","worker":"mail","goal":"'PR파트 검색엔진 회사 소개 문구 수정 요청' 메일 본문 조회","depends":[]},
    {"id":"t2","worker":"org_chart","goal":"최지원, 장욱진 사번/소속/근무지 조회","depends":[]},
    {"id":"t3","worker":"reservation","goal":"본사 2026-04-29 14:00~15:00 빈 회의실 조회","depends":[]},
    {"id":"t4","worker":"calendar","goal":"t2 참석자 2명의 2026-04-29 14:00~15:00 일정 충돌 확인","depends":["t2"]},
    {"id":"t5","worker":"calendar","goal":"내 캘린더에 '[PR파트] 검색엔진 소개 문구 회의' 일정 등록","depends":["t3","t4"],"needs_confirm":true},
    {"id":"t6","worker":"reservation","goal":"t3에서 고른 회의실 예약","depends":["t3","t4"],"needs_confirm":true},
    {"id":"t7","worker":"mail","goal":"t1 본문 기반 회의 아젠다 초안 작성 (비즈니스 톤)","depends":["t1"]}
  ]
}
```

**2) Executor 스케줄링:**

```
[레벨 0, 병렬]  t1, t2, t3  (depends 없음) → asyncio.gather
[레벨 1]        t4 (t2 완료 후), t7 (t1 완료 후) → 각자 준비되면 즉시 실행
[레벨 2]        t5, t6 (t3+t4 완료 후) → needs_confirm=true이므로 사용자에게 승인 UI 전송
               [사용자 응답 대기]
               승인 시 병렬 실행, 거부 시 SKIPPED
```

**3) Blackboard 상태 (예시):**

```python
{
  "t1": "제목: [PR파트] 검색엔진 회사 소개 문구 수정 요청\n본문: ...수정 요청 사항 3가지...",
  "t2": "최지원(A0012, PR파트, 성서), 장욱진(A0034, PR파트, 성서)",
  "t3": "성공-C/R3(id=198), 컨퍼런스콜(id=211) 비어있음",
  "t4": "최지원 14:00~15:00 [AI PoC] GS 정기 미팅 충돌, 장욱진 일정 없음",
  "t5": "DONE — eventId=XXXXX 등록 완료",
  "t6": "DONE — 성공-C/R3 예약 완료 (reservation_id=YYY)",
  "t7": "안녕하세요. 검색엔진 소개 문구 수정 관련하여..."
}
```

**4) Synthesizer 출력:**

```markdown
✅ 아래 작업을 완료했습니다:

| 항목 | 결과 |
|------|------|
| 📅 일정 등록 | 4/29(수) 14:00~15:00 "PR파트 검색엔진 소개 문구 회의" |
| 🏢 회의실 예약 | 본사 성공-C/R3 |
| 📧 참석자 | 최지원(⚠️ 기존 일정 충돌), 장욱진 |
| ✍️ 아젠다 초안 | 아래 참조 |

**⚠️ 최지원님 일정 충돌**: 같은 시간 [AI PoC] GS 정기 미팅 참석 중. 본인이 조율 필요.

**아젠다 초안**:
> 안녕하세요. 검색엔진 소개 문구 수정 관련하여...
```

## 모듈 설계

### planner.py (신규, `intent_classifier.py`를 진화)

```python
class Planner:
    """사용자 요청을 Task DAG로 분해하는 LLM 계획자"""

    async def plan(self, message: str, context: RequestContext) -> Plan:
        """
        - 단순 요청: is_trivial=True, tasks=1개로 반환 → 기존 classifier 동작과 동일
        - 복합 요청: tasks=N개로 분해, depends로 DAG 구성
        - LLM 프롬프트에 WORKER_REGISTRY(워커 capability 설명) 주입
        """
```

**프롬프트 설계 원칙:**
- 사용 가능한 워커 목록과 각 워커의 capability 명시
- 의존성을 명시하도록 강제 (A→B일 때 B.depends=["A"])
- Task goal은 "한 줄, 해당 워커가 즉시 실행 가능한 구체적 목표"
- `needs_confirm=true`는 쓰기 작업(예약/등록/발송)에만
- Few-shot 예시 3개 이상

### executor.py (신규, `orchestrator.py`의 실행 루프 이전)

```python
class Executor:
    """Plan을 받아 DAG 순회하며 워커 실행"""

    async def execute(
        self, plan: Plan, context: RequestContext,
        blackboard: Blackboard
    ) -> AsyncIterator[Event]:
        """
        - 위상정렬로 depends 만족되는 task부터 실행
        - 병렬 가능 task는 asyncio.gather
        - needs_confirm task는 사용자 승인 이벤트 대기
        - 실패 시 전략: 첫 구현은 해당 task만 FAILED 처리, 의존 task는 SKIPPED
        - 후속 개선: Planner에게 re-plan 요청 (Phase 2)
        """
```

### synthesizer.py (신규)

```python
class Synthesizer:
    """Blackboard 결과를 사용자용 단일 응답으로 합성"""

    async def synthesize(
        self, plan: Plan, blackboard: Blackboard,
        context: RequestContext
    ) -> AsyncIterator[str]:
        """
        - 각 task 결과를 요약/구조화
        - Markdown 표, 불릿, 이모지로 가독성 확보
        - 실패/SKIPPED task는 명시적 안내
        - 스트리밍 지원 (Haiku 모델)
        """
```

### Worker 인터페이스 변경 (소폭)

기존 `stream_response(messages, context, all_tools, memory_context, user_memory_context)` 유지.
다만 **`context["task_goal"]`** 필드를 추가하여, Planner-Executor 경로에서는 워커가 원본 메시지 대신 task goal만 보도록 함:

```python
# base_worker.py — build_system_prompt 확장
task_goal = context.get("task_goal")
if task_goal:
    prompt += f"""

## 당신의 TASK GOAL (최우선 지시)

{task_goal}

이 목표만 달성하세요. 사용자의 원본 메시지에 다른 요청이 있어도 **무시**하세요.
다른 부분은 다른 워커가 병렬로 처리 중입니다.
"""
```

기존 경로(`task_goal` 없음)에서는 원본 메시지 기반으로 동작 유지 → **완전 하위 호환**.

## 마이그레이션 계획

### Feature Flag

```bash
PLANNER_ENABLED=false  # 기본 false
```

- `false`: 기존 `intent_classifier → single worker + HANDOFF` 경로 유지
- `true`: `Planner → Executor → Synthesizer` 새 경로

분기는 `orchestrator.py` 최상단 한 곳에서만.

### Phase별 배포 단위 (deploy unit)

```
Phase 0: MCP 스폰 hotfix               ← 2026-04-20 완료 (commit d099adf)
Phase 1: 타입/Blackboard 인프라         (PLANNER_ENABLED 무관, 순수 추가)
Phase 2: Planner 모듈 + Plan 경로      (flag off, 로컬 테스트 완료 후 deploy)
Phase 3: Executor + Synthesizer       (flag off 유지)
Phase 4: 로컬 통합 테스트 (10+ 시나리오)
Phase 5: green 배포 → flag on으로 실트래픽 테스트
Phase 6: blue 전환 → 전면 활성화
Phase 7: 구 경로(intent_classifier, HANDOFF) 제거 + rename
```

각 Phase는 독립 commit/deploy. 문제 시 이전 Phase로 롤백 가능.

### 로컬 테스트 시나리오 (회귀 방지)

| # | 입력 | 기대 동작 |
|---|------|-----------|
| 1 | "안녕" | DirectWorker, 단일 task, is_trivial=true |
| 2 | "내일 일정 보여줘" | CalendarWorker, 단일 task |
| 3 | "PR파트 메일 요약해줘" | MailWorker, 단일 task |
| 4 | (복합) "메일 조회하고 회의실 예약" | 2 task 병렬, 의존성 명시 |
| 5 | (복합) "PR메일 관련 회의실+캘린더+아젠다" | 7 task, 병렬+순차 혼합 (본 문서 예시) |
| 6 | 일부 MCP 서버 실패 상황 | 해당 task FAILED, 나머지 정상 |
| 7 | needs_confirm task 거부 | SKIPPED 처리, 의존 task도 SKIPPED |
| 8 | 워크스페이스 + 복합 요청 | memory_context 주입 정상 |
| 9 | 파일 업로드 + 복합 요청 | file context 주입 정상 |
| 10 | 5개+ task의 동시 병렬 | asyncio.gather 타임아웃/성능 |

### 네이밍 변경 (Tier 1 + Tier 2)

| 현재 | 신규 | Tier |
|------|------|------|
| `intent_classifier.py` | `planner.py` | 1 |
| `IntentClassifier` 클래스 | `Planner` | 1 |
| `classify()` | `plan()` | 1 |
| `a2a_streaming.py` | `stream_handler.py` | 2 |
| `INTENT_TO_WORKER` | `WORKER_REGISTRY` | 2 |
| `chat_a2a.py` (라우트) | `chat_agent.py` | 2 |
| `is_handoff_target` context 키 | `sub_task_goal` or `task_goal` | 2 |
| `HANDOFF` 마커 | 삭제 (DAG depends로 대체) | 2 |

**유지:** `orchestrator.py` (승격 후 이름이 맞음), `workers/`, `Worker`, 프론트 이벤트명, 로그 prefix `[ORCHESTRATOR]` (신규 `[PLANNER]`, `[EXECUTOR]`는 추가)

## 결정 사항 및 주의점

### 단일 task 우회

Planner가 `is_trivial=true`면 기존 classifier 동작과 동등 (LLM 호출 1회 추가 비용 있으나 명확성 확보). 향후 Haiku로 경량화 가능.

### Planner 출력 검증

LLM이 JSON을 틀리게 반환할 수 있음. Fallback:
1. JSON 파싱 실패 → Intent classifier 호환 응답으로 재파싱 시도
2. 워커 이름 미지 → Direct/DirectResponseWorker fallback
3. 순환 의존성 감지 → 에러 후 intent_classifier 경로로 폴백 (safety net)

### needs_confirm UX

프론트에 새 이벤트 타입 `confirmation_required` 추가 예정. 사용자 응답을 기다리기 위해 스트림을 일시 중단하는 메커니즘 필요. **별도 설계 섹션 작성 예정** (Phase 3 전).

첫 구현은 **단순화**: needs_confirm=true task는 실행하지 않고 "아래 내용으로 진행할까요?" 프롬프트를 Synthesizer에서 안내하는 방식으로 대체. 다음 턴에서 사용자가 "응" 하면 실행. 멀티턴 상태 관리는 기존 chat_sessions에 저장.

### 실패 전략

- **단일 task 실패**: 해당 task만 FAILED, 의존 task는 SKIPPED로 cascade
- **Planner 실패**: 기존 intent_classifier 경로로 fallback
- **Executor 자체 실패** (버그): safety net으로 기존 orchestrator 로직 실행

### 성능 고려

- Planner LLM 호출이 추가 지연(1~2초) → 단순 요청은 trivial 판정으로 빠르게 우회
- Synthesizer LLM 호출 또한 지연 요인 → Haiku로 가볍게
- 병렬 task 수는 `MAX_PARALLEL_TASKS=5`로 제한 (도구 경합 방지)

### 보안 고려

- Worker의 employee_number 주입, 사번 강제(override) 로직은 **그대로 유지**. Planner는 goal만 생성할 뿐 도구 파라미터 결정은 워커에 위임
- `needs_confirm`은 쓰기 작업에 필수. Planner 프롬프트에 **쓰기성 워커 목록** 명시하여 LLM이 강제하도록
- Blackboard는 요청 생명주기 동안만 메모리 상 존재 → 세션 간 격리

### 마이그레이션 리스크

- **Phase 5 시점**이 가장 리스크 큼 (green에서 실트래픽 flag on). 롤백 플랜: `.env` PLANNER_ENABLED=false 변경 즉시 복구.
- Phase 7(네이밍 rename)은 기능 변경 없음. 리뷰 비용만 있음.

## 후속 문서 / 추가 설계 필요

1. **Planner 프롬프트 초안** — 별도 문서 또는 본 문서 업데이트
2. **needs_confirm UX 상세** — 프론트 이벤트 스펙, 멀티턴 상태 저장
3. **Executor 재시도/타임아웃 정책** — task별 세부값
4. **Synthesizer 출력 포맷 스펙** — 사용자 응답 스타일 가이드

## 타임라인 (잠정)

| Phase | 작업 | 예상 기간 |
|-------|------|-----------|
| 1 | 타입/Blackboard | 1~2일 |
| 2 | Planner 모듈 | 2~3일 |
| 3 | Executor + Synthesizer | 3~5일 |
| 4 | 로컬 통합 테스트 | 1~2일 |
| 5 | green 실트래픽 검증 | 1~2일 (운영 상태 주시) |
| 6 | blue 전환 | 반나절 |
| 7 | Cleanup & rename | 반나절 |

**총 9~15일** (실제로는 파편 시간 고려 시 2~3주)

## HITL 체크포인트

- [ ] 본 Design doc 승인 여부
- [ ] Task/Plan 스키마 필드 최종 확정
- [ ] Planner 프롬프트 초안 리뷰
- [ ] 로컬 테스트 시나리오 추가/수정
- [ ] Executor 병렬 제한 값 (`MAX_PARALLEL_TASKS`)
- [ ] Synthesizer 응답 포맷 스타일
- [ ] needs_confirm UX 결정
- [ ] green 배포 시점 승인
- [ ] blue 전환 승인
- [ ] Rename PR 범위 최종 확인

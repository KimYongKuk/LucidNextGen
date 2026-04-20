# 2026-04-20 Planner-Executor Phase 1 — 인프라 타입 추가

## 개요

[Planner-Executor 아키텍처 설계](2026-04-20_Planner-Executor-design.md)의 Phase 1로, 후속 Phase(Planner/Executor/Synthesizer 구현)에서 사용할 **공통 인프라 타입**을 선도입한다.

Phase 1은 **순수 additive** — 기존 `orchestrator.py`, `intent_classifier.py`, workers 코드에 영향 없음. 아직 어떤 코드도 새 타입을 사용하지 않기 때문이다. 타입만 미리 갖춰 Phase 2(Planner 모듈)부터 바로 구현 가능하도록 준비.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/state.py` | 수정 | `Task`, `Plan`, `TaskStatus` dataclass 추가. `RequestContext`에 `task_goal`/`task_id`/`task_dependencies` optional 필드 추가, `total=False` 전환 |
| `backend/app/agents/blackboard.py` | 신규 | `Blackboard` 클래스 — Task 결과 공유 저장소 (asyncio.Lock 기반 thread-safe) |

## 상세 내용

### Task / Plan / TaskStatus (state.py)

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_CONFIRM = "awaiting_confirm"


@dataclass
class Task:
    id: str
    worker: str                     # Intent value (예: "mail", "calendar")
    goal: str                       # 워커에 전달할 한 줄 목표
    depends: List[str] = []
    needs_confirm: bool = False
    status: TaskStatus = PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def is_ready(self, completed_task_ids: set) -> bool
    def elapsed_ms(self) -> Optional[int]


@dataclass
class Plan:
    tasks: List[Task] = []
    rationale: str = ""
    is_trivial: bool = False

    def get_task(self, task_id: str) -> Optional[Task]
    def get_ready_tasks(self, completed_ids: set) -> List[Task]
    def validate(self) -> Optional[str]   # DAG 유효성 검증 — 중복 id, 미지 depends, 순환 감지
```

### Blackboard (blackboard.py)

```python
class Blackboard:
    """요청 생명주기 동안 Task 결과를 공유하는 in-memory 저장소"""

    async def put(self, task_id: str, result: str, metadata: Optional[Dict] = None)
    async def get(self, task_id: str) -> Optional[str]
    async def get_metadata(self, task_id: str) -> Optional[Dict]
    async def get_many(self, task_ids: List[str]) -> Dict[str, str]
    async def get_all(self) -> Dict[str, str]
    async def has(self, task_id: str) -> bool
    def size(self) -> int
```

- `asyncio.Lock`으로 병렬 task 완료 race 방지
- `_results` (텍스트)와 `_metadata` (구조화) 분리
- 요청별 인스턴스 → 세션 간 완전 격리

### RequestContext 확장 (state.py)

```python
class RequestContext(TypedDict, total=False):  # ← total=False 로 변경
    # 기존 필드들...

    # Planner-Executor 경로 전용 (flag on + 복합 요청일 때만)
    task_goal: Optional[str]
    task_id: Optional[str]
    task_dependencies: Optional[Dict[str, str]]
```

`total=False` 전환으로 신규 필드가 optional이 됨. 기존 코드(dict 생성/참조)에는 영향 없음.

## 검증

### 유닛 테스트 (10/10 PASS)

| # | 항목 | 결과 |
|---|------|------|
| 1 | Task 기본 생성 (기본값 `PENDING`, `is_ready` no-depends) | OK |
| 2 | Task depends 체크 (미완료 시 `is_ready=False`) | OK |
| 3 | Plan 기본 + `get_task`, `get_ready_tasks`, `validate` | OK |
| 4 | DAG 검증 — 중복 id 감지 | OK |
| 5 | DAG 검증 — 존재하지 않는 depends 감지 | OK |
| 6 | DAG 검증 — 순환 의존성 감지 (DFS) | OK |
| 7 | Blackboard put/get/has/metadata 기본 | OK |
| 8 | Blackboard 동시 쓰기 (asyncio.gather 100×3) | OK — race 없음 |
| 9 | Blackboard `get_many` (부분 조회) | OK |
| 10 | `Task.elapsed_ms` 타이밍 계산 | OK |

### 기존 코드 호환성

```python
from app.agents.orchestrator import Orchestrator
from app.agents.intent_classifier import IntentClassifier
from app.agents.workers.base_worker import BaseWorker
from app.agents.workers.calendar_worker import CalendarWorker
from app.agents.workers.mail_worker import MailWorker
# → 모두 정상 import
```

기존 import/동작 영향 없음 확인.

## 결정 사항 및 주의점

### Task.worker 필드 타입

- `str`로 두고 `Intent` enum 값(예: `"mail"`)을 담음. Planner LLM이 JSON으로 반환하는 값을 직접 저장하기 위함.
- 실행 시점에 `INTENT_TO_WORKER` 매핑으로 실제 Worker 클래스명(`"MailWorker"`) 획득.
- `Intent` 타입으로 강제하지 않은 이유: LLM이 enum에 없는 값을 줄 수 있고, Executor에서 검증/fallback하는 편이 유연.

### Plan.validate의 순환 감지 알고리즘

- DFS 3-color (WHITE/GRAY/BLACK) 방식. 노드 수 N에 대해 O(N+E).
- 우리 DAG는 최대 10개 노드 수준이므로 성능 무관.
- 실패 시 **첫 번째 발견 cycle 노드 id**만 반환 (전체 cycle 경로는 반환 안 함 — 디버그엔 충분).

### Blackboard의 lock 전략

- 단일 `asyncio.Lock` — 모든 put/get 동작을 직렬화.
- 쓰기는 task 완료 시점 한 번뿐이라 competition 낮음.
- 향후 read-heavy가 되면 `asyncio.Semaphore` 기반 reader-writer로 개선 고려 (현재 불필요).

### `RequestContext` total=False 전환의 영향

- 런타임에 TypedDict는 dict와 동일하므로 동작 영향 0.
- Type checker(mypy 등)에서 기존 키들이 더 이상 "required"로 간주되지 않음. 하지만 이 프로젝트는 엄격한 mypy를 쓰지 않아 실질 영향 없음.
- 이점: Planner-Executor 경로에서 새 필드를 조건부로 주입 가능 (기존 경로는 안 넣어도 됨).

### 의도적으로 안 한 것

- **WORKER_REGISTRY 신규 생성 안 함** — Tier 2 rename(Phase 7)에서 `INTENT_TO_WORKER` → `WORKER_REGISTRY`로 개칭 예정. Phase 1에선 기존 `WORKER_CAPABILITIES` 재사용으로 충분.
- **Planner/Executor/Synthesizer 스켈레톤 안 생성** — Phase 2~3에서 본격 구현 시 한꺼번에.

## 후속 작업 (Phase 2)

1. `planner.py` 신규 — `Planner.plan(message, context) -> Plan`
2. Planner LLM 프롬프트 초안 (Few-shot 예시 3+)
3. `orchestrator.py`에 `PLANNER_ENABLED` feature flag 분기 추가 (아직 Executor 없으므로 Plan 출력만 로그에 찍고 기존 경로로 fallback)
4. Planner 유닛 테스트 (복합 요청 분해 정확도 검증)

# 2026-04-20 Planner-Executor Phase 2 — Planner 모듈 + shadow 모드

## 개요

[Phase 1](2026-04-20_Planner-Executor-Phase1.md)에서 추가한 `Task`/`Plan`/`Blackboard` 인프라 위에, 사용자 요청을 Task DAG로 분해하는 **Planner 모듈**을 신규 구현한다. `PLANNER_ENABLED` feature flag로 on/off 제어하며, 본 Phase에서는 **shadow 모드**(기존 경로와 병렬로 Planner를 호출하여 출력만 로그)로 동작시켜 실제 트래픽에서 Planner 품질을 관찰한다. 기존 동작에는 영향 없음.

Phase 3(Executor 도입) 이전까지는 Planner 출력이 실행으로 이어지지 않으므로 **순수 관찰 단계**이다.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/planner.py` | 신규 | `Planner` 클래스 + few-shot 시스템 프롬프트 + JSON 파싱 + DAG 검증 + singleton factory |
| `backend/app/agents/orchestrator.py` | 수정 | `_planner_shadow_run()` static method 추가, Phase 1 진입 직전 `PLANNER_ENABLED=true`일 때 fire-and-forget |

## 상세 내용

### Planner (planner.py)

```python
class Planner:
    def __init__(self): ...
    async def plan(self, message: str, context: RequestContext) -> Plan:
        """사용자 요청을 Plan으로 분해. 실패 시 PlannerFallback 발생."""

class PlannerFallback(Exception):
    """Planner 실패 시 호출자가 기존 intent_classifier 경로로 폴백하도록 알림"""

def get_planner() -> Planner: ...    # singleton
def is_planner_enabled() -> bool: ... # PLANNER_ENABLED env flag
```

**핵심 설계:**

- **모델**: Sonnet (계획 품질 중시, intent_classifier와 별개)
- **온도**: 0.0 (결정론적)
- **입력 컨텍스트**: `today`, `has_files`, `has_workspace`, `workspace_name` + 사용자 메시지
- **워커 카탈로그 주입**: 환경변수로 비활성화된 워커 제외하고 프롬프트에 목록 전달 (비활성 워커로 라우팅 방지)
- **출력 형식**: 순수 JSON (`is_trivial`, `rationale`, `tasks[]`). 코드 펜스 자동 제거
- **Few-shot 5개**:
  1. Trivial 단일 조회 ("오늘 일정 보여줘")
  2. Trivial direct ("파이썬 리스트 정렬")
  3. 2-task 병렬 ("메일 + 내일 일정")
  4. 7-task 복합 DAG (PR파트 메일+회의실+캘린더+아젠다 — 본 프로젝트 실제 장애 사례)
  5. 순차 의존 (메일 검색 → 본문 요약)

**검증 단계 (plan() 내부):**

1. LLM 호출 (실패 시 `PlannerFallback`)
2. 코드 펜스 제거 → `json.loads` (실패 시 `PlannerFallback`)
3. `_dict_to_plan`으로 dataclass 변환 (구조 에러 시 `PlannerFallback`)
4. `Plan.validate()` 호출 (중복 id / 미지 depends / 순환 감지 시 `PlannerFallback`)
5. 워커 이름 검증 (`Intent` enum에 없으면 `PlannerFallback`)

모든 실패는 **PlannerFallback 단일 예외 타입**으로 수렴 → 호출자는 단일 except만 걸면 됨.

### Orchestrator 통합 (orchestrator.py)

```python
# Phase 1 classification 직전:
if _planner_enabled():
    asyncio.create_task(self._planner_shadow_run(message, context))
# 기존 classifier 호출은 그대로
primary_intent, fallback_intent = await self.classifier.classify(...)
```

- `asyncio.create_task`로 **fire-and-forget** — 메인 파이프라인은 대기 없이 기존 경로 진행
- Shadow 실행 결과는 `[PLANNER] Shadow — N tasks (Xms), is_trivial=...` 로그로만 남김
- 실패는 조용히 `[PLANNER] Shadow failed: ...` 로그 (사용자 응답엔 영향 없음)

### Feature flag

```bash
PLANNER_ENABLED=false  # 기본값 (프로덕션 안전)
# 관찰 시작 시 green 환경에서만 true로 전환
```

- 대소문자 무관 (`true`, `TRUE`, `True` 모두 인식)
- 누락/오타 시 안전하게 false

## 검증

### 유닛 테스트 (8/8 PASS)

| # | 시나리오 | 결과 |
|---|----------|------|
| 1 | Trivial 단일 task JSON 파싱 | OK |
| 2 | 3-task 복합 DAG 파싱 (`depends`, `needs_confirm`) | OK |
| 3 | 코드 펜스(\`\`\`json) 자동 제거 | OK |
| 4 | JSON 파싱 실패 → `PlannerFallback` | OK |
| 5 | 순환 의존성 감지 → `PlannerFallback` | OK |
| 6 | 존재하지 않는 워커 이름 → `PlannerFallback` | OK |
| 7 | LLM 호출 예외 → `PlannerFallback` | OK |
| 8 | 빈 tasks 배열 → `PlannerFallback` | OK |

### 회귀 테스트

- `is_planner_enabled()`: env 누락=false, `true`=True, `false`=False, `TRUE`=True 모두 정상
- `Orchestrator()` 인스턴스화 정상
- Shadow helper `_planner_shadow_run` 존재 확인
- 기존 `intent_classifier` 경로 영향 없음

## 결정 사항 및 주의점

### 왜 shadow 모드인가

Planner를 바로 실행 경로로 투입하지 않는 이유:
1. **Executor 미구현** — Phase 3에서 추가 예정이므로 Plan을 받아도 실행할 주체 없음
2. **품질 관찰 필요** — 실제 트래픽에서 복합 요청 분해가 기대대로 되는지 로그로 먼저 확인
3. **비용 측정** — Planner 호출로 토큰이 얼마나 추가되는지 실측 후 최적화 방향 결정

### fire-and-forget의 함정 회피

- `asyncio.create_task`로 띄운 shadow task는 이벤트 루프가 종료되면 취소될 수 있음
- 정상 동작 중에는 문제 없지만, 서버 shutdown 시 미완료 task가 있으면 경고 로그 나올 수 있음 — 허용 범위
- Shadow 결과를 어디에도 저장하지 않음(로그만). 비동기 누출 위험 최소화

### Planner 프롬프트 튜닝 계획

현재 few-shot은 5개. Phase 3에서 Executor 도입 후 실제 실트래픽을 보면서 다음 항목을 모니터링/조정:
- `is_trivial` 판정의 정확도 (false positive 시 불필요한 DAG 생성)
- `needs_confirm` 판정의 보수성 (과도한 승인 요청은 UX 저해)
- 복합 요청 분해의 병렬성 효율 (독립 task를 잘 식별하는지)

### 모델 선택 재검토 여지

현재 Planner는 Sonnet 사용. 관찰 결과 대부분 요청이 trivial이면 Haiku로 전환하여 비용 절감 가능. 복합 요청 비율이 낮으면 **2-tier 구조**(Haiku로 trivial 빠르게 판정 → 복합이면 Sonnet에게 분해 위임) 검토.

### 향후 Phase 3 인터페이스

- `Executor.execute(plan, context, blackboard) -> AsyncIterator[Event]`
- `PLANNER_ENABLED=true`일 때 shadow 호출 대신 진짜 실행 경로로 분기
- 기존 `intent_classifier` 경로는 `is_trivial=true` 또는 `PlannerFallback` 시 폴백으로 유지

## 후속 작업

1. **Phase 3 — Executor 구현** — DAG 위상정렬, asyncio.gather 병렬 실행, Blackboard 연동
2. **Phase 3.5 — Synthesizer** — Blackboard 결과 → 사용자 응답 합성 (Haiku)
3. **Phase 4 — needs_confirm UX** — 프론트 승인 이벤트 + 멀티턴 상태 저장
4. **로컬 통합 테스트 시나리오 10개** — 설계 문서의 시나리오 목록 기준

## 파일 경로 (참고)

- 신규: `backend/app/agents/planner.py`
- 수정: `backend/app/agents/orchestrator.py` (import 1줄, shadow 호출 3줄, shadow helper 15줄)
- 설계: `docs/history/2026-04-20_Planner-Executor-design.md`
- Phase 1: `docs/history/2026-04-20_Planner-Executor-Phase1.md`

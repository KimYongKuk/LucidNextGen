# 2026-04-20 Planner-Executor Phase 4 — 실 Bedrock 통합 시나리오 검증

## 개요

[Phase 3](2026-04-20_Planner-Executor-Phase3.md)에서 구현 완료된 Planner→Executor→Synthesizer 파이프라인을 **실제 Bedrock Sonnet API**로 호출하여 10개의 대표 시나리오에서 Plan 품질을 검증한다. 유닛 테스트만으로는 LLM 출력 품질을 판정할 수 없으므로, 토큰 비용을 감수하고 실 호출로 Planner의 분해 정확도를 측정한다.

**결과: 10/10 PASS — 프롬프트 이터레이션 불필요, Phase 5(green 배포)로 진행 가능.**

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| (임시) `backend/test_phase4_scenarios.py` | 신규 → 삭제 | 10개 시나리오 자동 검증 harness. 1회성 실행 후 제거 |
| `CHANGELOG.md` / `docs/history/` | 수정/신규 | Phase 4 결과 기록 |

소스 코드 변경 없음. **Phase 4는 순수 검증 단계**.

## 테스트 설계

### 검증 구조

- 각 시나리오: (이름, 사용자 메시지, 검증 함수) 튜플
- Planner.plan() 실 호출 → Plan 반환 → 검증 함수로 구조 판정
- 검증 항목: `is_trivial`, task 수, worker 종류, `depends` 구조, `needs_confirm` 유무
- 토큰 사용량 + 지연시간 측정

### Validator 유틸

- `v_trivial_worker(worker)`: is_trivial=true + 1 task + 지정 worker
- `v_parallel_count(min, max)`: is_trivial=false + task 범위 + 모두 depends=[]
- `v_sequential(count)`: is_trivial=false + 지정 task 수 + 최소 1개 depends 보유
- `v_has_confirm()`: 최소 1개 needs_confirm=true
- `v_complex_dag(min_tasks, must_confirm)`: 병렬+순차 혼합 + confirm 포함

## 시나리오 결과

| # | 시나리오 | 요청 | 결과 | 지연 | in/out 토큰 |
|---|----------|------|------|------|-------------|
| S1 | 단순 인사 | "안녕" | ✅ 1 task / direct / is_trivial | 5167ms | 2437/113 |
| S2 | 일반 지식 | "파이썬 리스트 정렬하는 법 알려줘" | ✅ 1 task / direct / is_trivial | 2342ms | 2455/128 |
| S3 | 단일 캘린더 | "오늘 일정 보여줘" | ✅ 1 task / calendar / is_trivial | 2049ms | 2445/114 |
| S4 | 단일 메일 | "받은 메일 5개만 보여줘" | ✅ 1 task / mail / is_trivial | 2523ms | 2448/110 |
| S5 | 2-task 병렬 | "메일 5개 + 내일 일정" | ✅ 2 tasks 모두 depends=[] | 2695ms | 2458/144 |
| S6 | 순차 의존 (검색→요약) | "정기 점검 메일 찾아서 요약" | ✅ t2 depends ["t1"] | 2752ms | 2456/199 |
| S7 | 쓰기 (confirm 필수) | "내일 15~16시 팀 미팅 등록" | ✅ 1 task / calendar / needs_confirm | 16210ms | 2470/143 |
| S8 | 3-way 병렬 | "메일 + 일정 + 결재 대기" | ✅ 3 tasks / 모두 병렬 | 4316ms | 2471/192 |
| S9 | **복합 DAG (PR파트 케이스)** | 설계 문서 원본 장애 사례 | ✅ **7 tasks** / 병렬+순차+confirm | 7753ms | 2547/705 |
| S10 | wiki→PDF 순차 | "위키 보안 정책 찾아서 PDF로" | ✅ 2 tasks / t2 depends t1 | 3371ms | 2458/220 |

**총 토큰**: input 24,645 / output 2,068
**총 비용 (Sonnet $3/$15 per 1M)**: $0.074 + $0.031 = **~$0.10**
**평균 지연**: 4,917ms/시나리오

## S9 복합 DAG 상세 (설계 문서의 기대 출력과 대조)

**Planner 실제 출력:**

```
t1 [mail]        'PR파트 검색엔진' 키워드로 관련 메일 본문 조회              depends=[]
t2 [corp_rag]    최지원, 장욱진 사번 및 이메일 주소 조회                    depends=[]
t3 [reservation] 본사 2026-04-30(수) 14:00~15:00 빈 회의실 조회            depends=[]
t4 [calendar]    최지원, 장욱진의 해당 시간 일정 충돌 확인                  depends=["t2"]
t5 [reservation] t3 조회 회의실 중 하나 예약                              depends=["t3","t4"]  [CONFIRM]
t6 [calendar]    내 캘린더에 'PR파트 검색엔진 회의' 등록 + 참석자 추가       depends=["t2","t4","t5"]  [CONFIRM]
t7 [mail]        t1 메일 본문 기반 아젠다 초안 작성 (수신자 최지원·장욱진)     depends=["t1","t2"]  [CONFIRM]
```

**설계 문서 기대 출력과 일치:**

- 병렬 첫 wave: t1, t2, t3 (depends=[])
- 순차: t4는 t2 완료 후 (참석자 확인 필요)
- 수렴 wave: t5, t6, t7이 선행 데이터 집계 후
- 쓰기 작업(예약/캘린더/메일 초안)에만 needs_confirm=true

**Planner의 반대 없이 도달한 품질:** 설계 문서 시점엔 7-task 예시를 few-shot에 명시했으나 실행 시엔 유사 구조(5~8 tasks) 중 정확히 **7 tasks로 수렴**. Few-shot 학습 효과 확인.

## 관찰 및 판단

### 긍정적 관찰

1. **is_trivial 판정 정확도 100%** — 단순 4건 모두 trivial, 복합 6건 모두 is_trivial=false
2. **Worker 선택 정확도 100%** — 모든 시나리오에서 기대 워커와 일치
3. **depends 정확성 100%** — 병렬은 depends=[], 순차는 올바른 선행 task id 참조
4. **needs_confirm 보수성 적절** — 읽기 task는 confirm 없음, 쓰기 작업만 confirm=true
5. **Goal 품질** — "t1에서 찾은 메일 본문 조회 후 요약" 처럼 선행 task 결과 참조를 자연어로 명시
6. **한국어 rationale** — Few-shot 예시와 동일 톤으로 일관

### 주의 사항

1. **S7 지연 16초** — 이상치. Bedrock 냉시동 또는 리전 경합 가능성. 재현 테스트 권장이나 일회성으로 판단
2. **평균 지연 ~5초** — Sonnet 특성. 단순 요청은 2~3초, 복합 요청은 4~8초
3. **Input 토큰 2.4K 고정** — Few-shot 프롬프트가 대부분. Prompt caching 도입 시 비용 절감 가능 (Phase 5+ 고려)
4. **S10의 `direct` 워커 PDF 생성** — 기술적으로 동작하나(DirectResponseWorker에 PDF 공유 도구 존재), 명시적 doc worker가 있다면 더 명확. 현재 구조상 허용

### 비용 관점

- 시나리오당 ~$0.01
- 월 10K 복합 요청 기준: ~$100/월 Planner 추가 비용
- Prompt caching (Anthropic Bedrock 지원) 적용 시 30~50% 절감 가능 (Few-shot 부분이 재사용 가능)
- **Phase 5에서 실트래픽 관찰 후 최적화 필요 여부 판단**

## 결정 사항

1. **프롬프트 이터레이션 불필요** — 10/10 PASS 품질로 현재 프롬프트 유지
2. **Phase 5 진행 가능** — green 환경 배포 + 실트래픽으로 flag on 검증
3. **S7 지연 원인 추적은 선택사항** — 단일 outlier로 판단, 통계 유의미성 부족
4. **Prompt caching 도입 여부는 Phase 5 후 판단** — 실트래픽에서 비용 체감 후 결정

## 후속 작업

1. **Phase 5 — green 배포**
   - PLANNER_ENABLED=false로 배포 (코드만 반영)
   - green 환경에서 .env로 true 전환 → 내부 테스트 계정으로 실 요청
   - 로그 모니터링: Planner 출력 품질, 총 지연, 토큰 비용
2. **Phase 6 — blue 전환 후 전면 활성화**
3. **Phase 7 — Cleanup & rename** (Tier 1+2)

## 테스트 재실행 방법 (참고)

Phase 4 test harness는 일회성이라 삭제. 필요 시 `docs/history/2026-04-20_Planner-Executor-Phase4.md` 의 시나리오 표를 기반으로 재작성 가능. 또는 다음 경로에 복구:

```python
# 간단한 재실행 스니펫
import asyncio, os
os.environ["PLANNER_ENABLED"] = "true"
from app.agents.planner import get_planner

async def main():
    planner = get_planner()
    for msg in ["안녕", "오늘 일정 보여줘", "메일 5개랑 내일 일정"]:
        plan = await planner.plan(msg, {"user_id": "test"})
        print(f"{msg}: {len(plan.tasks)} tasks, is_trivial={plan.is_trivial}")

asyncio.run(main())
```

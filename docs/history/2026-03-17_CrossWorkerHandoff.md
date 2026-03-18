# 2026-03-17 Cross-Worker HANDOFF 메커니즘

## 개요
워커 간 데이터 연계를 위한 HANDOFF 메커니즘 구현. 이전 대화 데이터 활용(Case A)과 선행 워커 자동 실행 체이닝(Case B) 두 시나리오를 해결.

## 배경
엑셀워커가 이전 턴에서 메일워커가 가져온 데이터를 활용하지 못하고 "메일 접근 못합니다"라고 답변하는 문제 발생. 워커 간 데이터 흐름이 단절되어 있었음.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/state.py | ADD | `WORKER_CAPABILITIES` 딕셔너리 (13개 Intent → 기능 설명 매핑) |
| backend/app/agents/workers/base_worker.py | MODIFY | 히스토리 데이터 활용 지침, 요약 시 테이블 보존 강화, HANDOFF 프롬프트 |
| backend/app/agents/orchestrator.py | MODIFY | HANDOFF 패턴 감지 + 선행 워커→원래 워커 체이닝 로직 (Phase 5) |
| backend/app/agents/a2a_streaming.py | MODIFY | HANDOFF intent 기록 보호, HANDOFF 마커 DB 저장 시 제거 |

## 상세 내용

### Case A: 히스토리 데이터 활용
- `build_system_prompt()`에 "CONVERSATION DATA" 지침 추가
- 이전 대화에서 다른 워커가 가져온 데이터를 히스토리에서 직접 활용하도록 지시
- "접근할 수 없습니다" / "지원하지 않습니다" 응답 금지

### Case B: HANDOFF 체이닝
- 워커가 `<!--HANDOFF:intent값-->` 마커를 출력하면 Orchestrator가 감지
- 선행 워커 실행 → 결과를 `[이전 단계에서 가져온 데이터]`로 히스토리에 주입 → 원래 워커 재실행
- 무한 루프 방지 3중 안전장치:
  1. `is_handoff_target` 컨텍스트 플래그 → 선행 워커는 HANDOFF 프롬프트 미주입
  2. Orchestrator `not context.get("is_handoff_target")` 체크
  3. `handoff_intent != intent` → 자기 자신 HANDOFF 방지

### 요약 테이블 보존 강화
- Assistant 메시지에 테이블(마크다운 `|` 3행 이상) 포함 시 요약 limit 6,000자로 확대 (기본 2,000자)
- 요약 프롬프트에 테이블/표 보존 규칙 추가

### WORKER_CAPABILITIES 레지스트리
```python
WORKER_CAPABILITIES = {
    Intent.MAIL: "메일 조회/검색/요약 ...",
    Intent.XLSX: "엑셀 파일 생성/수정 ...",
    # ... 13개 Intent
}
```
- 각 워커 시스템 프롬프트에 자기 자신 제외한 다른 워커 능력 목록 주입

## 결정 사항 및 주의점
- HANDOFF는 최대 1단계만 허용 (A→B→재실행A). 2단계 체이닝은 의도적으로 미지원.
- DirectResponseWorker는 `tool_names`가 비어있어 HANDOFF 프롬프트 미주입 (의도적)
- HANDOFF 발생 시 응답 시간 약 2배 증가 (선행 워커 + 재실행 워커 직렬)
- HANDOFF 후 재실행 워커의 NO_RESULTS 감지 시 Fallback도 연쇄 실행 가능 (최대 3워커)

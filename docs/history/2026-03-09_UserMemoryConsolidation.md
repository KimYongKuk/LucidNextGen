# 2026-03-09 사용자 메모리 개선

## 개요
사용자 전역 메모리의 key facts 상한을 20 → 100개로 확대하고, 초과 시 기존 FIFO 방식 대신 Haiku LLM이 중요도 판단하여 공격적으로 압축(병합/삭제)하도록 개선. 추가로 메모리 로딩 버그 수정 및 프롬프트 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/services/memory_service.py | 수정 | 상한 100개, consolidation 추가, JSON 파싱 버그 수정 |
| backend/app/agents/workers/base_worker.py | 수정 | User Profile 프롬프트 개선 (메모리 활용 안내) |
| backend/app/agents/orchestrator.py | 수정 | 메모리 로딩 디버그 로그 추가 |

## 상세 내용

### 변경 전
- `USER_MEMORY_KEY_FACTS_LIMIT = 20`
- 초과 시 `all_facts[-20:]` (FIFO — 오래된 것부터 삭제)
- 문제: 이름, 부서 등 중요한 초기 fact가 밀려서 삭제됨

### 변경 후
- `USER_MEMORY_KEY_FACTS_LIMIT = 100`
- 초과 시 `_consolidate_user_facts()` 호출 → Haiku가 공격적 압축
  - 신원 정보(이름/부서/직책)는 절대 삭제 금지
  - 유사/중복 fact 병합 (예: 2개 → 1개)
  - 모호하거나 일회성 fact 삭제
  - "최대한 줄여라" 지시 → 100개 → 70~80개 수준으로 압축
- 실패 시 기존 FIFO로 폴백 (안전장치)

### 새 프롬프트: `USER_FACTS_CONSOLIDATION_PROMPT`
- 정리 우선순위: 신원정보 보존 > 명시적 요청 보존 > 유사 병합 > 모호/일회성 삭제
- 출력: 한 줄에 하나씩, 번호/기호 없이

### 새 메서드: `_consolidate_user_facts(all_facts)`
- 입력: 100개 초과된 fact 리스트
- Haiku 호출 → 응답 파싱 → 원문 매칭 시 메타데이터(extracted_at) 보존
- 병합/재작성된 fact는 새 타임스탬프 부여
- 검증: 빈 응답 → FIFO 폴백, 예외 → FIFO 폴백

### JSON 파싱 버그 수정 (`get_user_memory`)
- **원인**: DB에 `[{...}, {...}]` (bare list) 형태로 저장된 레거시 데이터가 있었음
- 코드는 `{"facts": [...]}` (dict 래퍼) 만 기대 → `list.get("facts")` 에서 `AttributeError`
- 예외가 조용히 삼켜져서 facts가 항상 None 반환 → 메모리 기능이 사실상 비활성 상태였음
- **수정**: `isinstance(data, dict)` / `isinstance(data, list)` 분기로 양쪽 형식 모두 지원

### User Profile 프롬프트 개선 (`base_worker.py`)
- 변경 전: "대화 주제와 직접 관련될 때만 자연스럽게 활용하세요"
- 변경 후: "당신은 이 사용자와의 이전 대화 내용을 기억하고 있습니다" + "자신에 대해 물어보면 답변하세요"
- LLM의 "이전 대화를 기억하지 못합니다" 기본 습성을 override

## 결정 사항 및 주의점
- 100개 채우려면 ~680 메시지 필요 → consolidation은 장기 사용자에게만 발생
- consolidation은 추가 Haiku 호출 1회 (비용 ~$0.004, 초과 시에만)
- "100개로 맞춰라"가 아닌 "최대한 줄여라" 방식 → 압축 후 여유 확보, 다음 정리까지 간격 늘어남
- JSON 파싱: 향후 저장은 `{"facts": [...]}` 래퍼 형식이지만, 읽기는 bare list도 호환

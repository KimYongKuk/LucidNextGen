# 2026-05-04 Agent Store 필터 카테고리 정비

## 개요
Agent Store 라우팅 화면(카탈로그 리스트)의 필터 카테고리를 사용자 피드백에 맞춰 재구성. 부서 필터 제거, 범위 필터에 Native 옵션 추가, 그리고 기능·범위 두 필터를 단일 선택 → 멀티 체크 방식으로 전환했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| frontend/components/agent-store/agent-filters.tsx | 수정 | 부서 Select 제거, 기능·범위 Select → DropdownMenuCheckboxItem 기반 멀티 체크, Native 옵션 추가, `ScopeOption` 타입 신규 export |
| frontend/components/agent-store/agent-store-content.tsx | 수정 | 필터 상태 타입을 `string` → `Capability[]` / `ScopeOption[]`로 전환, 부서 필터 state·핸들러 제거, 필터 로직에서 Native 분기(`a.isNative ? "native" : a.visibility`) 추가 |

## 상세 내용

### 1) 부서 필터 제거
- `departmentFilter` state, `handleResetFilters` 내 reset, `AgentFilters` props·UI 모두 제거.
- `mock-data.ts`의 `DEPARTMENTS` 상수는 다른 곳에서 쓰일 수 있어 그대로 두고 import만 제거.

### 2) 범위 필터에 Native 추가
- 기존 `Visibility = "public" | "team" | "private"`에 더해 `ScopeOption = Visibility | "native"` 신설.
- 카탈로그 필터링 시 에이전트의 `effective scope`를 다음과 같이 산출:
  ```ts
  const agentScope: ScopeOption = a.isNative ? "native" : a.visibility;
  ```
- 즉 Native seed Agent(`isNative=true`)는 visibility 값과 무관하게 항상 `native` 카테고리로 분류 → 사용자가 "Native만 보기"·"Native 빼고 보기"를 자연스럽게 선택 가능.

### 3) 멀티 체크 셀렉트
- shadcn `Select`(단일 선택)는 멀티 체크 미지원이라 기능·범위 두 필터를 `DropdownMenu` + `DropdownMenuCheckboxItem`으로 교체.
- 기존 `SelectTrigger`와 동일한 룩앤필을 유지하기 위해 `DropdownMenuTrigger asChild` + 직접 스타일링한 `<button>` 사용 (`h-9 w-[160px]`, `border-input`, `ChevronDown`).
- 체크 토글 시 메뉴가 닫히지 않도록 `onSelect={(e) => e.preventDefault()}` — 한 번 열어 여러 항목 빠르게 토글 가능.
- 트리거 라벨 규칙:
  - 0개 선택 → "전체 기능"·"전체 범위" (placeholder 톤)
  - 1개 선택 → 해당 항목 단일 라벨 ("대화형", "Public" 등)
  - 2개 이상 → "기능 N개"·"범위 N개"
- 정렬 셀렉트는 단일 선택이므로 그대로 `Select` 유지.

### 필터 매칭 로직
```ts
const matchesCapability =
  capabilityFilter.length === 0 ||
  capabilityFilter.some((c) => a.capabilities.includes(c));

const agentScope: ScopeOption = a.isNative ? "native" : a.visibility;
const matchesScope =
  scopeFilter.length === 0 || scopeFilter.includes(agentScope);
```
- 빈 배열 = 필터 미적용(= 전체 표시) — 모든 항목 체크 해제도 동일하게 처리.
- `hasFilters`(`empty-state`의 "필터 초기화" 분기) 판정도 `length > 0` 기준으로 변경.

## 결정 사항 및 주의점
- **Native를 visibility 안에 합친 이유**: Native 여부는 별도 boolean(`isNative`)이라 별도 토글로 두면 UX가 늘어남. 사용자가 "범위" 필터로 인지한다는 점에서 visibility 카테고리 안에 흡수하는 것이 가장 직관적이고, "Native 보기/빼기" 두 케이스 모두 한 셀렉트에서 해결됨.
- **DropdownMenu vs Popover**: 프로젝트에 `popover.tsx`가 없어 새 의존성 도입 대신 기존 `dropdown-menu.tsx`의 `DropdownMenuCheckboxItem` 재활용. 동작상 동일.
- **`onSelect` preventDefault**: 빼면 체크 한 번 토글마다 메뉴가 닫혀서 멀티 선택 UX가 망가짐.
- **DEPARTMENTS 상수 보존**: mock-data 측 상수는 그대로 둠 — 향후 다시 부서 분류가 필요해질 가능성 + 다른 mock 컴포넌트가 참조할 수 있어 안전하게 미삭제.
- **`isNative` 경로 신뢰**: `Agent` 타입의 `isNative`는 backend adapter가 채워주는 값(adapter 변경은 본 수정 범위 밖). adapter가 false/undefined일 경우 자연스럽게 `visibility` 분기로 떨어져 호환됨.

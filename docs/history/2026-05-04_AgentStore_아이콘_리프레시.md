# 2026-05-04 Agent Store 아이콘 리프레시

## 개요
Agent Store 카드/디테일/피커/워크스페이스 탭 4개 surface의 메인 아이콘 비주얼을 통일·정돈. 사용자가 카탈로그 카드 첫인상을 "AI가 자동 생성한 placeholder 같다"고 지적 → 두 가지 변경: (1) Lucide `Sparkles`(별/스파클) → `Puzzle`(퍼즐 조각)로 fallback 및 모든 사용처 교체, (2) 아이콘 박스의 컬러 타일 배경(`${iconColor}20`)을 제거해 카드 배경에 자연스럽게 녹아들게.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/components/agent-store/agent-card.tsx` | 수정 | 박스 배경 제거(rounded-xl + bgColor 삭제), 아이콘 h-5 → h-6, Sparkles → Puzzle |
| `frontend/components/agent-store/agent-detail-content.tsx` | 수정 | h-16 박스 배경 제거(rounded-2xl + bgColor 삭제), 아이콘 h-8 → h-10, Sparkles → Puzzle |
| `frontend/components/agent-store/agent-picker-dialog.tsx` | 수정 | h-9 박스 배경 제거, 아이콘 h-4 → h-5, Sparkles → Puzzle (iconMap + 빈 상태 CTA 모두) |
| `frontend/components/workspace-agents-tab.tsx` | 수정 | h-9 박스 배경 제거, 아이콘 h-4 → h-5, Sparkles → Puzzle (iconMap + 빈 상태 모두) |
| `frontend/components/agent-store/empty-state.tsx` | 수정 | "카탈로그 둘러보기" 버튼의 Sparkles → Puzzle |

## 상세 내용

### 1. 시각 시스템 변경 — 박스 배경 제거
이전: 메인 아이콘이 `${iconColor}20`(rgba 12.5%) 컬러 타일 안에 둘러싸여 카드 카탈로그 전체가 "회색 박스에 라인 아이콘이 박힌 격자"처럼 보였음. 카테고리(capability)별로 색이 들어갔지만 대부분 에이전트가 "대화형(chat)"이라 색 차이가 거의 발생하지 않아 시각적 변별력이 낮았음.

이후: 박스의 `backgroundColor` style + `rounded-xl/2xl` 클래스 제거. wrapper `<div>`는 유지(레이아웃·정렬 보존)하되 시각적으로는 "아이콘 자체"만 표시됨. 박스 프레이밍이 사라진 만큼 아이콘 자체의 시각 무게를 보상하기 위해 사이즈를 한 단계씩 키움 (h-5→h-6, h-8→h-10, h-4→h-5). 색상은 기존 `iconColor` (capability 기반) 그대로 유지.

### 2. Sparkles → Puzzle 교체
이유: `Sparkles`(별 모양) 아이콘은 ChatGPT/Notion AI/Copilot 등 모든 AI 도구가 default로 사용해 "AI 자동 생성물" 시그널이 너무 강함. Agent Store의 본질은 "설치해서 끼워 넣는 모듈 마켓"이므로 `Puzzle`(퍼즐 조각)이 의미적으로 더 적합 (Notion/Slack의 plugin/integration 마켓플레이스도 동일한 메타포).

교체 범위:
- 4개 파일 `iconMap`의 `Sparkles` 값을 `Puzzle` 컴포넌트로 매핑 (`Sparkles: Puzzle`)
- 4개 파일의 fallback `?? Sparkles` → `?? Puzzle`
- 빈 상태 아이콘 (피커 다이얼로그 line 234, workspace-agents-tab line 309) `Sparkles` → `Puzzle`
- `empty-state.tsx`의 "카탈로그 둘러보기" CTA 버튼 `Sparkles` → `Puzzle`

### 3. 백엔드 contract 보존
`agent.icon` 필드는 백엔드/mock에서 `"Sparkles"` 문자열을 그대로 보내고 있음 (예: `frontend/lib/agent-store/mock-data.ts:350`). DB 마이그레이션 없이 호환성 유지하기 위해 `iconMap`의 **키는 `"Sparkles"` 그대로 두고 값(컴포넌트)만 `Puzzle`로 매핑**:

```ts
const iconMap: Record<string, LucideIcon> = {
  // ...
  Sparkles: Puzzle,  // 키는 백엔드 contract, 값은 새 컴포넌트
  Newspaper,
};
```

이로써 기존 데이터(`agent.icon === "Sparkles"`)가 자동으로 Puzzle 아이콘으로 렌더되며, 새 에이전트 등록 시에도 `"Sparkles"` 문자열을 계속 써도 무방.

### 4. 검증 우회 시도 → 폐기 (Phosphor)
초기 시도: Lucide의 균일한 1.5px line stroke 자체가 "AI 생성물" 느낌의 원인이라 판단해 `@phosphor-icons/react`(duotone weight)로 라이브러리 swap PoC. 설치 시 `next-themes@0.3.0` peer 충돌(React 16/17/18만 지원, 본 프로젝트 React 19) → `--legacy-peer-deps`로 우회 가능했고 Phosphor 자체는 새 충돌을 만들지 않았음. 그러나 사용자가 "구조 유지" 방침으로 선회하면서 Phosphor 제거(`npm uninstall`) 후 Lucide만으로 시각 처리(배경 제거 + 아이콘 교체)로 마무리. 의존성 추가 없이 동일한 효과 달성.

## 결정 사항 및 주의점
- **새 아이콘 옵션이 필요할 때**: `iconMap` 기반 4개 파일을 모두 동기화해야 함. 같은 키 세트(`MapPin`, `FileBarChart`, `BookOpen`, `Receipt`, `Database`, `MessageCircle`, `Shield`, `TrendingUp`, `Sparkles`, `Newspaper`)가 4곳에 중복 정의되어 있어, 향후 새 아이콘을 추가할 때 모두 갱신 필요. 단일 모듈로 추출하는 리팩토링 여지 있음(현재는 단순 중복).
- **백엔드에 `"Puzzle"` 문자열 추가 시**: 키 `"Puzzle": Puzzle`을 명시적으로 iconMap에 추가하는 게 더 명확. 현재는 `Sparkles → Puzzle` 매핑으로만 동작.
- **컬러 시스템 변경 없음**: `getPrimaryCapabilityColor()`로 capability 기반 색상 결정하는 로직(`frontend/lib/agent-store/types.ts`) 그대로. 박스 배경만 사라진 거지 아이콘 색은 유지됨.
- **레이아웃 보존**: 모든 파일에서 wrapper `<div>`의 사이즈 클래스(h-9/h-10/h-16)와 flex 정렬은 그대로. 제목·뱃지와의 라인 정렬에 영향 없음.
- **Phosphor 패키지**: 설치 후 제거 완료. `package.json` lucide-react만 남아 있음.

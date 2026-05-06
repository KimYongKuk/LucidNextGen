# 2026-05-04 Agent Store 삭제 기능

## 개요
백엔드의 `DELETE /v1/agents/{slug}` (soft delete, 작성자 또는 operator만 허용) 엔드포인트는 이미 구현돼 있었으나 프론트엔드에 호출 UI가 없어 사용자가 본인이 등록한 에이전트를 정리할 수 없던 문제를 해결. Agent Store 카탈로그 그리드와 에이전트 디테일 페이지 양쪽에서 삭제 affordance 제공.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| frontend/components/agent-store/agent-detail-content.tsx | 수정 | 작성자/operator용 `삭제` 버튼 + AlertDialog 추가, 성공 시 `/agent-store`로 라우팅 |
| frontend/components/agent-store/agent-card.tsx | 수정 | 옵셔널 `onDelete` prop 추가, `isMine && !isNative`일 때 설치 버튼 옆에 휴지통 아이콘 버튼 |
| frontend/components/agent-store/agent-store-content.tsx | 수정 | 카드의 삭제 요청을 받아 단일 AlertDialog로 확인 후 `agentApi.delete` 호출 + 로컬 상태 제거 |

## 상세 내용

### 1. 디테일 페이지 (agent-detail-content.tsx)
- 마운트 시 `isOperatorUser(getUserId())`로 operator 여부 판별 → `isOperator` 상태에 저장.
- `canDelete = !agent.isNative && (agent.isMine || isOperator)`.
- 헤더 액션 영역(install/run 버튼 옆)에 destructive outline 스타일의 `삭제` 버튼을 `canDelete`일 때만 렌더.
- `AlertDialog`로 두 단계 확인:
  - 제목: "이 에이전트를 삭제하시겠습니까?"
  - 본문: 카탈로그 제거 + 설치 사용자 영향 + 비가역성 안내.
- 확인 시 `agentApi.delete(agent.slug)` → 성공 토스트 → `router.push("/agent-store")`. 실패 시 토스트만 표시하고 dialog 유지.

### 2. 카드 (agent-card.tsx)
- `AgentCardProps`에 `onDelete?: (agent: Agent) => void` 추가.
- `canDelete = !!onDelete && agent.isMine && !agent.isNative` — 부모가 핸들러를 줬을 때만 활성.
- 기존 설치 버튼을 `flex` 컨테이너로 감싸고, `canDelete` 조건일 때 옆에 작은 destructive outline `Trash2` 아이콘 버튼을 표시.
- 카드 본체의 onClick(라우팅)과 충돌 방지를 위해 버튼 클릭 시 `e.stopPropagation()` 후 `onDelete!(agent)` 호출.
- Tooltip으로 "삭제" 라벨 제공.

### 3. 스토어 컨테이너 (agent-store-content.tsx)
- 상태: `deleteTarget: Agent | null`, `deleting: boolean`.
- `handleDeleteRequest(a)`:
  - Native이면 `toast.info`로 안내 후 dialog 띄우지 않음 (백엔드도 거부하지만 사용자에게 즉시 피드백).
  - 그 외에는 `setDeleteTarget(a)`.
- `handleConfirmDelete()`:
  - `agentApi.delete(deleteTarget.slug)` → 성공 시 `setAgents(prev => prev.filter(...))`로 로컬 그리드에서 즉시 제거 (재 fetch 불필요).
  - 실패 시 토스트, dialog는 사용자가 닫을 수 있도록 유지.
- 삭제 진행 중에는 `onOpenChange`에서 `!open && !deleting`만 close 허용 → race 차단.
- AgentCard에 `onDelete={handleDeleteRequest}` 항상 전달. 카드 내부에서 `isMine && !isNative` 가드.

## 결정 사항 및 주의점
- **삭제 권한 노출 범위**:
  - 카드: `isMine`만 (operator라도 본인 작품이 아닌 카드에선 표시하지 않음 — 그리드 노이즈 방지).
  - 디테일: `isMine || isOperator` (operator는 명시적으로 디테일 진입한 뒤 삭제 가능).
- **AlertDialog는 컨테이너 단일 인스턴스**: 카드마다 dialog를 만들면 마운트가 카드 수만큼 늘어나고 상태 관리가 분산됨. `deleteTarget` 한 곳에 모아 처리.
- **로컬 상태 제거 방식**: 백엔드 soft delete 후 카탈로그 재 fetch 대신 클라이언트에서 즉시 filter — 응답 지연 없는 UX. 다음 페이지 진입 시 자연스럽게 서버 상태와 동기화됨.
- **Native 가드 다중화**:
  - 카드 prop 가드(`canDelete`에 `!agent.isNative`).
  - 컨테이너 핸들러 가드(`a.isNative`면 toast로 우회).
  - 백엔드 service 단의 권한 검증.
  세 겹 모두 의도적 — UI 갱신 지연/캐시 등으로 클라이언트 isNative가 잘못 표시될 가능성 대비.
- **확인 dialog 본문**: "설치한 사용자들도 더 이상 사용할 수 없습니다"는 soft delete의 user-visible side effect를 강조하기 위한 문구. 실제 DB는 `status='deleted'`로만 마킹되며 row 보존됨(복구 가능 여지).
- 향후 operator 전용 "관리자 모드"에서 본인 작품 외 에이전트도 카드 차원에서 삭제하고 싶다면 `onDelete` prop의 카드 측 조건을 `isMine || (operator prop)`으로 확장하면 됨.

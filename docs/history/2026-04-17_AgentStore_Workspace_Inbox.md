# 2026-04-17 Agent Store · Workspace-Agent 연결 · 알림함 분리

## 개요
루시드AI를 사내 AI Hub로 격상하기 위한 **첫 프론트엔드 구현 세션**. Agent Store 쇼케이스 페이지, Workspace에 Agent 붙이기(P1), 헤더 알림 아이콘 분리까지 작업. 모든 것이 프론트 단독(mock + localStorage) — 백엔드 연동은 아직 0.

내일 이어서 작업하기 위한 전체 맥락과 결정사항, 남은 과제 정리 문서.

---

## 1. 이번 세션 주요 결정사항

### 1.1 Agent Store 위치와 진입 동선
| 결정 전 | 결정 후 |
|---------|---------|
| `/admin/agent-store` (관리자 전용) | `/agent-store` (일반 사용자) |
| 진입점 미정 | 채팅 헤더 오른쪽 🏪 Store 아이콘 |
| 상세는 모달 | **README 스타일 상세 페이지** `/agent-store/[slug]` |

### 1.2 서비스 유형 분류 체계 — **타입 → capability 태그**
**폐기**: `Agent / Workflow / Knowledge` 3타입 단일 선택
- 문제1: "Agent Store 안에 Agent가 있네?" 용어 중복
- 문제2: 각 타입이 서로 다른 레이어 (상호작용 방식 / 실행 방식 / 데이터 소스)

**채택**: **capability 다중 태그 (4개)** — 한 Agent에 여러 태그 부착 가능
| 태그 | 의미 |
|------|------|
| 💬 대화형 (chat) | 자연어 질문 → 답변 |
| ⚡ 실행형 (run) | 폼 입력 → 작업 수행 |
| 📅 스케줄 (scheduled) | 주기적 자동 실행 |
| ⏳ 비동기 (async) | 실행 제출 후 완료 알림 |

**폐기된 태그 후보**:
- `📚 지식검색` → 💬 대화형 + 자유태그 `#RAG`로 표현
- `🔗 외부연동` → 모든 Agent가 해당되므로 태그로서 의미 없음
- `📄 문서출력` → description에 크리에이터가 자유 서술
- `⏱ 예상 소요 5분` 숫자 표시 → 싸구려 느낌, `estimatedDurationSec` 필드만 유지하고 UI 비노출

### 1.3 Agent Store 커버 범위
실제 등장할 서비스 유형 7종 (플랫폼 메타데이터로 표시):
1. Windows EC2 Python 매크로
2. Windows EC2 PAD
3. MISO Agent
4. MISO Workflow
5. 기타 Workflow (n8n 등)
6. 기타 Agent (향후)
7. Workspace (RAG 지식베이스)

### 1.4 Workspace ↔ Agent 관계 — **관점 2 (컨테이너)**
검토한 3가지 관점:
- 관점 1: Workspace = Agent의 한 종류 (Store에 편입)
- **관점 2 (채택)**: Workspace = Agent를 담는 컨테이너
- 관점 3: 하이브리드 (Workspace 승격 가능)

**사용자 동선 2단계**:
```
Agent Store에서 설치(ENABLE)
  ↓
Workspace 설정 → Agents 탭에서 붙이기(활성화)
  ↓
해당 Workspace 채팅에서 자연어로 호출 (라우팅은 P2+)
```

### 1.5 검토된 횡단 과제 7가지
다양한 capability/platform이 Workspace에 붙었을 때 풀어야 할 공통 문제:
1. 시스템 프롬프트 병합 순서 (Workspace 커스텀 + Agent 프롬프트)
2. RAG 소스 병합 (Workspace 문서 + Knowledge Agent)
3. **자격증명/권한** — Runner 기반 Agent의 caller vs service_account (조직 보안 정책과 엮임)
4. Workspace 업로드 파일 → Agent에 전달하는 메커니즘
5. 스케줄 Agent의 Workspace 컨텍스트 유지
6. Intent Router 동적 확장 (설치된 Agent 기반 라우팅)
7. Agent 자체 메모리 vs Workspace memory

→ Phase 단위로 쪼개서 점진적 해결.

### 1.6 구현 Phase 계획
| Phase | 포함 | Capability | 상태 |
|-------|------|-----------|------|
| **P1** | Workspace에 Agent 붙이기/떼기 UI (프론트만) | 데이터만 | ✅ 완료 |
| P2 | 동기 Agent 실제 호출 (Native + MISO Agent + Workspace RAG) | 💬/⚡동기 | 대기 |
| P3 | Runner 기반 비동기 Agent (Python/PAD) | ⏳ | 대기 |
| P4 | 스케줄 Agent | 📅 | 대기 |

### 1.7 스케줄 Agent 결과 전달 방식
옵션 A/B/C/D 검토 후 **A + notice-toast 하이브리드** 채택:
```
스케줄 실행 완료
  ├─ Workspace에 새 chat_session 자동 생성 (🤖 prefix)
  │    └─ 첫 메시지 = Agent 결과 (마크다운/차트/파일 등)
  └─ 알림함에 알림 추가 ("Q-cost 리포트 완료 · 확인하기")
```
세션 폭증 완화: 🤖 마커 필터 + 자동 아카이브(N일 후 `is_archived=1`) + Workspace 사이드바에 "최근 자동 실행" 접힘 섹션.

### 1.8 알림 시스템 리팩토링 (완료)
**기존 문제**:
- 🔔 Bell = 데일리 브리핑 모달 (공지+메일+결재 요약)
- 🌐 Globe = L&F WIKI + WhatsNew 모달 (기능 혼재)
- 공지사항이 Globe 안에 숨어있고, Bell은 브리핑인데 이름은 "실시간 알림"

**새 구조**:
| 아이콘 | 역할 |
|--------|------|
| 📰 Newspaper | 데일리 브리핑 (기존 NoticeToastProvider 그대로, 아이콘만 변경) |
| 🔔 Bell | **알림함 드로어** — 공지 + 스케줄 완료 + 동기 완료 누적 |
| 📖 BookOpen | 순수 L&F WIKI 외부 링크 |

**알림함 내부**:
- 2탭 (내 알림 / 공지사항) — 확장 시 필터 칩으로 진화 가능
- WhatsNew 모달 **재사용** (공지사항 탭 항목 클릭 시 기존 슬라이드 뷰)
- WhatsNew 브랜딩 "새 기능" → **"공지사항"** 리네이밍 (Sparkles → Megaphone)

---

## 2. 완료된 구현

### 2.1 Agent Store
- `/agent-store` 메인 (3탭: Active Agents / Catalog / My Creations)
- `/agent-store/[slug]` 상세 페이지 (README 마크다운 스타일)
- 필터: 검색 · capability · 부서 · 공개범위 · 정렬
- Mock Agent 10개 — 6종 플랫폼 실제 반영 (MISO Agent, MISO Workflow, PAD, Python EC2, n8n, Native, Workspace RAG)
- 설치 토글 (localStorage 아닌 state — 세션 독립)
- 헤더 🏪 아이콘으로 진입

### 2.2 Workspace → Agent 붙이기 (P1)
- Workspace 설정 모달에 **"Agents" 탭** 추가 (General / Knowledge / Agents 3탭)
- **AgentPickerDialog** — 설치한 Agent 목록에서 다중 선택
- **WorkspaceAgentsTab** — 활성 Agent 카드 + 제거 버튼 + capability strip + 경고 메시지
- localStorage 기반 매핑 `ws_agents_{workspace_uuid}` = `string[]`
- 부작용 경고 UI (자동 트리거):
  - 대화형 Agent 3개 이상 → "Intent 라우팅 혼란 가능"
  - 스케줄 Agent 1개 이상 → "정기 실행 결과가 이 Workspace로 전달"
  - 활성 Agent 8개 이상 → "10개 이하 권장"

### 2.3 알림 시스템 분리 (Phase N-1)
- 📰 데일리 브리핑 신설 (기존 Bell 기능 그대로 이동)
- 🔔 알림함 드로어 신설 (우측 슬라이드, 2탭)
  - 4개 mock 개인 알림 (Q-cost 완료, 세금계산서 발행, 뉴스레터, 외화 분석)
  - WhatsNew 공지 자동 구독 → 공지사항 탭 노출
  - 공지 클릭 시 WhatsNew 모달 재사용
  - 미읽음 상태 localStorage (`lucid-inbox-read`)
  - "모두 읽음" / 개별 제거 버튼
- 📖 WIKI 외부 링크 분리 (`NEXT_PUBLIC_WIKI_URL`)
- WhatsNew 브랜딩 리네이밍

---

## 3. 파일 변경 요약

### 3.1 생성 (14개)
**Agent Store 코어**:
- `frontend/lib/agent-store/types.ts`
- `frontend/lib/agent-store/mock-data.ts`
- `frontend/lib/agent-store/workspace-agents.ts`
- `frontend/components/agent-store/agent-card.tsx`
- `frontend/components/agent-store/agent-filters.tsx`
- `frontend/components/agent-store/agent-detail-content.tsx`
- `frontend/components/agent-store/agent-picker-dialog.tsx`
- `frontend/components/agent-store/empty-state.tsx`
- `frontend/components/agent-store/agent-store-content.tsx`
- `frontend/app/agent-store/page.tsx`
- `frontend/app/agent-store/[id]/page.tsx`

**Workspace-Agent 연결**:
- `frontend/components/workspace-agents-tab.tsx`

**알림함**:
- `frontend/components/notification-inbox/notification-inbox-provider.tsx`
- `frontend/components/notification-inbox/inbox-drawer.tsx`

### 3.2 수정 (4개)
- `frontend/app/layout.tsx` — `NotificationInboxProvider` 주입
- `frontend/components/chat-header.tsx` — 아이콘 재편 (📰 추가, 🔔 재배치, 🌐 → 📖)
- `frontend/components/workspace-settings-modal.tsx` — Agents 탭 추가
- `frontend/components/whats-new/whats-new-modal.tsx` — "새 기능" → "공지사항" 리브랜딩

### 3.3 삭제 (1개)
- `frontend/components/agent-store/agent-detail-modal.tsx` (모달 → 상세 페이지 전환)

---

## 4. 남은 과제 (내일 이어서)

### 4.1 우선순위 후보
| # | 작업 | 영역 | 의존성 |
|---|------|-----|--------|
| **A** | **Service Registry 백엔드** (MySQL + CRUD API) | BE | 없음 |
| **B** | Agent 등록 폼 `/agent-store/new` | FE | A 있으면 좋음 |
| **C** | ExternalAgentWorker + MISO Adapter (동기 호출) | BE | A 필요 |
| **D** | Intent Router 동적 확장 (설치된 Agent 기반) | BE | A + C 필요 |
| **E** | RPA Adapter + Callback + Job 추적 | BE | A + C 필요 |
| **F** | Runner (Windows EC2 Python/PAD 실행) | BE + DevOps | E 필요 |

**권장 순서**: A → (A+B 묶음) → C (첫 실제 동기 Agent 호출로 Phase 1 "킬러 유즈케이스" 체감 확보) → D → E → F

### 4.2 미결정 사항
- **자격증명 정책** (과제 3) — Runner 기반 Agent가 caller 권한으로 돌지, service_account 권한으로 돌지. 조직 보안 정책 엮임. 따로 떼서 논의 필요.
- **Workspace 파일 전달** (과제 4) — Lucid 파일 저장소 → Agent 전달 메커니즘 (presigned URL vs 인라인)
- **스케줄 Workspace 컨텍스트** (과제 5) — APScheduler에 workspace_id 축 추가 방식
- **공개 범위 승인 절차** — Public 공개 시 관리자 리뷰 필요 여부

### 4.3 Phase N-2 (알림 인프라 백엔드)
- `user_notifications` DB 테이블 설계 + CRUD API
- 스케줄/동기 Agent 완료 시 INSERT (읽음 상태 서버 동기화)
- 실시간 푸시 (WebSocket/SSE) 필요 여부 검토
- 현재 localStorage `lucid-inbox-read` → 백엔드 이관

### 4.4 Agent Store 보완
- 등록 폼 `/agent-store/new` — 현재는 `handleGoNew()` → "준비 중" toast
- `isInstalled` 상태 localStorage 영속화 (현재 세션마다 초기화)
- Agent Store와 Workspace의 설치 상태 동기화 (한쪽에서 설치하면 다른 쪽에도 반영)

### 4.5 부작용 검토 후속
- 여러 Agent 붙었을 때 Intent 충돌·응답 경합 등 실제 동작은 P2 이후 실측
- 현재는 정적 경고 UI만 — 실제 라우팅 로직 연결 시 검증 필요

---

## 5. 기술/설계 노트

### 5.1 Mock 데이터 전략
- 10개 Agent가 **6종 플랫폼을 모두 커버**하도록 배치 — 프론트 UX 검증용
- `isInstalled: true`인 Agent 5개 (내 알림/Picker 테스트용)
- `isMine: true`인 Agent 2개 (My Creations 탭 테스트용)
- 상태 혼합: `active` 7개, `maintenance` 1개, `inactive` 1개, `active` 2개 (mine, private)

### 5.2 localStorage 키 체계
| 키 | 용도 |
|---|-----|
| `ws_agents_{workspace_uuid}` | Workspace에 붙은 Agent id 배열 |
| `lucid-inbox-read` | 알림함 읽은 항목 id Set |
| (기존) `lucid-ai-notifications-dismissed:{YYYY-MM-DD}` | 데일리 브리핑 오늘 닫기 |
| (기존) `whats-new-seen-{id}` | WhatsNew 읽은 공지 |

→ 백엔드 이관 시 `ws_agents_*`는 `workspace_agents` 테이블로, `lucid-inbox-read`는 `user_notifications.read_at`으로.

### 5.3 설계서와의 정합
최신 설계서 [루시드AI_Hub_아키텍처_설계서.md](../루시드AI_Hub_아키텍처_설계서.md) (2026-04-06 v1.0)의:
- §5.4 "사용자별 활성 액션" → **P1에서 구현됨** (설치 + Workspace 활성화)
- §3.3 action.yaml 매니페스트 → **BE 작업 시 DB 스키마로 반영 예정**
- §6 액션 라우팅 → **Phase 2 Intent Router 확장과 일치**
- §4 Runner → **Phase 3/4에서 작업**

### 5.4 알림함 확장성
현재 `InboxItem.type`이 `schedule_done / async_done / sync_done / mail / approval / announcement / system`으로 7가지. 새 유형 추가는 provider의 mock 배열에 추가하고 inbox-drawer iconMap에 아이콘만 매핑하면 됨. 2탭 구조가 답답해지면 single-feed + filter chips로 진화 예정 (옵션 C 보류분).

---

## 6. 내일 바로 시작 가능한 항목

**권장 시작**: 옵션 **A (Service Registry 백엔드)**
- 이유: 모든 후속 작업의 기반, 프론트와 독립 작업 가능
- 구체 작업:
  1. `backend/migrations/add_agent_store.sql` — `service_registry` / `user_actions` / `runners` / `action_executions` 테이블
  2. `backend/app/services/service_registry_service.py` — CRUD 로직
  3. `backend/app/api/routes/agent_store.py` — REST 엔드포인트
  4. 프론트 `lib/api/agent-store.ts` — API 클라이언트 (mock → 실제 교체)

**대안**: 옵션 **B (등록 폼)**을 먼저 프론트 단독으로 만들기
- 백엔드 스키마 확정 전이라도 등록 UX 그림을 미리 볼 수 있음
- 단, 재작업 가능성 있음 (스키마 변경 시)

---

*세션 종료: 2026-04-17*
*다음 세션에서 이 문서 참고하여 이어서 진행*

# 02. 데이터 모델

> **목적**: Hub가 요구하는 영속 데이터의 전체 지도. 테이블 단위로 소유자, 관계, 생명주기를 명시한다. **Phase 1 범위만 확정**, Phase 2~3은 도입 시점에 재설계.

## 범위

- In scope: MySQL 신규 테이블, 기존 테이블 확장, 스키마 이관 경로
- Out of scope: ChromaDB/SQLite 내부 구조 (기존 그대로)

## 설계 의존성

- [01_terminology.md](01_terminology.md) ✅ 완료 — 테이블명/필드명 결정 근거
- [03_manifest_spec.md](03_manifest_spec.md) → `agents.manifest` JSON 컬럼 구조
- [04_registration_flow.md](04_registration_flow.md) → 검증·승인 워크플로우의 데이터 모델 적용

---

## ✅ 확정: Phase 1 테이블 8개

| # | 테이블 | 역할 |
|---|--------|------|
| 1 | `agents` | 에이전트 카탈로그 (메타/플랫폼/공개범위/상태) |
| 2 | `user_agents` | 사용자별 설치/활성화 (Active Agents 리스트 소스) |
| 3 | `workspace_agents` | 워크스페이스에 붙은 에이전트 매핑 |
| 4 | `agent_review_reports` | AI 자동 검증 리포트 (퀄리티/보안) |
| 5 | `agent_approvals` | 인간 최종 승인 결정 |
| 6 | `agent_executions` | 실행 이력 (감사·디버깅·통계) |
| 7 | `user_notifications` | 알림함 (스케줄/async 완료 push) |
| 8 | `runners` | Runner EC2 등록 (4대 본부별, 기존 RPA 자산 흡수) |

### 제외/보류

| 테이블 | 사유 |
|--------|------|
| ~~`user_agent_favorites`~~ | 즐겨찾기 불필요 (사용자 결정) |
| ~~`agent_versions`~~ | Phase 1은 `agents.version` 컬럼만. 별도 테이블은 Phase 2 재검토 |
| ~~`agent_reviews(별점)`~~ | 사용자 평가/리뷰 시스템은 Phase 2 이후 |
| `agent_credentials` | Phase 1은 **AWS SSM Parameter Store**(무료) 활용, DB 테이블 X. Phase 2 = AWS Secrets Manager 점진(자동 회전 필요 시) |
| `connectors` | Phase 2~3 (Connector 카탈로그 도입 시점) |
| `agent_connectors` | Phase 2~3 (Agent에 붙은 Connector 매핑) |

---

## ER 개요

```
                            ┌──────────────────┐         ┌──────────────────┐
                            │     agents       │────────▶│     runners      │
                            │  (카탈로그)       │ runner_id│ (EC2 4대 본부별) │
                            └─────────┬────────┘         └──────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
   ┌────▼─────────┐         ┌─────────▼──────────┐        ┌─────────▼──────────┐
   │ user_agents  │         │ workspace_agents   │        │agent_review_reports│
   │ (설치/활성화)│         │  (워크스페이스 부착)│        │   (AI 자동 검증)   │
   └──────────────┘         └────────────────────┘        └─────────┬──────────┘
        │                             │                             │
   ┌────▼──────────┐         ┌────────▼─────────┐         ┌─────────▼──────────┐
   │   users       │         │    workspaces    │         │   agent_approvals  │
   │  (기존)       │         │     (기존)       │         │   (인간 승인 결정) │
   └───────────────┘         └──────────────────┘         └────────────────────┘

                            ┌──────────────────┐
                            │ agent_executions │
                            │   (실행 이력)    │
                            └─────────┬────────┘
                                      │
                            ┌─────────▼──────────┐
                            │ user_notifications │
                            │     (알림함)        │
                            └────────────────────┘
```

**관계 요약**:
- `agents` 1:N `user_agents`, `workspace_agents`, `agent_review_reports`, `agent_executions`
- `agents` N:1 `runners` (Runner 플랫폼 Agent만, nullable)
- `agent_review_reports` 1:N `agent_approvals` (한 리포트에 재승인 가능)
- `agent_executions` 1:0..N `user_notifications` (스케줄/async 완료 시만)

---

## 테이블 명세 (컬럼 디테일은 다음 단계)

### 1. `agents` — 카탈로그

**역할**: 등록된 모든 Agent의 메타데이터.

**컬럼 확정** (자주 쿼리되는 것만 정규화 + 매니페스트 디테일은 JSON):
- `id` (UUID PK)
- `slug` (URL friendly, UNIQUE)
- `name`, `description`, `icon`
- `tags` (JSON)
- `author_user_id`, `author_team`
- `platform` (enum: `native` / `miso` / `runner` / `webhook`) — 정규화 (필터링 빈번)
- `capabilities` (JSON array: `chat` / `run` / `scheduled` / `async`) — JSON (다중)
- `visibility` (enum: `private` / `team` / `public`) — 정규화
- `status` (enum: `draft` / `pending_review` / `active` / `maintenance` / `disabled` / `deleted`) — 정규화
- `version` (semver string)
- `manifest` (JSON) — `inputs` / `output` / `runtime` / `triggers` / `requires` 디테일 보관
- `install_count` (INT) — denormalize 카운터, **트리거 대신 `user_agents` INSERT/DELETE 시 애플리케이션 레벨 갱신**
- `is_native_seed` (BOOL) — Native Agent seed 식별용 플래그
- `created_at`, `updated_at`

**Native Agent 처리**: 13개 Native Worker (DirectWorker 등) 모두 `agents` 테이블에 **seed row** 생성. 모든 사용자에게 `user_agents`에 자동 install (default `enabled=true`). seed Agent는 `is_native_seed=true`로 마크하여 일반 Agent 등록 흐름과 구분.

### 2. `user_agents` — 외부 Agent 설치/활성화 (Native 제외)

**역할**: 사용자가 설치한 **외부 Agent** (MISO/Runner/Webhook) 추적. **Native Agent는 포함하지 않음**.

**컬럼 확정**:
- `user_id`, `agent_id` (복합 PK)
- `enabled` (BOOL, default true) — 일시 비활성화 (uninstall 안 하고 끌 때)
- `installed_at`
- `last_used_at` (DATETIME, nullable) — 실행 시 애플리케이션 레벨 갱신 (정렬용)

**Native Agent 처리 정책 (재정의 — AD 인증 환경)**

> AD/LDAP 자동 인증으로 회원가입 시점이 없으므로, Native Agent는 **DB row 없이 코드/카탈로그 레벨에서 모든 사용자에게 자동 활성화**된다.

- Native Agent는 `agents` 테이블 카탈로그 row만 존재 (`is_native_seed=TRUE`)
- `user_agents`에 INSERT **하지 않음**
- "Active Agents" 리스트 계산 = `agents WHERE is_native_seed=TRUE` ∪ `user_agents WHERE user_id=? AND enabled=TRUE`
- 신규 사용자 가입 hook 불필요 (AD 인증으로 첫 진입 시 자동 인식)
- 사용자별 Native on/off는 Phase 1 요구사항 아님 (필요 시 Phase 2에 별도 `user_native_disabled` 테이블 추가 검토)

**근거**:
- 18개 Native × 수백 명 = 수천 row 불필요한 누적 회피
- Native는 코드 배포로 모든 사용자 동일 노출이 본질
- AD 환경에 hook 걸 시점 없음 — lazy install/login hook 모두 부자연

### 3. `workspace_agents` — 워크스페이스 부착

**역할**: 4-17 localStorage `ws_agents_{uuid}`의 백엔드 이관. 워크스페이스에 붙은 Agent 매핑.

**주요 컬럼 후보**:
- `workspace_id`, `agent_id` (복합 PK)
- `attached_at`, `attached_by_user_id`

**결정 필요**:
- [ ] 워크스페이스에 붙이려면 `user_agents` 설치가 선행돼야 하나? (UX 정책)

### 4. `agent_review_reports` — AI 자동 검증 리포트

**역할**: Agent 등록/버전업 시 자동 트리거되는 검증 결과. 한 Agent에 N개 (재검증 가능).

**주요 컬럼 후보**:
- `id` (UUID PK)
- `agent_id`, `agent_version` (어떤 버전 검증)
- `review_round` (재검증 라운드 번호)
- `category` (enum: `quality` / `security`) — Phase 1은 2종, 추후 확장
- `reviewer_kind` (enum: `auto`) — 자동 검증만. 인간은 `agent_approvals`로
- `reviewer_id` (검증 시스템 식별자, 예: "validator-v1")
- `score` (0~100 또는 NULL)
- `severity_max` (enum: `info` / `warn` / `error` / `critical`)
- `findings` (JSON: `[{severity, category, message, location?, suggestion?}]`)
- `status` (enum: `passed` / `warnings` / `failed`)
- `created_at`, `completed_at`

**결정 필요**:
- [ ] `category` enum vs string (확장성)
- [ ] findings JSON 스키마 표준화
- [ ] 검증 시스템 자체 구현 — 04에서 다룸 (Native Agent? 별도 서비스?)

### 5. `agent_approvals` — 인간 승인 결정

**역할**: AI 리포트를 본 인간 검토자가 내리는 최종 결정.

**컬럼 확정**:
- `id` (UUID PK)
- `agent_id`, `agent_version`
- `report_ids` (JSON array — 검토 시 본 리포트 N개의 id)
- `approver_user_id` — **operator 권한자만** (`NEXT_PUBLIC_OPERATOR_USERS`, 현재 A2304013)
- `decision` (enum: `approved` / `rejected` / `request_changes`)
- `comment` (TEXT)
- `decided_at`

**승인자 권한**: Phase 1은 **operator role**(현재 A2304013 단독). 검토자 풀이 늘어나면 별도 `reviewer_role` 신설은 Phase 2에 검토.

**재제출 처리**: `request_changes` 후 작성자가 수정 → 새 `agent_review_reports` 생성 → 새 `agent_approvals` row 추가 (기존 row 업데이트 X). 결정 히스토리 보존.

**TBD (04에서 결정)**:
- [ ] private/team Agent도 승인 필수인가, public만 게이팅인가

### 6. `agent_executions` — 실행 이력

**역할**: 모든 Agent 실행의 감사 로그. 디버깅, 통계, 보안 감사용.

**주요 컬럼 후보**:
- `id` (UUID PK)
- `agent_id`, `agent_version`
- `user_id`, `workspace_id` (nullable), `session_id` (nullable, chat_sessions 참조)
- `input_args` (JSON)
- `output_summary` (TEXT, 요약본 — 큰 결과는 별도 저장소)
- `status` (enum: `pending` / `running` / `success` / `failed` / `timeout` / `cancelled`)
- `error_message` (TEXT)
- `started_at`, `completed_at`, `execution_time_ms`

**결정 필요**:
- [ ] 보관 기간 정책 (90일? 1년?) — 파티셔닝 전략
- [ ] output 큰 파일(xlsx 등)은 어디에 — 기존 `file_archive` 활용?
- [ ] PII 마스킹 정책 (input/output에 사번, 이메일 포함 시)

### 7. `user_notifications` — 알림함

**역할**: 4-17 §1.8 알림함 인프라. 스케줄/async Agent 완료 시 INSERT, 사용자가 읽음 처리.

**컬럼 확정**:
- `id` (UUID PK)
- `user_id`
- `type` (enum: `schedule_done` / `async_done` / `sync_done` / `mail` / `approval` / `announcement` / `system`)
- `title`, `body`
- `agent_id` (nullable), `execution_id` (nullable, agent_executions 참조)
- `link_url` (클릭 시 이동 경로)
- `read_at` (NULL = unread)
- `created_at`

**보관 정책**: **90일 hard delete** (배치 잡으로 매일 cleanup). 보안 감사 필요한 정보는 `agent_executions`에 별도 보관되므로 알림함은 짧게 가도 무방.

**TBD**:
- [ ] 푸시 채널 — Phase 1은 인앱만(API 폴링). WebSocket/SSE/이메일 fan-out은 Phase 2 검토

---

### 8. `runners` — Runner EC2 등록

**역할**: Runner 플랫폼 Agent가 실행되는 EC2 인스턴스 정보. 4대 RPA 자산 흡수.

**컬럼 확정**:
- `id` (UUID PK)
- `name` (예: "CPO본부 Runner")
- `ec2_instance_id` (예: "i-0abc...")
- `labels` (JSON array: 예 `["cpo", "sap-fi", "office", "production"]`)
- `responsible_dept_groups` (JSON array: 본부명 — 예 `["CPO"]`) — IT 수동 매핑
- `status` (enum: `online` / `offline` / `busy` / `maintenance`)
- `last_heartbeat` (DATETIME)
- `auth_token_hash` (Runner 인증)
- `efs_mount_path` (선택, 매크로 파일 EFS 외부화 시) — Phase 1 nullable
- `created_at`, `updated_at`

**Phase 1 초기 데이터 (4대)**:
| name | labels | responsible_dept_groups |
|------|--------|------------------------|
| CPO본부 Runner | `["cpo", "sap", "office", "mes"]` | `["CPO"]` |
| 영업/마케팅 Runner | `["sales", "office", "crm"]` | `["L3=17"]` (실명 후속 확인) |
| CFO본부 Runner | `["cfo", "sap-fi", "office"]` | `["CFO"]` |
| 공통/감사 Runner | `["shared", "office"]` | `["감사실", "L3=643", "직속"]` |

**라우팅**: Agent의 `manifest.runtime.required_labels`가 Runner의 `labels`에 모두 포함되는지 매칭. 같은 라벨 가진 Runner 여러 대일 때만 부하 분산 (Phase 2~3에 ASG 도입 시).

**TBD**:
- [ ] EFS 외부화 도입 시점 (Phase 1 = 디스크, Phase 2~3 = EFS)
- [ ] 엘앤에프플러스 위치 확정 후 Runner 추가 여부

## 마이그레이션 전략

- 신규 8개 테이블 → `backend/migrations/add_agent_hub_phase1.sql` 단일 마이그레이션 파일
- 기존 4-17 localStorage 이관:
  - `ws_agents_{workspace_uuid}` → `workspace_agents` INSERT 스크립트
  - `lucid-inbox-read` → `user_notifications.read_at` (id 기반 매칭, 가능한 항목만)
- Native Agent seed:
  - 18개 Native Worker → `agents` INSERT (`is_native_seed=true`)
  - **`user_agents` INSERT 안 함** (Native는 코드 레벨 자동 활성화, 위 §2 참조)
- 외래키 제약 — **모두 ON DELETE RESTRICT**:
  - hard delete 금지. soft delete (`agents.status='deleted'`)만 사용
  - 진짜 hard delete가 필요하면 관리자 별도 작업 (수동 cleanup 스크립트)
  - 기존 `users` / `workspaces` / `chat_sessions` 테이블과의 FK 추가

## 참고

- [00_vision.md §10.2](00_vision.md) — 4-06 초안 (`actions`, `runners`, `action_executions`)
- [2026-04-17 §4.3](../history/2026-04-17_AgentStore_Workspace_Inbox.md) — 알림함 백엔드 이관 과제
- [backend/migrations/](../../backend/migrations/) — 기존 마이그레이션 컨벤션 (특히 `add_workspace_memory.sql`)

## 체크리스트

- [x] Phase 1 테이블 목록 확정 — 7개
- [x] 즐겨찾기/별점 시스템 제외 결정
- [x] AI 검증 + 인간 승인 2테이블 분리 결정
- [x] ER 개요 1차 확정
- [x] manifest 정규화 정책 확정 — **자주 쿼리는 정규화 + 디테일 JSON**
- [x] Native Agent seed 정책 확정 — **agents 테이블에 row + 자동 install**
- [x] 외래키 정책 확정 — **모두 RESTRICT, soft delete만 사용**
- [x] 승인자 권한 확정 — **operator role**
- [x] 알림 보관 기간 확정 — **90일 hard delete**
- [x] `runners` 테이블 Phase 1 포함 확정 — **4대 본부별 매핑 (CPO/Sales/CFO/Shared)**
- [x] 부서→Runner 매핑 정책 확정 — **IT 수동 매핑 + 라벨 자동 라우팅**
- [ ] 각 테이블 컬럼 타입/길이 디테일
- [ ] 보관 기간/파티셔닝 정책 (`agent_executions`)
- [ ] PII 마스킹 정책 (`agent_executions.input_args`)
- [ ] 마이그레이션 SQL 파일 작성

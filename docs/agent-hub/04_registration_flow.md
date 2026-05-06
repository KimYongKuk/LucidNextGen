# 04. 등록 플로우

> **목적**: Agent 라이프사이클 — 등록/검증/승인/편집/비활성/삭제 — 와 각 단계의 UI/검증/통지 규칙.

## 범위

- In scope: Agent 등록 UI 진입, AI 검증 + 인간 승인, 편집/버전, soft delete
- Out of scope: 라우팅 (→ [05](05_routing.md)), Runner 통신 규격 (→ [06](06_runner_protocol.md)), 자격증명 저장소 (→ [07](07_security.md))

## 설계 의존성

- [01_terminology.md](01_terminology.md) ✅ 페르소나 (Phase별)
- [02_data_model.md](02_data_model.md) ✅ `agents`, `agent_review_reports`, `agent_approvals`
- [03_manifest_spec.md](03_manifest_spec.md) ✅ 매니페스트 스키마

---

## ✅ 확정: 라이프사이클 상태

```
draft ──submit──▶ pending_review ──[AI검증]──▶ pending_approval ──[인간승인]──▶ active
                                       │                              │
                                       ▼                              ▼
                                    rejected                    request_changes
                                       │                              │
                                       └────── 수정 ◀─────────────────┘
                                                재제출

[active] ──작성자 일시중단──▶ [maintenance]
[active] ──관리자 강제중단──▶ [disabled]
[active|maintenance|disabled] ──삭제──▶ [deleted] (soft delete)
```

| 상태 | 설명 | 카탈로그 노출 | 실행 가능 |
|------|------|------------|----------|
| `draft` | 작성 중, 본인만 접근 | X | X |
| `pending_review` | AI 자동 검증 진행 중 | X | X |
| `pending_approval` | 인간 검토자 승인 대기 | X | X |
| `rejected` | 검증/승인 실패 → 작성자 수정 필요 | X | X |
| `active` | 정상 노출/실행 | ✅ | ✅ |
| `maintenance` | 작성자가 일시 중단 | ✅ ("점검중" 뱃지) | X |
| `disabled` | 관리자 강제 중단 | X | X |
| `deleted` | soft delete (hard delete 금지) | X | X |

---

## ✅ 확정: 등록 UI 진입

### 진입 화면 (`/agent-store/new`)

```
┌────────────────────────────────────────────────────────────────┐
│  어떤 종류의 Agent를 등록하시겠습니까?                          │
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ 🟦 MISO Agent    │  │ 🔒 Runner        │  │ 🌐 Webhook   │  │
│  │                  │  │                  │  │              │  │
│  │ MISO 빌더에서    │  │ EC2 매크로/PAD/  │  │ 외부 REST    │  │
│  │ 만든 Agent 등록  │  │ Python 등록      │  │ API 등록     │  │
│  │                  │  │                  │  │              │  │
│  │ [모든 사용자]    │  │ [IT operator만]  │  │ [개발자]     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
│                                                                │
│  ※ Native Agent는 코드 배포로만 등록됩니다.                     │
└────────────────────────────────────────────────────────────────┘
```

**규칙**:
- 권한 없는 카드 **disabled 노출** ("IT operator 권한 필요" 툴팁)
- Native는 카드 미포함 (코드 배포만)
- 클릭 → `/agent-store/new/{platform}` 위저드 이동

### 페르소나/Phase별 권한 게이팅

| Phase | MISO 카드 | Runner 카드 | Webhook 카드 |
|-------|----------|------------|--------------|
| 1 (지금) | 모든 사용자 | **operator만** | 개발자 role |
| 2 | 모든 사용자 | operator + 본부 협력자 (PAD만) | 개발자 + 일부 현업 |
| 3 | 모든 사용자 | + 일부 현업 (Excel VBA) | 광범위 개방 |

### 플랫폼별 등록 위저드

각 위저드 = **공통 메타 + 플랫폼별 runtime 입력**.

#### MISO 위저드 (`/agent-store/new/miso`)

1. **MISO Agent 가져오기**
   - MISO Studio URL 붙여넣기 → name/description 자동 추출
   - 또는 app_id 직접 입력
2. **공통 메타 확인/수정** (이름, 설명, 아이콘, 태그)
3. **mode 선택** (`agent` / `workflow`)
4. **공개범위** (private/team/public)
5. **트리거 (선택)** — cron 표현식
6. **제출** → `pending_review` 진입

#### Runner 위저드 (`/agent-store/new/runner`)

1. **executor 선택** (`pad` / `python` / `vbs` / `bat` / `ps1`)
2. **Runner 라벨 선택** (체크박스, `runners` 테이블에서 가용 라벨 목록)
3. **매크로 파일 업로드 또는 경로 입력** (EC2 디스크 기준)
4. **인자 정의** (`{{var}}` 템플릿)
5. **공통 메타 + 공개범위 + 트리거**
6. **제출** → `pending_review`

#### Webhook 위저드 (`/agent-store/new/webhook`)

1. **URL + 메소드** 입력
2. **인증 방식** 선택 (Bearer / API key / HMAC / None)
3. **인증 토큰** Hub Vault에 저장 (Phase 2부터, Phase 1은 `.env` 환경변수 ref)
4. **request_mapping / response_mapping** JSON 에디터
5. **공통 메타 + 공개범위 + 트리거**
6. **제출** → `pending_review`

---

## ✅ 확정: 검증 + 승인 워크플로우

### 흐름

```
[제출] → pending_review (AI 자동 검증 시작)
            │
            ▼
   ┌──────────────────────────────┐
   │  AgentValidatorService       │
   │  ├── 매니페스트 형식 검증     │
   │  ├── 보안 패턴 스캔          │
   │  └── LLM(Sonnet) 품질 평가   │
   └──────────────┬───────────────┘
                  │
        ┌─────────┼─────────┐
        ▼                   ▼
   [passed]            [failed/critical]
        │                   │
        ▼                   ▼
  pending_approval      rejected (작성자 알림)
        │
        ▼
   [operator 승인] → active
   [operator 반려] → rejected
   [operator 변경요청] → request_changes
```

### 검증 시스템 구현 위치

**별도 서비스 클래스**: `backend/app/services/agent_validator_service.py`

- 매 등록/버전업 시 비동기 백그라운드 작업으로 트리거
- Bedrock(Sonnet) 직접 호출
- Native Agent로 구현하지 않음 (단순성 + 메타 순환 방지)
- 결과를 `agent_review_reports`에 INSERT

### 검증 항목 (Phase 1)

| 카테고리 | 항목 | 차단 기준 |
|---------|------|----------|
| **quality** | 매니페스트 필수 필드 | 누락 시 자동 reject |
| quality | 입력 스키마 일관성 | 경고 |
| quality | description 명료성 (LLM 평가) | 경고 |
| **security** | 자격증명 평문 노출 | critical → 자동 reject |
| security | URL/endpoint 검증 (사내망/외부) | 경고 |
| security | (Runner) 매크로 파일 위험 패턴 (rm -rf, format 등) | critical |
| security | (Webhook) SSRF 가능 URL (10.x, 169.254.x) | critical |

### 검증 적용 범위

**모든 등록이 `pending_review` 거침 (Phase 1)**:
- private/team/public 무관
- 검증 시스템 신뢰성 축적 단계
- private도 SAP 자격증명 다룰 수 있어 검증 필요

### 인간 승인자

- **operator role** (`NEXT_PUBLIC_OPERATOR_USERS` — 현재 A2304013)
- 승인 큐 화면: `/admin/agent-store/approvals` (별도 페이지)
- 승인 결정: `agent_approvals` INSERT
- 알림: 작성자에게 결과 통지 (`user_notifications`)

---

## ✅ 확정: 편집 / 버전 관리 (Phase 1)

### 편집 시 동작

- 편집 = `agents.version` semver patch 자동 증가 (1.0.0 → 1.0.1)
- 매니페스트 변경 → 새 `pending_review` 진입 (재검증)
- 승인 통과 시 `active` 상태 유지, `version` 갱신
- **Phase 1은 이전 버전 보존 X** (in-place 갱신, `agents` row 그대로)

### 자동 업그레이드 정책

- 기존 설치자(`user_agents`)는 자동으로 새 버전 사용
- Major 버전 변경(1.x → 2.x) 시 입력 스키마 호환성 깨질 수 있음 → **Phase 2에 호환성 검사 + 사용자 확인 다이얼로그**
- Phase 1은 단순 자동 적용

### 버전 이력 (Phase 2 이후)

- `agent_versions` 별도 테이블 도입
- 이전 버전으로 롤백 가능
- 사용자별 고정 버전 선택 가능

---

## ✅ 확정: 삭제 정책

### Soft Delete만 (hard delete 금지)

- `agents.status = 'deleted'` 로 변경
- 카탈로그 비노출 + 신규 실행 불가
- `agent_executions`, `agent_review_reports`, `agent_approvals` 모두 보존 (감사)
- `user_agents`, `workspace_agents` row 보존 (참조 유지)

### 복구

- operator 권한자가 `deleted` → `disabled` 또는 `active` 변경 가능
- 상태 변경 이력은 [02 `agent_review_reports` 또는 별도 audit] — TBD

### Hard Delete

- 관리자 별도 작업 (수동 cleanup 스크립트)
- 통상 운영에선 발생 X

---

## 매니페스트 검증 로직 (구체화)

[03 §매니페스트 검증](03_manifest_spec.md) 항목을 `AgentValidatorService` 안에서:

1. **JSON Schema 검증** — 03의 공통 필드 + platform별 runtime 스키마
2. **slug 중복 체크** — `agents.slug UNIQUE`
3. **runtime 일관성** — `platform` 값과 `runtime.platform` 일치
4. **Runner 라벨 매칭** — `required_labels` 모두 포함하는 `runners` row 존재
5. **cron 유효성** — `croniter` 라이브러리로 파싱
6. **매크로 파일 존재** (Runner) — Runner에 SSH/agent로 파일 존재 확인
7. **endpoint reachability** (Webhook/MISO) — 등록 시 1회 ping (선택)

---

## 참고

- [00_vision.md §5](00_vision.md) — 등록 흐름 초안
- [2026-04-17 §4.4](../history/2026-04-17_AgentStore_Workspace_Inbox.md) — 등록 폼 미구현
- [frontend/components/agent-store/agent-store-content.tsx:101](../../frontend/components/agent-store/agent-store-content.tsx#L101) — 현재 "준비 중" toast

## 체크리스트

- [x] 라이프사이클 상태 확정 (8개 상태)
- [x] 등록 UI 진입점 확정 (페르소나별 카드 + disabled 노출)
- [x] 플랫폼별 위저드 윤곽 확정 (MISO/Runner/Webhook)
- [x] 검증 시스템 위치 확정 — `AgentValidatorService` 별도 서비스 클래스
- [x] 검증 적용 범위 확정 — **모든 등록 `pending_review` 거침**
- [x] 인간 승인자 권한 확정 — **operator role 단독**
- [x] 편집/버전 정책 확정 — **새 버전 생성, 자동 업그레이드, 이력 보존 X (Phase 1)**
- [x] 삭제 정책 확정 — **soft delete만**
- [ ] 위저드 UI 와이어프레임 (구현 시점에 디자인)
- [ ] AgentValidatorService 구체 검증 룰 (구현 시점에 정의)
- [ ] 승인 큐 화면 와이어프레임 (구현 시점에 디자인)

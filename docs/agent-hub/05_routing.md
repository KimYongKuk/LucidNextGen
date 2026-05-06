# 05. 라우팅

> **목적**: 사용자 발화 → 어떤 Agent를 실행할지 결정. 기존 Intent Router를 워크스페이스 단위로 격리 확장.

## 범위

- In scope: 워크스페이스 컨텍스트별 Agent 매칭, 시스템 프롬프트 합성, 실행 전 확인 UX
- Out of scope: 등록 흐름 (→ [04](04_registration_flow.md)), Agent 실행 자체 (→ [06](06_runner_protocol.md))

## 설계 의존성

- [01_terminology.md](01_terminology.md) ✅ Workspace = 컨테이너
- [02_data_model.md](02_data_model.md) ✅ `workspace_agents`
- [03_manifest_spec.md](03_manifest_spec.md) ✅ `intent_hints`, `capabilities`

---

## ✅ 확정: Workspace 격리 라우팅

### 핵심 원칙

> **일반 채팅 = Native Agent만**, **Workspace 채팅 = Native + 부착된 Agent**

```
[일반 채팅 (Workspace 없음)]
   사용자 발화
       │
       ▼
   기존 Intent Router (Native Worker만 후보)
       │
       └── DirectWorker / WebSearchWorker / MailWorker / ... 13개
       
[Workspace 채팅 (workspace_id 있음)]
   사용자 발화
       │
       ▼
   확장 Intent Router
       │
       ├── Native Worker 13개
       └── workspace_agents[workspace_id]  ← 사용자가 부착한 Agent (MISO/Runner/Webhook)
            │
            └── 워크스페이스 시스템 프롬프트 = Agent들의 intent_hints 합성
```

### 격리의 효과

- **일반 채팅 라우팅 단순**: 18개 Native만 후보, 기존 quick_classify + Haiku 분류 그대로
- **사용자가 만든 Agent 격리**: 200개 등록되어 있어도 일반 채팅 후보 풀에 X
- **워크스페이스 = Agent 사용 컨테이너**: 사용자가 의식적으로 워크스페이스 만들어 Agent 부착
- **부작용 0**: 4-17 §1.4 "Workspace = Agent 컨테이너" 관점 그대로 실현

### Active Agents 리스트 계산 (Native = 코드 활성화)

AD 인증 환경 정책에 따라 Native는 `user_agents` 없이 자동 활성화:

```sql
-- 사용자의 Active Agents = Native(전체) ∪ 사용자가 설치한 외부 Agent
SELECT * FROM agents
WHERE status = 'active'
  AND (
    is_native_seed = TRUE   -- Native: 모든 사용자에게 자동 활성
    OR id IN (
      SELECT agent_id FROM user_agents
      WHERE user_id = ? AND enabled = TRUE
    )
  );
```

→ 02 §2 결정 그대로. `user_agents`엔 외부 Agent(MISO/Runner/Webhook)만 row 보관.

---

## ✅ 확정: 빠른 워크스페이스 생성 UX

### 진입 동선

Agent Store 카탈로그에서 Agent 카드 클릭 시:

```
┌───────────────────────────────────────────────────┐
│  📊 월간 매출 리포트                              │
│  ERP 매출 데이터를 추출하여 엑셀 보고서 자동 생성  │
│                                                   │
│  [이 Agent로 워크스페이스 만들기 →]               │
│  [내 워크스페이스에 추가...] (드롭다운)            │
└───────────────────────────────────────────────────┘
```

**"이 Agent로 워크스페이스 만들기"** 클릭 시:

1. 새 워크스페이스 자동 생성
   - 이름: Agent 이름 + " Workspace" (편집 가능)
   - 시스템 프롬프트: Agent의 `intent_hints.system_prompt` 자동 주입
   - `workspace_agents` INSERT (해당 Agent 부착)
2. 워크스페이스 진입 → 즉시 채팅 시작 가능

### 시스템 프롬프트 자동 합성

워크스페이스에 부착된 Agent N개의 `intent_hints.system_prompt`를 합성:

```python
def compose_workspace_system_prompt(workspace_id):
    base = "당신은 {workspace_name}에서 일하는 어시스턴트입니다.\n\n"
    base += "# 사용 가능한 Agent 가이드:\n"
    
    for agent in get_workspace_agents(workspace_id):
        if agent.manifest.intent_hints?.system_prompt:
            base += f"\n## {agent.name}\n"
            base += agent.manifest.intent_hints.system_prompt
    
    # 사용자 정의 워크스페이스 프롬프트도 합성
    if workspace.custom_prompt:
        base += f"\n\n# 추가 지침:\n{workspace.custom_prompt}"
    
    return base
```

→ 사용자 발화 시 LLM(Sonnet)이 이 프롬프트를 컨텍스트로 받아서 적절한 Agent 선택.

---

## 라우팅 로직 (Phase 1)

### 일반 채팅 (workspace_id 없음)

기존 그대로 (변경 X):

```
사용자 발화
  ↓
Phase 1: quick_classify (정규식, 즉시) → 매칭되면 Native Worker 직행
  ↓ 실패
Phase 2: LLM 분류 (Haiku) → Native Worker 13개 중 선택
  ↓
Worker 실행
```

### 워크스페이스 채팅 (workspace_id 있음)

```
사용자 발화 + workspace 컨텍스트
  ↓
Phase 1: quick_classify (정규식) → Native Worker 우선 매칭
  ↓ 실패
Phase 2: LLM 분류 (Sonnet)
  - 시스템 프롬프트 = compose_workspace_system_prompt(workspace_id)
  - 후보 = Native Worker + workspace_agents
  - LLM이 어느 Agent를 부를지 선택 + 입력 추출
  ↓
실행 전 확인 UX (선택, 아래 참조)
  ↓
Agent 실행
```

**모델 선택**:
- Native Worker 13개만 = Haiku (빠름)
- 워크스페이스에 외부 Agent 부착 시 = Sonnet (시스템 프롬프트 길어지고 추론 복잡)

---

## 실행 전 확인 UX

되돌리기 어려운 작업(파일 생성, 외부 시스템 호출, Runner 매크로) = 실행 전 확인 단계.

### 확인 다이얼로그 패턴

```
┌──────────────────────────────────────────────────┐
│  「월간 매출 리포트」 Agent를 실행할까요?         │
│                                                  │
│  입력 파라미터:                                   │
│  - 대상 연월: 2026-04                             │
│  - 공장: 서울공장                                 │
│                                                  │
│  실행 위치: ec2-cpo-01 (CPO본부 Runner)           │
│  예상 소요: 약 3분                                │
│                                                  │
│  [실행] [취소] [파라미터 수정]                    │
└──────────────────────────────────────────────────┘
```

### 확인 적용 기준

| Capability | 확인 단계 |
|-----------|----------|
| `chat` (대화형) | 확인 X (즉시 실행) |
| `run` (실행형) | **확인 필수** (입력 파라미터 프리뷰) |
| `scheduled` | 라우팅 대상 X (자동 실행만) |
| `async` | 확인 후 "백그라운드 실행 + 알림" 안내 |

### Phase 1 단순화

- `chat` capability 위주 — 확인 X
- `run`/`async` Agent 부착 시만 다이얼로그
- `scheduled` 미노출 (자동 실행 결과는 알림함으로만)

---

## 충돌 해결

### 활성 Agent 2개가 동시 매칭되면?

LLM(Sonnet) 응답에 confidence 함께 받아서:
- 1개 Agent confidence ≥ 0.8 → 그 Agent 실행
- 2개 이상 confidence ≥ 0.7 → 사용자에게 선택 다이얼로그
- 모두 < 0.7 → Native Worker 폴백 (DirectWorker)

### 4-17에서 정의한 경고 — 라우팅 측면 대응

- 대화형 Agent 3개 이상 부착 → 매칭 다이얼로그 자주 발생 가능 (워크스페이스 설정에 경고)
- 활성 Agent 8개 이상 → 시스템 프롬프트 길어져 비용 증가, Sonnet 강제

---

## 참고

- [00_vision.md §6](00_vision.md) — 라우팅 초안
- [2026-04-17 §1.5](../history/2026-04-17_AgentStore_Workspace_Inbox.md) — 횡단 과제 #6
- [backend/app/agents/intent_classifier.py](../../backend/app/agents/intent_classifier.py) — 기존 구현
- [backend/app/services/memory_service.py](../../backend/app/services/memory_service.py) — 워크스페이스 시스템 프롬프트 합성에 메모리도 함께

## 체크리스트

- [x] Workspace 격리 모델 확정
- [x] 빠른 워크스페이스 생성 UX 확정
- [x] 시스템 프롬프트 자동 합성 로직 정의
- [x] 일반 채팅 vs 워크스페이스 채팅 라우팅 분기
- [x] 모델 선택 (Haiku/Sonnet) 정책
- [x] 실행 전 확인 UX 패턴
- [ ] 다중 Agent confidence 임계값 미세 조정 (구현 시점)
- [ ] 워크스페이스 시스템 프롬프트 토큰 길이 제한 (구현 시점)

# 07. 보안

> **목적**: Agent 등록·실행 전반의 자격증명, 권한, 공개범위 승인, 감사 로그 정책.

## 범위

- In scope: 자격증명 저장·전달, 실행 권한, 검증·승인, 사번 위조 방지, 감사
- Out of scope: 네트워크/방화벽 구성, SSO 자체 정책

## 설계 의존성

- [02_data_model.md](02_data_model.md) ✅ `agent_executions`, `agent_review_reports`, `agent_approvals`
- [03_manifest_spec.md](03_manifest_spec.md) ✅ `runtime.auth_ref`
- [04_registration_flow.md](04_registration_flow.md) ✅ AgentValidatorService, operator 승인
- [06_runner_protocol.md](06_runner_protocol.md) ✅ Runner 인증

---

## ✅ 확정: 자격증명 저장 — AWS SSM Parameter Store (Phase 1)

### 결정

| Phase | 저장소 | 근거 |
|-------|-------|------|
| **Phase 1** | **AWS SSM Parameter Store** (Standard) | 무료, AWS 표준, IAM 통합. 시크릿 ~10개 수준에 충분 |
| Phase 2 | **AWS Secrets Manager** | 자동 회전 필요 시 점진 이전 |

### 키 네임스페이스

```
/lucid-hub/
├── miso/
│   └── api-key                  ← MISO API key (전사 1개)
├── runner/
│   └── auth-token/{runner_id}   ← Runner별 인증 토큰
├── webhook/
│   └── {agent_slug}/auth        ← Webhook Agent별 자격증명
└── sap/
    ├── finance/{user_id}        ← SAP 자격증명 (부서별)
    └── manufacturing/{user_id}
```

### 매니페스트의 `auth_ref` 형식

```yaml
runtime:
  auth_ref: "ssm:/lucid-hub/miso/api-key"
```

→ Hub가 실행 시점에 SSM에서 fetch + 일회성 주입.

### 접근 제어

- Hub Backend EC2/ECS에 IAM Role 부여
- IAM Policy: `ssm:GetParameter` for `/lucid-hub/*`
- Runner는 Hub로부터 받은 자격증명만 사용 (직접 SSM 접근 X — 보안 표면 축소)

---

## ✅ 확정: 사번 위조 방지

### 패턴 — 기존 `prepare_tools()` 재사용

기존 Mail/Approval/LFON Worker에서 검증된 패턴:

```python
def prepare_tools(self, all_tools, context):
    user_id = context["user_id"]  # SSO 세션에서 자동 주입
    
    for tool in all_tools:
        original_ainvoke = tool.ainvoke
        
        async def secured_ainvoke(input_data, config=None, *, _user_id=user_id, _orig=original_ainvoke):
            # employee_number를 args에 강제 주입 (LLM이 위조해도 덮어씀)
            if "args" in input_data:
                input_data["args"]["employee_number"] = _user_id
            return await _orig(input_data, config)
        
        object.__setattr__(tool, "ainvoke", secured_ainvoke)
        object.__setattr__(tool, "_unwrapped_ainvoke", original_ainvoke)
    
    return all_tools
```

### 적용 범위

- **모든 Native Worker** (이미 적용 완료)
- **Runner Agent**: Hub가 `job_dispatch` 시 `args.employee_number = caller_user_id` 강제 주입
- **Webhook Agent**: `request_mapping`에 `employee_number: "{{caller.user_id}}"` 시스템 매핑 자동 삽입
- **MISO Agent**: MISO API 호출 시 `user` 필드에 caller user_id 강제 (MISO가 표준 지원)

### 매니페스트에서 사용자 입력으로 employee_number 받지 않음

LLM이 위조 못 하도록, 매니페스트의 `inputs`에 `employee_number` 같은 자기 식별 필드 정의 금지. 사번은 **항상 시스템이 주입**.

→ AgentValidatorService가 검증 시 차단 (`inputs[].name`에 `employee_number`/`사번` 등 금지어 체크).

---

## ✅ 확정: 실행 권한 주체

### Phase 1 — `caller` 권한 (호출한 사용자 권한)

```
사용자 A가 SAP 매크로 호출
   ↓
Hub가 agent_executions INSERT
   ↓
Runner에 job_dispatch + secrets 주입 (사용자 A의 SAP 자격증명)
   ↓
Runner가 사용자 A 자격증명으로 SAP 접근
```

### service_account 모델은 안 씀

이유:
- caller 모델이 **접근 통제 정확** (사용자별 SAP 권한 그대로 적용)
- service_account는 **권한 과다 부여** 위험 (모든 매크로가 같은 권한)
- L&F가 부서별 SAP 권한 다르다고 명시함 → caller 모델 필수

### 자격증명 흐름

```
1. 사용자 A 로그인 (SSO) → Hub 세션
2. 사용자 A가 SAP Agent 실행 → Hub가 SSM에서 /lucid-hub/sap/finance/{userA} fetch
3. Hub가 Runner에 job_dispatch + 자격증명 주입 (메모리만, 디스크 X)
4. Runner가 매크로 실행 시 환경변수로 자격증명 전달
5. 매크로 종료 → Runner가 자격증명 메모리 폐기
```

### 사용자별 자격증명 등록

- 별도 UI에서 사용자가 자기 SAP 비번 등록 → SSM에 `/lucid-hub/sap/{dept}/{userId}` 저장
- Phase 1 = 수동 등록, Phase 2 = SSO 연동 자동 동기화 검토

---

## ✅ 확정: 입력 검증 (SSRF, Path Traversal, SQL Injection)

### AgentValidatorService에서 차단

| 위험 | 검증 항목 | 차단 기준 |
|------|----------|----------|
| **SSRF** (Webhook) | URL이 사설 IP 가리키는지 (10.x, 169.254.x, 127.x) | critical → 자동 reject |
| **Path Traversal** (Runner) | `entry`에 `..`, 절대경로(`/`, `C:\`) | critical |
| **명령어 주입** (Runner BAT/PS1) | `args` 템플릿에 `;`, `&&`, `|` | critical |
| **SQL Injection** (Webhook) | `request_mapping`에 사용자 입력이 raw SQL로 들어가는지 | critical |
| **Secret Leak** | 매니페스트 평문에 `password`, `key`, `token` 같은 패턴 | critical |

### 런타임 추가 방어

- Runner는 `args` 인자를 **subprocess에 list 형태로 전달** (shell=False) → 명령어 주입 차단
- Webhook은 URL을 `urllib.parse`로 파싱해 host 화이트리스트 체크

---

## ✅ 확정: 공개범위 승인

### Phase 1 — 모든 등록이 operator 승인 거침

[04 §검증·승인 워크플로우](04_registration_flow.md) 그대로:
- private/team/public 무관 모두 `pending_approval` 거침
- operator role(`NEXT_PUBLIC_OPERATOR_USERS`, 현재 A2304013)이 검토

### 추가 보안 체크리스트 (operator 승인 시 수동 확인)

operator UI에 표시되는 체크리스트:

```
[ ] 1. 매니페스트 메타가 명확한가? (이름, 설명)
[ ] 2. AgentValidatorService 자동 검증 통과 여부
[ ] 3. (Runner) 매크로 entry 경로가 화이트리스트 디렉토리 내?
[ ] 4. (Webhook) URL이 신뢰할 수 있는 도메인?
[ ] 5. (Webhook) request_mapping에 caller 사번 강제 주입 포함?
[ ] 6. 자격증명 ref가 SSM 표준 경로?
[ ] 7. trigger 있는 경우, cron이 부적절한 시간(업무 시간 외 한정)?
[ ] 8. 공개범위(public)면 적절한가? team으로 한정 가능?

→ [승인] [반려] [변경요청]
```

---

## ✅ 확정: Security Guard Agent와의 통합

### 현재 Security Guard 역할

[backend/app/agents/security_guard_agent.py](../../backend/app/agents/security_guard_agent.py):
- 27개 룰 + rate limit + Haiku 3-Layer 차단
- 5-Tier 대응 (allow/warn/throttle/block/email-alert)
- 사용자 발화 기반 검사

### Hub 통합 방향

| 영역 | Security Guard 적용 |
|------|--------------------|
| 사용자 발화 (Hub 채팅) | **그대로 적용** (기존 그대로) |
| Agent 실행 결과 | **선택 적용** — 실행 출력에 민감 정보 포함 시 마스킹 |
| 자동 검증 (AgentValidatorService) | **별도 운영** — 매니페스트 보안 패턴 검증 |
| 운영 대시보드 | **공유** — operator가 같은 감사 화면에서 보안 이벤트 확인 |

### Phase 1 = 기존 Security Guard 그대로 + 매니페스트 검증만 별도

Phase 2~3에서 통합 대시보드 검토.

---

## ✅ 확정: 감사 로그

### `agent_executions` 보존 정책

| 항목 | 정책 |
|------|------|
| 일반 실행 이력 | **1년 보관** |
| 실패/오류 이력 | **2년 보관** (분석/디버깅) |
| 보안 차단 이벤트 | **영구** (Security Guard와 같은 정책) |
| `input_args` PII | **로깅 시 마스킹** (사번, 이메일, 전화번호) |

### 마스킹 대상

```
employee_number/사번 → "A2304013" → "A23***013"
email → "user@lnf.co.kr" → "u***@lnf.co.kr"
SAP password → 절대 로깅 X (메모리만)
```

### 파티셔닝 (Phase 2)

`agent_executions` 월별 파티션 (실행 이력 폭증 대비). Phase 1은 단일 테이블, 인덱스만 잘.

---

## 참고

- [00_vision.md §12.4](00_vision.md) — 기존 자산 보존 원칙
- [backend/app/agents/security_guard_agent.py](../../backend/app/agents/security_guard_agent.py) — 기존 보안 에이전트
- [docs/history/2026-04-22 LFON Account Management](../history/) — `prepare_tools()` 사번 강제 주입 패턴 (LFON)

## 체크리스트

- [x] 자격증명 저장소 = **SSM Parameter Store (Phase 1) → Secrets Manager (Phase 2)**
- [x] 사번 위조 방지 = `prepare_tools()` 패턴 모든 플랫폼 적용
- [x] 실행 권한 = caller 모델 (사용자별)
- [x] 입력 검증 = AgentValidatorService에서 SSRF/Path Traversal/주입 차단
- [x] 공개범위 승인 = 모든 등록 operator 검토 + 체크리스트
- [x] Security Guard = 기존 그대로 + 매니페스트 검증 별도
- [x] 감사 로그 = 1년/2년/영구 + PII 마스킹
- [ ] SSO 연동 자동 자격증명 동기화 (Phase 2)
- [ ] 통합 보안 대시보드 (Phase 2~3)
- [ ] `agent_executions` 파티셔닝 (Phase 2)

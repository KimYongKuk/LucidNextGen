# 03. 매니페스트 명세

> **목적**: Agent의 정의 표준. Hub가 "이게 뭘 하고, 뭘 넣으면 뭐가 나오는지, 어떻게 실행하는지"를 알 수 있는 최소 공통 표준.

## 범위

- In scope: 메타데이터, 입출력 스키마, 실행 정보(runtime), 공개범위, 트리거
- Out of scope: 실행 바이너리/스크립트 내부 로직 (Runner 또는 외부 플랫폼이 책임)

## 설계 의존성

- [01_terminology.md](01_terminology.md) ✅ Platform 4종, 페르소나
- [02_data_model.md](02_data_model.md) ✅ `agents.manifest` JSON 컬럼

---

## ✅ 확정: 보관 형태 = **DB JSON only (Phase 1)**

- `agents.manifest` JSON 컬럼에 매니페스트 전체 보관
- YAML 파일(`agent.yaml`) 별도 저장 X (Phase 1)
- Phase 2 (Runner Agent의 Git 관리 시점) — YAML import/export 도입

**근거**: 가장 쉽고 가벼운 출발. UI 폼이 직접 JSON 생성, 별도 파일 시스템 운영 X.

---

## 매니페스트 구조 (Phase 1)

### 공통 필드 (모든 플랫폼)

```jsonc
{
  // 기본 메타
  "name": "월간 매출 리포트",
  "description": "ERP 매출 데이터를 추출하여 엑셀 보고서 자동 생성",
  "icon": "📊",
  "tags": ["매출", "보고서", "ERP"],
  "version": "1.0.0",

  // 분류
  "platform": "runner",          // native | miso | runner | webhook
  "capabilities": ["run", "scheduled"],  // 다중 선택

  // 공개 범위
  "visibility": "team",          // private | team | public

  // Agent 설계자의 의도 힌트 (워크스페이스 시스템 프롬프트 자동 합성용)
  "intent_hints": {
    "system_prompt": "사용자가 매출 분석을 요청하면 monthly_sales_report Agent를 호출하세요. 결과는 표/차트로 정리합니다.",
    "trigger_examples": [
      "이번 달 서울공장 매출 뽑아줘",
      "Q1 매출 보고서 만들어줘"
    ]
  },

  // 입출력
  "inputs": [ ... ],             // 아래 [입력 정의] 참조
  "output": { "type": "file", "format": "xlsx" },

  // 실행 (플랫폼별 분기)
  "runtime": { ... },            // 아래 [runtime 스키마] 참조

  // 자동 트리거 (선택)
  "triggers": [ ... ],           // 아래 [트리거] 참조

  // 권한 (Phase 1 자리만, 비활성)
  "requires": {
    "connectors": [],            // Phase 2~3 활성화
    "permissions": []            // Phase 2~3 활성화
  }
}
```

### `intent_hints` 필드 — Phase 1 신설

워크스페이스에 Agent를 부착할 때, 워크스페이스 시스템 프롬프트에 **자동 합성**되는 힌트.

| 필드 | 용도 |
|------|------|
| `system_prompt` | LLM에게 이 Agent를 언제·어떻게 쓰는지 안내. 다중 Agent 부착 시 워크스페이스 프롬프트에 합성 |
| `trigger_examples` | (선택) 사용자 발화 예시. 라우팅 학습 보조 |

**합성 예시 (워크스페이스에 Agent 2개 부착 시)**:
```
[워크스페이스 시스템 프롬프트]
당신은 {워크스페이스 이름}에서 일하는 어시스턴트입니다.

# 사용 가능한 Agent 가이드:

## 월간 매출 리포트
사용자가 매출 분석을 요청하면 monthly_sales_report Agent를 호출하세요...

## VOC 분석
사용자가 IT/회계 지원 요청 사례를 묻거나...
```

→ 라우팅 로직(05)이 이 합성된 프롬프트 사용.

---

## ✅ 확정: 플랫폼별 `runtime` 스키마 (4종)

### `native` — 백엔드 Worker 클래스

```jsonc
"runtime": {
  "platform": "native",
  "worker_class": "MailWorker"   // backend/app/agents/workers/ 안 클래스
}
```

→ 등록은 **코드 배포로만**. 일반 사용자 등록 UI 차단.

### `miso` — MISO REST API

```jsonc
"runtime": {
  "platform": "miso",
  "app_id": "abc-123-월매출분석",  // MISO Agent/Workflow ID
  "mode": "agent",                // agent | workflow
  "auth_ref": "vault:miso-api-key" // Hub Vault 참조 (Phase 2 Vault 도입 후)
}
```

→ 등록 시 **MISO Studio URL 붙여넣기**로 자동 채움 가능 (snippet import).

### `runner` — Windows EC2 Runner

```jsonc
"runtime": {
  "platform": "runner",
  "required_labels": ["sap-fi", "office"],  // Runner 매칭 라벨
  "executor": "pad",            // pad | python | vbs | bat | ps1
  "entry": "monthly_close.flow", // EC2 디스크의 매크로 파일 경로
  "args": ["{{year_month}}", "{{factory}}"],  // 입력 변수 치환
  "timeout": 300                // 초
}
```

→ Hub Router가 `required_labels` 매칭되는 `runners` 테이블 row 자동 선택. 없으면 등록 거부.

### `webhook` — 일반 외부 REST

```jsonc
"runtime": {
  "platform": "webhook",
  "method": "POST",
  "url": "https://hooks.slack.com/services/T../B../xyz",
  "headers": { "Content-Type": "application/json" },
  "auth_ref": "vault:slack-token",
  "request_mapping": {            // 입력 → request body
    "channel": "{{channel}}",
    "text": "{{message}}"
  },
  "response_mapping": {           // response → output
    "ok": "{{response.ok}}",
    "ts": "{{response.ts}}"
  }
}
```

---

## 입력 정의 (`inputs`)

### Phase 1 = **자리만 + 기본 타입 4종**

```jsonc
"inputs": [
  {
    "name": "year_month",
    "label": "대상 연월",
    "type": "string",
    "required": true,
    "placeholder": "2026-04"
  },
  {
    "name": "factory",
    "label": "공장",
    "type": "enum",
    "required": true,
    "options": ["서울공장", "구지1공장", "구지2공장"]
  }
]
```

**Phase 1 지원 타입 4종**: `string` / `number` / `enum` / `text`

**Phase 2 추가 예정**: `date`, `file`, `user`(사번 선택), `boolean`

→ 검증 규칙(regex, min/max, etc.) 디테일은 본격 구현 단계에서 정의 (사용자 결정).

---

## ✅ 확정: 트리거 (`triggers`)

매니페스트의 `triggers`는 **자동 실행 조건**만. 사용자 수동 발화/클릭은 모든 Agent 기본 지원 (정의 불필요).

### Phase 1 = **cron 스케줄만**

```jsonc
"triggers": [
  {
    "type": "schedule",
    "cron": "0 9 1 * *",  // 매월 1일 09:00
    "timezone": "Asia/Seoul"
  }
]
```

스케줄 실행 결과 → `agent_executions` INSERT → `user_notifications`에 알림 push (4-17 §1.7).

### Phase 2 추가 예정

- `event` 트리거 (새 메일, Wiki 문서 변경, DB 이벤트 등)
- 트리거 체이닝 (한 Agent 완료 → 다른 Agent 자동 실행)

---

## ✅ 확정: 권한 (`requires`) — Phase 1 자리만

```jsonc
"requires": {
  "connectors": [],     // Phase 2~3 활성화 (Connector 도입 시)
  "permissions": []     // Phase 2~3 활성화 (권한 체계 정립 시)
}
```

Phase 1은 빈 배열로 통일. 매니페스트 스키마 호환성을 위해 **필드 자체는 남겨둔다**.

---

## 매니페스트 검증

등록 시 Hub가 검증할 항목 (04 등록 플로우에서 상세):
- 필수 필드 존재 (`name`, `platform`, `runtime`, ...)
- `platform`과 `runtime.platform` 일치
- `runtime` 스키마가 platform에 맞는지 (예: `runner` 플랫폼이면 `executor` 필수)
- `slug` 중복 없음 (`agents.slug` UNIQUE)
- `cron` 표현식 유효성 (트리거 있는 경우)
- `required_labels`가 등록된 Runner 중 하나에 매칭되는지

---

## 참고

- [00_vision.md §3.3](00_vision.md) — `action.yaml` 초안 (이번 확정으로 대체됨)
- [docs/MISO_API_Reference.md](../MISO_API_Reference.md) — MISO REST API 호출 형식
- [frontend/lib/agent-store/types.ts](../../frontend/lib/agent-store/types.ts) — 프론트 Agent 인터페이스 (매니페스트 일부)

## 체크리스트

- [x] 보관 형태 확정 — **DB JSON only (Phase 1)**
- [x] 공통 필드 확정
- [x] 플랫폼별 runtime 스키마 4종 확정
- [x] 입력 타입 Phase 1 = `string/number/enum/text` 4종
- [x] 트리거 Phase 1 = cron 스케줄만
- [x] requires는 자리만, Phase 1 비활성
- [x] `intent_hints` 필드 신설 — 워크스페이스 시스템 프롬프트 자동 합성용
- [ ] 입력 검증 규칙 디테일 (구현 시점에 정의)
- [ ] 매니페스트 검증 로직 구체화 (04에서)

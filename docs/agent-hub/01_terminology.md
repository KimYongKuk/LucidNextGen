# 01. 용어 정의

> **목적**: Hub에서 사용하는 핵심 용어를 하나로 통일한다. 4-06 설계서(Action)와 4-17 프론트 구현(Agent), history 문서(Service)의 혼용을 정리한다.

## 범위

- In scope: 아키텍처 설계 문서 전반에서 쓰이는 주요 명사/형용사
- Out of scope: UI 카피 (사용자에게 보이는 용어는 별도 — UX 팀과 합의)

---

## ✅ 확정: Hub의 정체성

> **Hub = MISO에 도구를 공급하는 통합 백엔드 게이트웨이 + 가벼운 채팅 인터페이스**

### 사용자 진입점 이중화

```
[현업 메인]                    [현업 보조]
   MISO 빌더                    Hub 채팅
       │                          │
       │ MCP import               │ 자체 호출
       ▼                          ▼
   ┌──────────────────────────────────┐
   │       Hub MCP Gateway            │  ← 모든 Agent를 MCP tool로 통합 노출
   └──────────────┬───────────────────┘
                  │
   ┌──────────────┼──────────────────┐
   ▼              ▼                  ▼
[Native MCP]  [Runner EC2]      [Webhook 외부]
   11개 서버    4대 (본부별)        n8n/SaaS
```

### 핵심 원칙

1. **MISO = 메인 빌더** (조직 투자 정렬). 현업이 자연어로 워크플로우 작성.
2. **Hub = 도구 공급자**. MISO에서 import할 MCP gateway 1개만 노출.
3. **Runner/Native/Webhook은 외부 노출 X**. Hub만이 그들을 부른다.
4. **자격증명은 Hub Vault 중앙 집중**. MISO에 분산 X.

### MISO 배포 형태

`api.miso.landf.co.kr` — **사내 호스팅**. 사내망에서 Hub MCP 호출 가능.

### Hub MCP Gateway 도입 시점

- **Phase 1**: Hub 채팅에서 Runner Agent 호출까지 (기본 카탈로그/실행)
- **Phase 2**: Hub MCP gateway 노출 → MISO에서 import 가능
- → MISO 통합은 Phase 2로 명시적 분리

---

## ✅ 확정: 최상위 엔티티 = **Agent**

4-06 설계서의 "Action", 4-17 history의 "Service" 후보를 기각하고 **Agent**로 통일.

- 파일명: `agent.yaml` (`action.yaml` 아님)
- 테이블명: `agents` (`actions` / `service_registry` 아님)
- URL: `/agent-store/*` (이미 프론트 적용)
- API: `/api/v1/agents/*`
- 최상위 디렉토리: `docs/agent-hub/`

**선택 근거**
- 4-17 프론트 네이밍과 일치 — 재작업 불필요
- AI 업계 관용 (LangGraph, OpenAI Agents SDK 등)
- 사용자 관점 자연스러움 ("에이전트 스토어")

---

## ✅ 확정: Worker = Agent의 Native 구현체

**결론**: Worker와 Agent는 **동일 선상의 개념**으로 취급. 용어는 **Agent로 통일**.

### 관계 모델

**Agent ↔ Worker(인스턴스) = 1:1**

```
등록된 Agent 1개 ──┬──▶ Worker 인스턴스 1개 (자기 runtime 설정 보유)
                  │
                  └──▶ 같은 플랫폼 Agent는 같은 Worker 클래스를 공유 (구현 디테일)
```

- Native Agent (Direct, Mail, 등): 각자 전용 Worker 클래스 (DirectWorker, MailWorker), 1:1
- MISO Agent "월매출분석" / "VOC분석": 공통 `MisoWorker` 클래스의 **별도 인스턴스** 각 1개
- Runner Agent "출장비정산" / "재고리포트": 공통 `RunnerWorker` 클래스의 **별도 인스턴스** 각 1개

**클래스 레벨** (Worker 클래스 : Agent 인스턴스)는 1:N일 수 있지만, **인스턴스 레벨** (Worker 인스턴스 : Agent)은 항상 1:1.

→ 개념 모델/용어 수준에서는 **"Agent 하나 = Worker 하나"**로 통일한다.

### 코드 레벨 네이밍 정책

**코드 내 Worker 용어는 영구 유지**. 강제 rename 없음.

| 레이어 | 용어 |
|--------|------|
| 사용자 UI | Agent |
| 문서 (docs/agent-hub) | Agent |
| DB 스키마 | `agents`, `agent_executions`, ... |
| API 엔드포인트 | `/api/v1/agents` |
| **백엔드 코드** | **Worker 유지** (`BaseWorker`, `DirectWorker`, `backend/app/agents/workers/`) |
| 로그/주석 | 혼용 허용 |

**근거**
- Worker → Agent rename은 순수 이름값 교체, 동작 변화 0 → 리팩토링 ROI 없음
- LangGraph 등 업계도 worker/agent 혼용 관용 존재
- "언젠가 바꾼다"는 약속은 실행 안 될 것이 명확하므로 처음부터 **영구 허용**으로 선언

---

## 하위 용어

### 현재 상태

| 용어 | 상태 | 정의 |
|------|------|------|
| **Workspace** | ✅ 확정 | Agent를 담는 **컨테이너** (Platform 아님, 영구 유지). 4-17 관점 2 채택 |
| **Runner** | ✅ 확정 | Windows EC2 상주 서비스. 로컬 스크립트 실행 |
| **Capability** | ✅ 확정 | Agent의 상호작용 방식 다중 태그 (chat/run/scheduled/async) |
| **Platform** | ✅ 확정 | Agent의 구현 백엔드 분류 — **native / miso / runner / webhook** 4종 |
| **Connector** | ✅ 확정 | Agent의 애드온 (등록 UI에서 선택하는 확장 모듈). 구현은 MCP 기반 |

### Platform — 4종 확정

| Platform | 설명 | 하위 구분 필드 (매니페스트) | **등록자 페르소나** |
|----------|------|------------------------|------------------|
| `native` | 백엔드 Worker 클래스 구현 | `worker_class` (DirectWorker, MailWorker 등) | 내부 개발자 (코드 배포) |
| `miso` | MISO REST API 전용 실행 엔진 | `mode: agent` / `mode: workflow` | **현업 비개발자** (MISO 바이브코딩) |
| `runner` | Windows EC2 Runner 경유 로컬 실행 | `executor: python / vbs / bat / ps1 / pad` | **IT / 개발자** (PAD 포함, 일단 IT가 포지션) |
| `webhook` | 일반 외부 REST (n8n, Zapier, 임의 API) | `method`, `url`, `request_mapping`, `response_mapping` | 개발자 / SaaS 구매자 |

**4-17 §1.3의 7종 분류에서의 변화**:
- Windows EC2 Python 매크로 → `runner` / `executor: python`
- Windows EC2 PAD → `runner` / `executor: pad`
- MISO Agent → `miso` / `mode: agent`
- MISO Workflow → `miso` / `mode: workflow`
- 기타 Workflow (n8n 등) → `webhook`
- 기타 Agent (향후) → **제거** (모호한 범주)
- Workspace RAG → **제거** (Agent가 아니라 워크스페이스 내장 기능으로 취급)

**Workspace RAG 처리**: Workspace "컨테이너 관점 유지" 원칙 하에, Workspace 자체를 Agent로 올리지 않는다. 워크스페이스 내 문서 RAG는 Workspace의 **내장 기능**(토글 on/off)이며, 기존 `UserFilesWorker` 로직이 워크스페이스 컨텍스트에 의해 자동 활성화된다. 카탈로그에서 독립 Agent로 노출하지 않는다.

### 페르소나 분리 원칙 (Phase별 점진 개방)

4-06 설계서의 "현업 자율성" 원칙은 **MISO 루트로 한정**한다. Runner는 보수적 시작 → 점진 개방.

| Phase | MISO | Runner | Webhook | Native |
|-------|------|--------|---------|--------|
| **1 (지금)** | 현업 | **IT 단독** | 개발자 | 내부 개발자 |
| 2 (점진 개방) | 현업 | IT + 본부 협력자 (PAD만) | 개발자 + 일부 현업 | 내부 개발자 |
| 3 (장기) | 현업 | + 일부 현업 (Excel VBA 등) | 광범위 개방 | 내부 개발자 |

**Phase 1 = IT 단독** 근거:
- SAP 자격증명/사내망 접근권 등 보안 민감
- 검증·승인 시스템 신뢰성 미검증 상태
- IT가 매크로 패턴/템플릿 축적 단계

**점진 개방 트리거**:
- 검증·승인 시스템 N개월 무사고
- PAD가 저코드라 우선 개방 (VBS/Python/PS1은 영구 IT)
- 본부별 IT 협력자 지정으로 IT 부담 분산

**MISO**: 모든 Phase에서 현업 영역 (조직 투자 정렬).

등록 UI는 페르소나/Phase별로 진입 분리 — [04_registration_flow.md](04_registration_flow.md) 참조.

### Connector — Agent 애드온으로 확정

**정의**: Agent에 선택적으로 부착 가능한 **확장 모듈**. Agent 등록 UI에서 "이 Agent가 사용할 외부 연동"을 체크하는 단위.

**구현 관계**:
- 구현은 **MCP Server 기반**
- 관리자가 "Connector로 공개 승격"한 MCP만 카탈로그에 노출
- 한 Agent에 0~N개 붙을 수 있음
- 붙은 Connector의 도구를 Agent가 자연어로 호출

**모든 MCP가 Connector는 아님**:
- 예: `mail_server` MCP는 MailWorker **전용** — Connector로 노출 안 함
- 예: (가정) `slack_mcp`는 여러 Agent에 애드온으로 붙일 수 있음 — Connector로 노출

**도입 시점**: Phase 2~3 (Agent 등록 실제 구현 시점). 지금은 정의만.

### 용어 층 구분 원칙 (혼동 방지)

용어 충돌 방지를 위해 각 용어의 **층**을 명시한다:

| 층 | 용어 | 주체 | 예 |
|----|------|------|-----|
| 논리 단위 | **Agent** | 등록 단위 | "월매출분석" Agent |
| Agent 확장 | **Connector** | Agent 레벨 애드온 (사용자 선택) | Slack Connector, Gmail Connector |
| 실행 구현 | **Worker** (= 실행 엔진) | Platform별 실행기 (내부) | MisoWorker, RunnerWorker |
| 도구 집합 | **MCP Server** | 도구 묶음 제공자 (인프라) | slack_mcp, mail_server |
| 개별 도구 | **Tool** | 함수 단위 | send_message, get_inbox |

**"Adapter" 용어는 쓰지 않는다** — "실행 엔진(Worker)"으로 대체.

---

## 참고

- [00_vision.md §3.1](00_vision.md) — "Action" 초안 (이번 확정으로 대체됨)
- [2026-04-17 §1.2](../history/2026-04-17_AgentStore_Workspace_Inbox.md) — Capability 태그 채택 근거
- [frontend/lib/agent-store/types.ts](../../frontend/lib/agent-store/types.ts) — 프론트 Agent 인터페이스

## 체크리스트

- [x] 최상위 엔티티 명칭 확정 — **Agent**
- [x] Worker vs Agent 관계 확정 — **Agent 통일, 코드는 Worker 유지, Agent ↔ Worker 인스턴스 1:1**
- [x] Platform 분류 확정 — **native / miso / runner / webhook**
- [x] Workspace 위상 확정 — **Platform 아님, 컨테이너 영구 유지**
- [x] Hub 정체성 확정 — **MISO에 도구 공급하는 MCP gateway + 가벼운 자체 채팅**
- [x] 페르소나 분리 확정 — **Phase 1: Runner는 IT 단독 / Phase 2: PAD만 현업 개방 / MISO는 항상 현업**
- [x] Connector 용어 확정 — **Agent 애드온, MCP 기반, 승격된 MCP만 노출, 도입은 Phase 2~3**
- [x] 용어 층 구분 원칙 확정 — **Agent / Connector / Worker / MCP Server / Tool 5층**

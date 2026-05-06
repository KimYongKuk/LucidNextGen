# 2026-04-30 Agent Hub Phase 1 설계

## 개요

루시드AI를 사내 AI Hub로 격상하기 위한 **설계 컨센서스 7개 문서 작성** + **Phase 1 마이그레이션 SQL 2개** 작업. 4-06 비전 문서(`docs/루시드AI_Hub_아키텍처_설계서.md`)를 보존(`00_vision.md`)하고, 4-17 프론트 mock 구현 이후 비어 있던 구현 명세를 새로 정립. 등록 로직 직접 진입 전에 **용어/데이터/매니페스트/등록흐름/라우팅/Runner프로토콜/보안 컨센서스를 먼저 잡음**.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `docs/agent-hub/README.md` | 추가 | 8개 문서 인덱스 + 작성 원칙 |
| `docs/agent-hub/00_vision.md` | 이동 | 기존 `docs/루시드AI_Hub_아키텍처_설계서.md` → 보존 (4-06 원본) |
| `docs/agent-hub/01_terminology.md` | 추가 | Agent/Worker/Platform/Workspace/Connector 용어 통일, 페르소나 Phase별 |
| `docs/agent-hub/02_data_model.md` | 추가 | 8개 테이블 ER + 마이그레이션 전략 |
| `docs/agent-hub/03_manifest_spec.md` | 추가 | DB JSON 매니페스트, 플랫폼별 runtime 4종, `intent_hints` 신설 |
| `docs/agent-hub/04_registration_flow.md` | 추가 | 라이프사이클 8상태, 페르소나별 위저드, AI 검증+인간 승인 |
| `docs/agent-hub/05_routing.md` | 추가 | Workspace 격리 라우팅, 빠른 워크스페이스, 시스템 프롬프트 자동 합성 |
| `docs/agent-hub/06_runner_protocol.md` | 추가 | WebSocket, 메시지 8종, MySQL 큐, S3 presigned 파일 |
| `docs/agent-hub/07_security.md` | 추가 | SSM Parameter Store, caller 권한, 사번 위조 방지 |
| `backend/migrations/add_agent_hub_phase1.sql` | 추가 | 8개 테이블 DDL + 외래키 RESTRICT |
| `backend/migrations/seed_agent_hub_phase1.sql` | 추가 | Runner 4대 + Native Agent 18개 카탈로그 seed |

## 상세 내용

### 1. 핵심 컨센서스 결정 사항

#### 1.1 용어 (01)

- **최상위 엔티티 = Agent**. (Action/Service 후보 기각)
- **Worker = Agent의 인스턴스 1:1**. 백엔드 코드는 Worker 용어 영구 유지, 사용자/문서/DB/UI는 Agent로 통일.
- **Platform 4종**: `native` / `miso` / `runner` / `webhook`. (4-17 §1.3의 7종을 Platform 차원으로 정리)
- **Workspace = Agent를 담는 컨테이너** (Platform 아님, 영구 유지).
- **Connector = Agent의 애드온** (Phase 2~3 활성화, MCP Server 일부를 승격하여 노출).
- **5층 레이어 구분**: Agent / Connector / Worker / MCP Server / Tool.

#### 1.2 페르소나 Phase별 점진 개방 (01)

| Phase | MISO | Runner | Webhook | Native |
|-------|------|--------|---------|--------|
| 1 (지금) | 현업 | **IT 단독** | 개발자 | 내부 개발자 |
| 2 | 현업 | IT + 본부 협력자 (PAD만) | 개발자 + 일부 현업 | 내부 개발자 |
| 3 | 현업 | + 일부 현업 (Excel VBA) | 광범위 개방 | 내부 개발자 |

#### 1.3 Hub의 정체성 (01)

> **Hub = MISO에 도구를 공급하는 통합 백엔드 게이트웨이 + 가벼운 채팅 인터페이스**

- 메인 빌더 = MISO (조직 투자 정렬)
- Hub MCP Gateway가 모든 Agent를 MCP tool로 통합 노출 → MISO에서 import
- Phase 2 작업: Hub MCP gateway 노출

#### 1.4 데이터 모델 (02) — Phase 1 = 8개 테이블

| # | 테이블 | 역할 |
|---|--------|------|
| 1 | `agents` | 카탈로그 (정규화 컬럼 + manifest JSON) |
| 2 | `user_agents` | 사용자별 설치/활성화 (Active Agents 리스트 소스) |
| 3 | `workspace_agents` | 워크스페이스 부착 (4-17 localStorage 이관) |
| 4 | `agent_review_reports` | AI 자동 검증 리포트 (퀄리티/보안) |
| 5 | `agent_approvals` | 인간 승인 결정 (operator role) |
| 6 | `agent_executions` | 실행 이력 (감사·디버깅·통계) |
| 7 | `user_notifications` | 알림함 (90일 hard delete) |
| 8 | `runners` | Runner EC2 등록 (4대 본부별) |

**제외**: 즐겨찾기, 사용자 별점, `agent_versions` 분리 테이블, `agent_credentials`(SSM 활용), Connector 관련.

**정책**:
- 외래키 모두 ON DELETE RESTRICT (soft delete만 사용)
- Native Agent 18개 → seed 데이터로 INSERT (`is_native_seed=TRUE`)
- 모든 user에게 Native Agent 자동 install (다음 단계 작업)

#### 1.5 매니페스트 (03)

- **DB JSON only** (Phase 1). YAML 파일 별도 X.
- 공통 필드: name/description/icon/tags/version/platform/capabilities/visibility/inputs/output/runtime/triggers/intent_hints/requires
- **`intent_hints` 신설**: Agent 설계자가 시스템 프롬프트 힌트 작성 → 워크스페이스에 부착 시 자동 합성
- 플랫폼별 runtime 4종 명세
- 입력 타입 Phase 1 = `string/number/enum/text` 4종
- 트리거 Phase 1 = cron 스케줄만
- `requires`는 자리만 잡고 Phase 1 비활성

#### 1.6 등록 플로우 (04)

- 라이프사이클 8상태: `draft → pending_review → pending_approval → active → maintenance / disabled / deleted` + `rejected`
- 페르소나별 위저드 분리: `/agent-store/new/miso`, `/agent-store/new/runner`, `/agent-store/new/webhook`
- 권한 없는 카드는 disabled로 노출 (학습성)
- Native는 카드 미포함 (코드 배포로만)
- **모든 등록이 `pending_review` 거침** (Phase 1, private/team/public 무관)
- 검증 시스템 = `AgentValidatorService` 별도 서비스 클래스 (Bedrock Sonnet 직접 호출)
- 인간 승인자 = operator role (`NEXT_PUBLIC_OPERATOR_USERS`)
- 편집 시 새 버전 자동 증가, 자동 업그레이드 (Phase 1은 이전 버전 보존 X)
- soft delete만 (hard delete 금지)

#### 1.7 라우팅 (05)

- **Workspace 격리 라우팅**: 일반 채팅 = Native만, Workspace 채팅 = Native + 부착 Agent
- **빠른 워크스페이스 생성 UX**: Agent 카드 클릭 → 워크스페이스 자동 생성 + Agent 자동 부착 + 시스템 프롬프트 자동 합성
- 시스템 프롬프트 자동 합성: 부착된 Agent N개의 `intent_hints.system_prompt` 병합
- 모델: 일반 채팅 = Haiku, Workspace = Sonnet
- 실행 전 확인 UX: `run` capability에 한해 다이얼로그

#### 1.8 Runner 프로토콜 (06)

- 채널 = WebSocket, 연결 방향 = Runner → Hub (outbound, 방화벽 친화)
- 메시지 타입 8종: register / heartbeat / job_dispatch / job_progress / job_result / job_error / job_cancel / shutdown
- 작업 큐 = Phase 1 MySQL 테이블, Phase 2 Redis
- 파일 전달 = S3 presigned URL
- 하트비트 30초, 5분 미수신 → offline
- Phase 1 자동 재시도 X
- AMI 골든 이미지 + EFS 외부화 + ASG = Phase 2~3 도입

#### 1.9 보안 (07)

- 자격증명 = **AWS SSM Parameter Store** (Phase 1, 무료) → Phase 2 = Secrets Manager 점진
- 사번 위조 방지 = 기존 `prepare_tools()` 패턴 모든 플랫폼 적용
- 실행 권한 = caller 모델 (사용자별 SAP 자격증명 그대로)
- 입력 검증 = AgentValidatorService에서 SSRF/Path Traversal/주입 차단
- 감사 로그: 일반 1년 / 실패 2년 / 보안 영구, PII 마스킹

### 2. EC2 Runner 매핑 (조직도 분석 결과)

PostgreSQL `v_org_chart` VIEW 분석 (총 5회 쿼리, c:/tmp/analyze_org_for_runner_v*.py):
- 엘앤에프 본체(L2=12, 226부서/821명) → CPO/영업/CFO/공통 4본부 식별
- L2=12:566 (광미래중국), L2=12:58 (JHC) — **분석 대상 제외**
- 엘앤에프플러스 별도 자회사로 v_org_chart에 안 보임 (후속 확인 필요)
- 본부 분포:
  - CPO (L3=147, 477명, 58%): 생산/R&D 본부
  - 미상 (L3=17, 203명, 25%): 영업/마케팅 추정
  - CFO (L3=410, 117명, 14%): 재경/지원
  - 미상 (L3=643, 15명, 2%): 작은 본부
  - 감사실 (L3=140, 3명)

→ Runner 4대 본부별 매핑:
1. `CPO본부 Runner` (labels: cpo/sap/office/mes/production)
2. `영업/마케팅 Runner` (labels: sales/office/crm)
3. `CFO본부 Runner` (labels: cfo/sap-fi/office)
4. `공통/감사 Runner` (labels: shared/office)

**점진 확장 시나리오**:
- Phase 1: 4대 정적
- Phase 2: CPO 본부 spike 시 +1 (라벨 동일 풀 형성)
- Phase 3: 엘앤에프플러스 별도 EC2 추가 (확정 시)

### 3. AWS 아키텍처

```
[AWS Cloud — Linux EC2]                         [AWS Cloud — Windows EC2]
├── ALB (HTTPS 종료)                            ├── Runner 4대 (본부별)
├── Hub Frontend (Next.js, Blue/Green)          │   PAD/SAP GUI/Office/Python/Runner.exe
├── Hub Backend (FastAPI, Blue/Green)           │   상시 WSS 연결 → Hub
├── RDS MySQL (Multi-AZ)                        │
├── ElastiCache Redis (Phase 2)                 ├── EFS (Phase 2 외부화)
├── S3 (산출물 30일 보관)                        └── Direct Connect 또는 VPN
├── SSM Parameter Store (자격증명)                  → 사내 SAP/MES/그룹웨어
├── CloudWatch (메트릭+로그+알람)
└── SNS (operator 알람)
```

**비용 가늠**: 월 $850~ (Runner Windows EC2 4대 라이선스 포함)

### 4. 마이그레이션 SQL 구조

**add_agent_hub_phase1.sql**:
- 8개 테이블 `CREATE TABLE IF NOT EXISTS`
- InnoDB + utf8mb4 (기존 컨벤션)
- 외래키 모두 RESTRICT
- 인덱스: 자주 쿼리하는 (user_id, agent_id, status, created_at) 등
- `agents.runner_id` FK → 두 테이블 모두 생성 후 ALTER로 추가

**seed_agent_hub_phase1.sql**:
- Runner 4대 INSERT (ec2_instance_id/auth_token_hash는 PLACEHOLDER)
- Native Agent 18개 INSERT (DirectWorker, MailWorker, ITSupportWorker 등)
- `is_native_seed=TRUE` 마크
- `status='active'` (검증/승인 거치지 않음 — 코드 배포된 것이므로 신뢰)
- `manifest`에 `runtime.worker_class`, `intent_hints.system_prompt` 포함

## 결정 사항 및 주의점

### 결정 근거

- **MISO 메인 빌더 정렬**: 조직이 MISO에 투자 → 현업 진입은 MISO만, Hub는 도구 공급자
- **Workspace 격리 라우팅**: 4-17 §1.4 "Workspace = 컨테이너" 관점 그대로 실현, Intent Router 단순화
- **AI 검증 + 인간 승인**: 사용자 요구 — operator가 검증 보고 최종 결정
- **SSM Parameter Store**: 무료 + Phase 1 시크릿 ~10개 수준에 충분, 자동 회전 필요해지면 Secrets Manager로 점진
- **소문자 SQL alias**: PostgreSQL이 unquoted alias를 lowercase fold함 — `as L1_id`가 `l1_id`로 저장됨, 조직도 분석 v2 스크립트에서 KeyError 겪음

### 알려진 주의점

1. **Runner placeholder 값**: `ec2_instance_id`, `auth_token_hash` 모두 PLACEHOLDER. 실제 EC2 배포 시점에 갱신 필요.
2. **본부명 미상**: L3=17(영업/마케팅 추정), L3=643(2%) — 실제 본부명 확인 후 `responsible_dept_groups` 갱신.
3. **엘앤에프플러스 위치**: v_org_chart에서 안 보임. 별도 자회사인지, L2=12 안에 흡수인지 후속 확인.
4. **Native Agent 자동 install**: seed에서 `agents` row만 생성. 모든 user에게 `user_agents` INSERT 하는 별도 스크립트 필요 (다음 단계).
5. **Hub MCP Gateway 미구현**: Phase 1 = Hub 자체 채팅에서 Agent 호출만. MISO에서 import하려면 Phase 2에서 MCP gateway 구현 필요.
6. **AWS Windows EC2 한국어 패키지 + sysprep 이슈**: 파트너사 협조 부족 가능성, AWS Korea 직접 컨택 또는 SetupComplete.cmd 후처리로 해결 가능.

### Phase 2~3 작업 항목 (백로그)

- 컬럼 타입/길이 디테일 + DDL 보강
- `agent_versions` 테이블 분리
- ASG + EFS 외부화 (Runner 동적 풀)
- **Hub MCP Gateway** 구현 (MISO 연계 핵심)
- Connector 카탈로그 활성화
- AWS Secrets Manager 이전 (자동 회전 시점)
- 통합 보안 대시보드 + Security Guard 통합
- `agent_executions` 월별 파티셔닝
- 사용자별 SAP 자격증명 등록 UI

### 다음 단계 후보

1. 사용자별 Native Agent 자동 install 스크립트 (seed 마무리)
2. AgentValidatorService 골격 (`backend/app/services/agent_validator_service.py`)
3. Agent CRUD API 라우트 (`/api/v1/agents`)
4. 등록 폼 프론트 (`/agent-store/new/{platform}` 위저드)

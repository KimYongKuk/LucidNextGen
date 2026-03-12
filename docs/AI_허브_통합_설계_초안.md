# AI 허브 통합 설계 초안

> 작성일: 2026-03-12
> 상태: 초안 (구현 전 컨셉 정리)
> 목적: Lucid AI 플랫폼을 사내 AI 서비스 허브로 진화시키기 위한 아키텍처 설계

---

## 1. 비전

Lucid를 단순 챗봇이 아닌 **사내 AI 서비스 허브**로 확장한다.
- 외부 RPA 서버, MISO(Agent/Workflow) 등 다양한 서비스를 Lucid에서 자연어로 호출
- 부서별 서비스 개발 → 등록 → 공유하는 **사내 AI 서비스 마켓플레이스** 구축
- Lucid = 자연어 인터페이스 + 핵심 요약 / 외부 UI = 상세 조작·시각화

---

## 2. 전체 아키텍처

```
┌─────────────────── Lucid AI Platform ───────────────────┐
│                                                          │
│  사용자: 자연어로 요청                                     │
│       ↓                                                  │
│  [Orchestrator] → [Service Registry 조회]                 │
│       ↓                                                  │
│  ┌─────────────────┐   ┌──────────────────────┐          │
│  │ 내부 Workers     │   │ ExternalAgentWorker  │          │
│  │ (기존 그대로)     │   │                      │          │
│  │ · DirectWorker  │   │  platform_type 확인   │          │
│  │ · MailWorker    │   │       ↓              │          │
│  │ · CorpRAGWorker │   │  ┌─────────────┐     │          │
│  │ · ...           │   │  │ RPAAdapter   │──────────→ EC2 RPA 서버들
│  └─────────────────┘   │  │ MISOAdapter  │──────────→ MISO 플랫폼
│                        │  │ (향후 추가)   │──────────→ 기타 플랫폼
│                        │  └─────────────┘     │          │
│                        └──────────────────────┘          │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 연동 대상

### 3-1. RPA 서버 (부서별 EC2)

- 각 부서가 자체 EC2에 RPA 서버를 호스팅
- 서버 기반 자동화 (데스크톱 제어 아님 — OS 레벨 자동화는 보안/배포 문제로 제외)
- **비동기 패턴**: 작업 제출 → job_id → 완료 시 callback

| 특성 | 값 |
|------|-----|
| 응답 시간 | 분~시간 단위 |
| 통신 | REST API (표준 4개) |
| 결과 전달 | Callback (Push) 권장, Polling (Pull) 폴백 |

**RPA 서버 표준 API (부서가 지켜야 할 최소 인터페이스):**
```
POST   /execute          작업 실행 요청 → { job_id } 반환
GET    /status/{job_id}  상태 조회
POST   /cancel/{job_id}  취소 요청
완료 시 → Lucid callback URL로 POST
```

내부 구현은 Python/Java/Node 등 자유. 이 4개 API만 지키면 Lucid에 연동 가능.

**Job Lifecycle:**
```
SUBMITTED → RUNNING → COMPLETED
                   ↘ FAILED (재시도 max 2회)
                   ↘ CANCELLED
```

### 3-2. MISO 플랫폼 (GS MISO)

- n8n 유사 워크플로우 엔진 + LLM Agent 노드
- **동기 패턴**: POST 요청 → 즉시 결과 반환
- 인증: API Key

| 유형 | 설명 | 패턴 |
|------|------|------|
| Workflow | 트리거 → 노드 체인 → 결과 (예: Q-cost 분석) | 동기 POST |
| Agent | LLM + Instruction 기반 대화형 응답 | 동기 POST |

**연동 예시 — Q-cost 분석:**
```
QMS (데이터 원천) → MISO (분석 워크플로우) → Lucid (사용자 인터페이스)

사용자: "이번 달 Q-cost 분석해줘"
    → Lucid → MISO API POST → MISO가 QMS 데이터 분석 → 결과 반환
    → Lucid가 결과 요약 + 대시보드 링크 제공
```

Lucid는 분석 로직을 모름. MISO한테 "실행해줘" → 결과 전달만 담당.
분석 기준 변경 시 MISO 워크플로우만 수정, Lucid는 변경 없음.

### 3-3. 대시보드가 있는 서비스

MISO 등에서 v0 같은 도구로 대시보드 UI를 만들어둔 경우:

```
Lucid = 자연어 진입점 + 핵심 요약 (API 호출 결과)
외부 UI = 본격적인 조작/시각화 (별도 창에서 접근)
```

- 간단한 확인/질문 → Lucid 채팅에서 처리
- 상세 분석/조작 → 외부 대시보드 링크로 안내
- iframe 임베드는 하지 않음 (인증 전파, X-Frame-Options 등 제약)

---

## 4. 어댑터 패턴

### 왜 어댑터가 필요한가

RPA와 MISO는 통신 방식이 다름:
```
RPA:  POST /execute → job_id (비동기) → callback으로 결과
MISO: POST /run → 바로 결과 (동기)
```

ExternalAgentWorker가 매번 플랫폼별 분기를 하면 서비스 늘어날수록 복잡해짐.
어댑터가 차이를 숨겨서 Worker는 항상 동일한 인터페이스로 호출:

```python
result = await adapter.execute(params)  # Worker는 이것만 호출

# 내부적으로:
# RPAAdapter.execute()   → 제출 → 대기 → callback → 결과
# MISOAdapter.execute()  → POST → 바로 결과
```

### 어댑터 결정 방식

Service Registry의 `platform_type` 필드가 어댑터를 결정:

```
Registry 조회 → platform_type = "rpa"  → RPAAdapter
             → platform_type = "miso" → MISOAdapter
             → platform_type = "xxx"  → 향후 추가 어댑터
```

새 플랫폼 추가 시 어댑터 클래스 하나만 만들면 됨. ExternalAgentWorker 코드 변경 없음.

### 어댑터 클래스

```python
class RPAAdapter:
    async def execute(self, service_config, params, user_id) -> dict
    async def get_status(self, job_id) -> dict       # 폴링 폴백용
    async def cancel(self, job_id) -> bool

class MISOAdapter:
    async def execute(self, service_config, params, user_id) -> dict
```

---

## 5. Service Registry

### DB 스키마

```sql
CREATE TABLE service_registry (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,              -- "매입 세금계산서 발행"
    description TEXT,                         -- Intent 분류용 설명
    platform_type VARCHAR(20) NOT NULL,      -- rpa / miso / (향후 확장)
    endpoint VARCHAR(255) NOT NULL,          -- API URL
    auth_type VARCHAR(20),                   -- bearer / api_key
    auth_credential VARCHAR(100),            -- vault 참조 키
    input_schema JSON,                       -- 필요한 파라미터 스펙
    keywords JSON,                           -- ["세금계산서","매입","발행"]
    dashboard_url VARCHAR(255),              -- 외부 대시보드 URL (있는 경우)

    -- 소유/관리
    department VARCHAR(50),                  -- "재무팀" / "공통"
    owner_id VARCHAR(50),                    -- 등록자

    -- 공유 범위
    scope VARCHAR(20) DEFAULT 'private',     -- public / department / group / private
    allowed_depts JSON,                      -- ["재무팀","생산팀"] (group일 때)

    -- 상태/메타
    status VARCHAR(20) DEFAULT 'draft',      -- draft / review / active / deprecated
    version VARCHAR(20) DEFAULT '1.0',
    estimated_duration_sec INT,              -- RPA 예상 소요 시간
    usage_count INT DEFAULT 0,               -- 호출 횟수

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_scope_status (scope, status),
    INDEX idx_department (department)
);
```

### RPA Job 추적 (RPA 전용)

```sql
CREATE TABLE rpa_jobs (
    id VARCHAR(36) PRIMARY KEY,
    service_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    session_id VARCHAR(36),
    request_params JSON,
    status ENUM('submitted','running','completed','failed','cancelled')
        DEFAULT 'submitted',
    result JSON,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    INDEX idx_user_status (user_id, status),
    INDEX idx_session (session_id)
);
```

---

## 6. Lucid 내부 구성요소 (신규 개발 필요)

| 구성요소 | 역할 |
|---------|------|
| Service Registry (DB + API) | 모든 외부 서비스 목록 관리 |
| ExternalAgentWorker | 외부 서비스 호출 전담 Worker |
| RPAAdapter | EC2 RPA 서버 통신 (비동기 Job) |
| MISOAdapter | MISO API 통신 (동기 POST) |
| Callback 엔드포인트 | RPA 완료 알림 수신 (`/api/v1/rpa/callback`) |
| 서비스 관리 UI | 등록/승인/목록 (admin 페이지 확장) |
| 권한 필터링 | scope/department 기반 서비스 노출 제어 |

---

## 7. 서비스 공유 생태계

### 공유 범위

```
scope:
  ├── public     → 전사 누구나 사용 가능
  ├── department → 해당 부서만
  ├── group      → 지정된 부서 목록
  └── private    → 만든 사람만 (개발/테스트 중)
```

### 서비스 등록 흐름

```
① 부서 담당자: MISO 또는 RPA로 서비스 개발
② Lucid 서비스 등록 신청 (관리자 UI)
   - 이름, 설명, 키워드, 엔드포인트, 플랫폼 유형, 공유 범위
③ 플랫폼팀 검수 (API 동작 확인, 보안 체크)
④ 승인 → Registry 등록 → 즉시 사용 가능
⑤ 공유 범위 확대 가능 (department → public)
```

### 거버넌스

| 항목 | 내용 |
|------|------|
| 누가 만드나 | 각 부서 담당자 (MISO/RPA 개발자) |
| 누가 등록하나 | 만든 사람 신청 → 플랫폼팀 승인 |
| 품질 관리 | 검수 단계 (API 테스트, 보안 체크) |
| 폐기 | 일정 기간 미사용 → deprecated → 삭제 |
| 모니터링 | 서비스별 호출량, 성공률, 응답시간 |

---

## 8. Workspace + Agent 활성화

외부 서비스는 기존 Worker처럼 자동 라우팅되기보다, **Workspace에 명시적으로 붙여서 활성화**하는 구조:

```
[마케팅 워크스페이스]
  ├── 기본 기능 (문서, 대화, 메모리)
  ├── + Q-cost 분석 Agent ✅ (활성화)
  ├── + 경쟁사 모니터링 Agent ✅ (활성화)
  └── + 세금계산서 Agent ⬜ (비활성화)

→ 활성화된 Agent만 해당 Workspace에서 호출 가능
→ 사용자 권한 범위(scope)에 포함된 서비스만 붙일 수 있음
```

---

## 9. RPA 결과 전달 방식

### Callback (Push) — 권장

```
[RPA 서버] 완료 → POST /api/v1/rpa/callback
    → rpa_jobs 상태 업데이트
    → 사용자 온라인: 채팅방에 결과 메시지 삽입
    → 사용자 오프라인: 다음 접속 시 알림 (notice_toast)
```

### Polling (Pull) — 폴백

```
APScheduler 30초 간격으로 pending job 상태 조회
→ 완료 감지 시 알림
```

---

## 10. 사용자 경험 예시

### RPA 호출 (비동기)
```
사용자: "세금계산서 3건 발행해줘"

Lucid: "세금계산서 발행 작업을 접수했습니다.
        - 건수: 3건
        - 예상 소요: 약 3~5분
        - 작업번호: JOB-20260312-001
        완료되면 알려드리겠습니다."

(3분 후)

Lucid: "세금계산서 발행이 완료되었습니다.
        - 성공: 3건 / 실패: 0건"
```

### MISO Workflow 호출 (동기)
```
사용자: "이번 달 Q-cost 분석해줘"

Lucid: → MISO API 호출 → 결과 수신

Lucid: "2월 Q-cost 분석 결과입니다.
        - A Site: 목표 대비 95% 달성
        - C Site: 목표 대비 72% (미달)
        상세 현황 보기 → [대시보드 열기]"
```

### 작업 상태 확인
```
사용자: "아까 세금계산서 작업 어떻게 됐어?"

Lucid: "현재 RPA 작업 현황입니다:
        1. JOB-001 세금계산서 발행 — 진행 중 (2분 경과)
        2. JOB-002 급여명세서 조회 — 완료 (10분 전)"
```

---

## 11. 향후 확장 아이디어

### 스케줄 실행
- Workspace에 스케줄 설정을 붙여서 자동 실행
- 내부 Worker(메일 요약, 뉴스 검색 등)도 스케줄 가능 (외부 서비스 불필요)
- APScheduler + DB 기반 개인별 스케줄 관리
- 별도 세션에서 상세 설계 예정

### 브라우저 확장
- Chrome Extension 기반 경량 자동화 (OS 레벨 없이 가능한 영역)
- 그룹웨어 자동 입력, 반복 양식 채우기 등

### RPA 서버 템플릿
- 부서가 쉽게 RPA 서버를 만들 수 있는 보일러플레이트 제공

### 서비스 관리 대시보드
- 서비스별 호출량, 성공률, 응답시간 모니터링
- 인기 서비스 랭킹

---

## 12. 구현 우선순위 (안)

| 순서 | 작업 | 이유 |
|------|------|------|
| 1 | Service Registry DB + CRUD API | 모든 것의 기반 |
| 2 | ExternalAgentWorker + MISOAdapter | MISO가 동기라 단순, 빠른 검증 |
| 3 | RPAAdapter + Job 추적 + Callback | 비동기 패턴 |
| 4 | Intent 동적 확장 (Registry 키워드) | 자동 라우팅 |
| 5 | Workspace Agent 활성화 UI | 사용자 경험 |
| 6 | 서비스 등록/관리 UI | 생태계 운영 |
| 7 | 권한/공유 범위 필터링 | 거버넌스 |

---

## 13. 기존 Lucid 자산 활용

이미 갖춰진 것들:
- **Worker 패턴** → ExternalAgentWorker 추가가 자연스러움
- **MCP Adapter 경험** → 외부 API 어댑터 패턴 익숙
- **스트리밍 파이프라인** → 결과 전달 인프라 완성
- **알림 시스템 (notice_toast)** → 비동기 작업 완료 알림 가능
- **관리자 대시보드 (report)** → 서비스 관리 UI 확장 가능
- **APScheduler** → 스케줄 실행 인프라 존재

기술적으로 새로운 것은 없음. 전부 기존 패턴의 확장.

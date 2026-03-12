# RPA 어댑터 설계 초안

> 작성일: 2026-03-12
> 상태: **통합 문서로 이전됨**
> 이전 위치: [AI_허브_통합_설계_초안.md](AI_허브_통합_설계_초안.md)
>
> 이 문서의 내용은 AI 허브 통합 설계 초안에 포함되었습니다.

## 1. 니즈 요약

### 목표
- Lucid AI 플랫폼에서 **자연어로 RPA 서비스를 호출**할 수 있게 한다
- 부서별 RPA 서버를 독립적으로 운영하되, Lucid에서 통합 접근 가능
- 공통 서비스는 플랫폼팀이 개발/배포하여 전사 사용

### 범위
- **포함**: 서버 기반 RPA (별도 RPA 서버에서 실행)
- **제외**: 사용자 데스크톱 직접 제어 (OS 레벨 자동화는 보안/배포 문제로 제외)
- **향후 검토**: 브라우저 확장(Chrome Extension) 기반 경량 자동화는 나중에 별도 검토 가능

### 운영 모델
```
┌──────────────────── Lucid AI Platform ────────────────────┐
│                                                            │
│  사용자 자연어 요청 → IntentClassifier → RPAAdapter         │
│                                                            │
└────────────────────────────┬───────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
      ┌──────────┐   ┌──────────┐   ┌──────────────┐
      │ 재무팀    │   │ 인사팀    │   │  공통 서비스   │
      │ RPA 서버  │   │ RPA 서버  │   │  RPA 서버     │
      │          │   │          │   │              │
      │ ·세금계산서│   │ ·입사처리 │   │ ·PDF 대량변환 │
      │ ·매출집계 │   │ ·퇴직정산 │   │ ·데이터 수집  │
      │ ·미수금관리│   │ ·근태보정 │   │ ·시스템 점검  │
      └──────────┘   └──────────┘   └──────────────┘
         부서 자율        부서 자율       플랫폼팀 관리
```

## 2. 아키텍처

### 두 계층 분리 원칙

| 계층 | 관리 주체 | 역할 |
|------|----------|------|
| Lucid 쪽 | 플랫폼팀 | RPAAdapter, Service Registry, 라우팅, Job 추적, 알림 |
| RPA 서버 쪽 | 각 부서 or 플랫폼팀 | 실제 자동화 로직 실행 (내부 구현 자유) |

### Lucid 내부 위치

```
[Orchestrator]
    ├── IntentClassifier (확장: Registry 키워드 동적 로드)
    ├── 기존 Workers (DirectWorker, MailWorker, ...)
    └── ExternalAgentWorker (신규)
            └── RPAAdapter
                ├── Service Registry 조회
                ├── Job 제출
                ├── 즉시 응답 (접수 안내)
                └── 완료 시 알림
```

### 비동기 작업 흐름

RPA는 수 분~수십 분 소요되므로 **비동기 패턴 필수**:

```
사용자: "세금계산서 3건 발행해줘"
    ↓
[RPAAdapter] → RPA 서버에 작업 제출 → job_id 발급
    ↓
즉시 응답: "작업 접수됨. 예상 5분. 완료되면 알려드리겠습니다."
    ↓
(사용자는 다른 대화 계속)
    ↓
[RPA 서버] 완료 → Callback으로 Lucid에 보고
    ↓
[Lucid] → 채팅방에 결과 메시지 삽입 or 알림 토스트
```

### Job Lifecycle

```
SUBMITTED → RUNNING → COMPLETED
                   ↘ FAILED (재시도 max 2회)
                   ↘ CANCELLED
```

## 3. Lucid 쪽 필요 구성요소

### 3-1. RPA Service Registry (DB)

```sql
CREATE TABLE rpa_services (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,          -- "매입 세금계산서 발행"
    description TEXT,                     -- Intent 분류용 설명
    department VARCHAR(50),              -- "재무팀" / "공통"
    endpoint VARCHAR(255) NOT NULL,      -- RPA 서버 API URL
    auth_type VARCHAR(20),               -- bearer / api_key
    auth_credential VARCHAR(100),        -- vault 참조 키
    input_schema JSON,                   -- 필요한 파라미터 스펙
    keywords JSON,                       -- ["세금계산서","매입","발행"]
    estimated_duration_sec INT,          -- 예상 소요 시간
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3-2. Job 추적 (DB)

```sql
CREATE TABLE rpa_jobs (
    id VARCHAR(36) PRIMARY KEY,
    service_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    session_id VARCHAR(36),              -- 요청한 채팅 세션
    request_params JSON,
    status ENUM('submitted','running','completed','failed','cancelled')
        DEFAULT 'submitted',
    result JSON,
    error_message TEXT,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    INDEX idx_user_status (user_id, status),
    INDEX idx_session (session_id)
);
```

### 3-3. Callback 엔드포인트

```python
# backend/app/api/routes/rpa.py

@router.post("/api/v1/rpa/callback")
async def rpa_callback(payload: RPACallback):
    """모든 RPA 서버가 완료 시 여기로 결과 보고"""
    await update_job(payload.job_id, payload.status, payload.result)
    await notify_user(...)  # 채팅방 메시지 삽입 or 토스트 알림
```

### 3-4. RPAAdapter 클래스

```python
class RPAAdapter:
    async def submit_job(self, service_config, params, user_id) -> RPAJob
    async def get_status(self, job_id) -> RPAJobStatus      # 폴링 폴백용
    async def get_result(self, job_id) -> RPAJobResult
    async def cancel_job(self, job_id) -> bool
```

## 4. RPA 서버 쪽 표준 API 스펙

각 부서가 RPA 서버를 만들 때 지켜야 할 **최소 인터페이스**:

```
POST   /execute          작업 실행 요청 → { job_id } 반환
GET    /status/{job_id}  상태 조회 (폴링 폴백용)
POST   /cancel/{job_id}  취소 요청

완료 시 → Lucid callback URL로 POST (권장)
```

- 내부 구현은 Python/Java/Node 등 자유
- 이 4개 API만 지키면 Lucid에 연동 가능

## 5. 결과 전달 방식

| 방식 | 설명 | 우선순위 |
|------|------|---------|
| Callback (Push) | RPA 완료 시 Lucid webhook으로 POST | **권장** |
| Polling (Pull) | Lucid가 주기적으로 상태 조회 (30초 간격) | Callback 불가 시 폴백 |

### 사용자 알림 분기

```
완료 시점에 사용자가...
├── 온라인 (채팅 중) → 채팅방에 결과 메시지 삽입
└── 오프라인          → 다음 접속 시 알림 (notice_toast 활용)
```

## 6. Intent 분류 확장

```python
# intent_classifier.py 확장

# Registry에서 키워드 동적 로드 → quick_classify에 주입
def quick_classify(query):
    # 기존 룰 먼저 (MAIL, APPROVAL, ...)
    ...
    # RPA 서비스 키워드 매칭
    for service in rpa_registry.list_active():
        if any(kw in query for kw in service.keywords):
            return Intent.EXTERNAL, {"type": "rpa", "service_id": service.id}
```

## 7. 사용자 경험 예시

```
사용자: "지난달 매입 세금계산서 3건 발행해줘"

Lucid: "세금계산서 발행 작업을 접수했습니다.

        작업 내용:
        - 유형: 매입 세금계산서
        - 건수: 3건
        - 대상 기간: 2026년 2월

        예상 소요: 약 3~5분
        작업번호: JOB-20260312-001

        완료되면 이 채팅방에서 알려드리겠습니다."

(3분 후)

Lucid: "세금계산서 발행이 완료되었습니다.

        처리 결과:
        - 성공: 3건 / 실패: 0건
        - (주)ABC 외 2건 — 국세청 전송 완료"
```

```
사용자: "아까 세금계산서 작업 어떻게 됐어?"

Lucid: "현재 RPA 작업 현황입니다:
        1. JOB-001 세금계산서 발행 — 진행 중 (2분 경과)
        2. JOB-002 급여명세서 조회 — 완료 (10분 전)"
```

## 8. 공통 서비스 배포 흐름

```
플랫폼팀이 공통 RPA 서비스 개발
    ↓
공통 RPA 서버에 배포
    ↓
rpa_services 테이블에 등록 (관리자 UI 또는 API)
    ↓
자동으로 IntentClassifier에 키워드 반영
    ↓
모든 사용자가 즉시 사용 가능
```

## 9. 향후 검토 사항

- **관리자 UI**: RPA 서비스 등록/관리 화면 (admin 페이지 확장)
- **권한 관리**: 부서별 서비스 접근 제어 (재무팀 서비스는 재무팀만 등)
- **모니터링**: Job 성공/실패율, 평균 소요 시간 대시보드
- **브라우저 확장**: Chrome Extension 기반 경량 자동화 (OS 레벨 없이 가능한 영역)
- **RPA 서버 템플릿**: 부서가 쉽게 RPA 서버를 만들 수 있는 보일러플레이트 제공

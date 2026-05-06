# 06. Runner 프로토콜

> **목적**: Hub ↔ Runner 간 통신 규격. Runner가 아웃바운드 연결만으로 Hub와 주고받는 메시지 포맷, 인증, 작업 큐, 실패 처리.

## 범위

- In scope: 통신 채널, 메시지 타입, 인증, 하트비트, 작업 큐, 결과 회송
- Out of scope: Runner 내부 실행기 (Python/PAD/VBS subprocess는 Runner 구현 디테일)

## 설계 의존성

- [02_data_model.md](02_data_model.md) ✅ `runners`, `agent_executions`
- [03_manifest_spec.md](03_manifest_spec.md) ✅ `runtime.required_labels`, `runtime.executor`
- [07_security.md](07_security.md) Runner 인증 토큰

---

## ✅ 확정: 통신 방식

| 항목 | 결정 |
|------|------|
| 채널 | **WebSocket** (양방향, 실시간 진행률) |
| 연결 방향 | **Runner → Hub** (아웃바운드, 방화벽 친화) |
| 인증 | Runner 등록 시 발급된 **토큰** (DB hash 저장) |
| 하트비트 | **30초 주기**, 5분 미수신 → `runners.status = 'offline'` |
| 작업 큐 | **Phase 1 = MySQL 테이블 기반**, Phase 2 = Redis |
| 파일 전달 | **S3 presigned URL** (Runner → S3 PUT → Hub presigned download URL 발급) |

### 연결 다이어그램

```
[Hub Backend]               [Runner EC2 (Windows)]
    │                              │
    │ ◀────── WSS connect ─────────┤  (Runner가 부팅 시 outbound)
    │                              │
    │ ────── job_dispatch ───────▶ │
    │ ◀───── job_progress ────────┤
    │ ◀───── job_result ──────────┤
    │                              │
    │ ◀───── heartbeat (30s) ─────┤
    │ ────── ping (선택) ─────────▶ │
```

---

## 메시지 타입 (8종)

### Runner → Hub

| 타입 | 시점 | 페이로드 |
|------|------|---------|
| `register` | 최초 연결 | `{runner_id, version, labels, hostname}` |
| `heartbeat` | 30초 주기 | `{runner_id, cpu_percent, memory_percent, active_jobs}` |
| `job_progress` | 작업 중 | `{job_id, percent, log_chunk}` |
| `job_result` | 작업 완료 | `{job_id, status: 'success', output_files: [s3_keys], execution_time_ms}` |
| `job_error` | 작업 실패 | `{job_id, status: 'failed', error_message, stack_trace}` |

### Hub → Runner

| 타입 | 시점 | 페이로드 |
|------|------|---------|
| `job_dispatch` | 실행 요청 | `{job_id, agent_id, runtime: {...}, args, secrets: {...}, timeout}` |
| `job_cancel` | 취소 요청 | `{job_id, reason}` |
| `shutdown` | 재시작 요청 | `{reason, drain_timeout_sec}` |

### `job_dispatch` 페이로드 예시

```jsonc
{
  "type": "job_dispatch",
  "job_id": "uuid-...",
  "agent_id": "uuid-...",
  "runtime": {
    "executor": "pad",
    "entry": "monthly_close.flow",
    "args": ["2026-04", "서울공장"],
    "timeout": 300
  },
  "secrets": {
    // SSM Parameter Store에서 fetch한 자격증명, 일회성 주입
    "SAP_USER": "...",
    "SAP_PASSWORD": "..."
  },
  "output_upload_url": "https://s3.amazonaws.com/.../presigned-PUT-url"
}
```

→ Runner는 작업 완료 후 결과 파일을 S3에 PUT, key를 `job_result`에 회신.

---

## 작업 큐 (Phase 1 = MySQL)

### 단순 큐 모델

`agent_executions` 테이블이 작업 큐 역할:
- `status = 'pending'` → 대기
- `status = 'running'` → Runner가 받아서 실행 중
- `status = 'success' / 'failed' / 'timeout'` → 종료

### 디스패치 흐름

```
1. 사용자가 Agent 실행 요청
2. Hub가 agent_executions INSERT (status='pending')
3. Runner 라우터가 required_labels 매칭되는 Runner 선택
   - 가용 Runner 중 active_jobs 적은 것 우선
4. Hub가 해당 Runner WebSocket으로 job_dispatch 송신
5. Runner ack → status='running' 갱신
6. Runner가 결과 회신 → status='success' 갱신 + S3 key 저장
```

### Phase 2 = Redis 도입 시점

- 동시 처리량 증가 (Runner 풀 ASG 도입과 같이)
- 작업 우선순위 큐 필요 시
- 실시간 큐 깊이 모니터링 필요 시

---

## 실패 / 재시도 정책

| 실패 유형 | Phase 1 정책 |
|----------|-------------|
| Runner 응답 없음 (timeout) | `status='timeout'` 후 재시도 X (사용자에게 알림) |
| Runner offline | 같은 라벨 다른 Runner로 자동 재배치 (있을 경우) |
| 매크로 자체 오류 | `status='failed'` + error_message 사용자에게 노출, 재시도 X |
| WebSocket 끊김 | Runner가 재연결 + 진행 중 작업은 status='timeout' 처리 |

→ **Phase 1은 자동 재시도 X**. 실패 시 사용자가 수동 재실행. 자동 재시도는 Phase 2.

---

## 동시 실행 제한 (Phase 1)

- **Runner당 동시 실행 = 2개** (PAD/SAP GUI 1개 + 헤드리스 Python 1개 정도)
- 한계 도달 시 큐 대기 (`status='pending'` 상태로)
- 평균 대기 시간 모니터링 → 5분 초과 시 알람 → EC2 추가 검토 (02 §runners)

---

## 파일 전달 (S3 presigned)

### 흐름

```
1. Hub가 job_dispatch 시 S3 presigned PUT URL 발급
   - 키: agent-outputs/{job_id}/{filename}
   - 만료: 1시간
2. Runner가 매크로 실행 → 결과 파일 로컬에 생성
3. Runner가 S3 PUT (presigned URL 사용)
4. Runner가 job_result에 S3 key 포함
5. Hub가 사용자에게 presigned GET URL 발급 → 다운로드
```

### 보관 정책

- S3 객체: 30일 후 자동 삭제 (또는 NAS 영구 이관 옵션)
- 사용자 다운로드 = presigned GET URL (15분 만료)

---

## Runner 측 구성 (참고)

```
ec2-cpo-01 (Windows Server)
├── LucidAI-Runner.exe        (Windows Service)
│   ├── config.yaml           (hub_url, runner_id, auth_token)
│   ├── WebSocket 클라이언트
│   ├── 작업 큐 워커 (asyncio)
│   └── 로컬 실행기 (PAD/Python/VBS subprocess)
│
└── D:/macros/                (매크로 파일들, Phase 1 디스크 / Phase 2 EFS)
    ├── monthly_close/
    │   └── monthly_close.flow
    └── ...
```

### Runner config.yaml

```yaml
hub_url: "wss://hub.lnf.co.kr/runner/ws"
runner_id: "i-0abc..."           # EC2 instance ID
runner_name: "CPO본부 Runner"
labels: ["cpo", "sap-fi", "office"]
workspace: "D:/macros/"
auth_token: "${RUNNER_AUTH_TOKEN}"   # 환경변수 또는 Parameter Store
heartbeat_interval_sec: 30
```

---

## 참고

- [00_vision.md §4](00_vision.md) — Runner 아키텍처 원안
- GitHub Actions self-hosted runner 프로토콜 (참고 레퍼런스)

## 체크리스트

- [x] 통신 채널 = WebSocket
- [x] 연결 방향 = Runner → Hub (outbound)
- [x] 메시지 타입 8종 정의
- [x] 작업 큐 = Phase 1 MySQL, Phase 2 Redis
- [x] 파일 전달 = S3 presigned URL
- [x] 인증 = Runner 토큰 (DB hash)
- [x] 하트비트 = 30초 주기
- [x] 실패 정책 = Phase 1 재시도 X
- [ ] WebSocket 연결 인증 디테일 (구현 시점)
- [ ] Lifecycle hook (ASG drain 시) — Phase 2
- [ ] Backpressure 처리 — Phase 2

# 루시드AI Hub — 사내 AI 통합 플랫폼 아키텍처 설계서

> 본 문서는 루시드AI를 챗봇에서 사내 업무 AI 통합 플랫폼(AI Hub)으로 격상하기 위한 전체 아키텍처와 설계 방향을 정리한 것입니다.

---

## 1. 현재 상태 (AS-IS)

### 1.1 기존 시스템 구성

| 시스템 | 역할 | 기술 스택 |
|--------|------|----------|
| **루시드AI** | AI 챗봇 (질의응답, 문서생성, 메일조회 등) | Next.js + FastAPI, AWS Bedrock, LangGraph |
| **L&F WIKI** | 사내 지식 베이스 | Outline Wiki (커스텀 Docker 빌드) |
| **그룹웨어(TIMS)** | 사원정보, 근태, 결재, 조직도 | 레거시 시스템, PostgreSQL |
| **MISO** | 노코드 Agent/워크플로우 빌더 | 자체 플랫폼, REST API 제공 |
| **RPA 서버** | 업무 자동화 매크로 실행 | Windows EC2, VBS/Python/BAT |

### 1.2 이미 구현된 연동

- TIMS → Wiki: 사용자 동기화 (사원번호, 이름, 이메일)
- 루시드AI → Wiki: 플로팅 챗 위젯으로 위키 내에서 루시드AI 사용
- 루시드AI → TIMS: 결재 조회, IT VOC, 회계 VOC, 메일 조회
- 루시드AI → MCP: 11개 MCP 서버를 통한 도구 연동 (PDF생성, 차트, RAG, 웹검색 등)

### 1.3 현재의 한계

- 각 시스템이 **독립적으로 운영**되어 데이터와 기능이 사일로화
- 현업이 만든 자동화(VBS, RPA, MISO 워크플로우)가 **개인/팀 내에서만 사용** — 조직 전체로 공유 불가
- 새로운 자동화를 연결하려면 **매번 개발자가 코드 작성** 필요
- 루시드AI가 할 수 있는 일이 **개발팀이 만들어둔 Worker로 한정**

---

## 2. 비전 (TO-BE): 루시드AI Hub

### 2.1 핵심 방향

> 루시드AI를 챗봇에서 **사내 업무 AI 통합 플랫폼(AI Hub)**으로 격상.
> "누구나 만들고, 누구나 쓰고, AI가 연결하는" 업무 자동화 생태계.

### 2.2 전체 구조도

```
┌──────────────────────────────────────────────────────────────┐
│                        루시드AI Hub                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  루시드AI Core                          │  │
│  │           Chat + Connect + Agent 통합 엔진              │  │
│  │                                                        │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌─────────────────┐  │  │
│  │  │   Chat   │  │   Connect    │  │  Orchestrator   │  │  │
│  │  │  자연어   │  │ 통합 연결    │  │  의도분류 +     │  │  │
│  │  │  인터페이스│  │ 레이어      │  │  액션 라우팅     │  │  │
│  │  └──────────┘  └──────────────┘  └─────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                              │                                │
│          ┌───────────────────┼───────────────────┐           │
│          ▼                   ▼                   ▼           │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ 마켓플레이스  │  │  MISO Builder  │  │   L&F WIKI     │   │
│  │              │  │                │  │                │   │
│  │ Agent/워크    │  │ 노코드 Agent/  │  │ 지식 베이스     │   │
│  │ 플로우/액션   │  │ 워크플로우     │  │ 문서 저장소     │   │
│  │ 공유 스토어   │  │ 빌더 도구      │  │                │   │
│  └──────────────┘  └────────────────┘  └────────────────┘   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    Runner Layer                        │  │
│  │         로컬 자동화 실행 (VBS, RPA, Python, BAT)        │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 각 모듈 역할

| 모듈 | 역할 | 비유 |
|------|------|------|
| **루시드AI Core** | Chat + Connect + Agent 통합 엔진. 모든 것의 중심. 사용자 요청을 이해하고, 적절한 액션을 찾아 실행하고, 결과를 전달 | iPhone |
| **MISO Builder** | 현업이 Agent/워크플로우를 직접 만드는 노코드 빌더 도구 | Xcode |
| **마켓플레이스** | 만든 것을 공유하고 내려받는 곳. 공개 범위(나만/팀/전사) 설정 가능 | App Store |
| **L&F WIKI** | 지식이 축적되는 저장소. RAG 기반 Q&A, 자동 문서 생성의 대상 | iCloud |
| **Runner Layer** | 로컬 환경에서 실행되는 자동화(VBS, RPA 등)를 허브와 연결하는 경량 상주 서비스 | Self-hosted Runner |

### 2.4 루시드 Connect의 역할

- 단순 그룹웨어 연동이 아닌, **모든 것을 자유롭게 붙이는 통합 연결 레이어**
- 커넥터 하나 만들면 Chat에서도, MISO에서도, Wiki에서도 다 쓸 수 있음
- 외부 AI 서비스(GPT, Gemini 등)도 커넥터로 붙여서 Agent 안에서 활용 가능
- **기술 기반: MCP (Model Context Protocol)** — 이미 루시드AI와 MISO 양쪽에서 지원

---

## 3. 핵심 아키텍처: 액션 시스템

### 3.1 "액션"이란?

허브에서 실행 가능한 모든 자동화 단위를 **액션(Action)**이라 부릅니다.
MISO 에이전트든, VBS 매크로든, Python 스크립트든, 외부 API든 — 허브 입장에서는 전부 "액션"입니다.

```
액션의 종류:
├── MISO 에이전트        → MISO REST API 호출
├── MISO 워크플로우      → MISO REST API 호출
├── VBS/Python/BAT 매크로 → Runner를 통한 로컬 실행
├── RPA 자동화           → Runner를 통한 RPA 서버 호출
├── 외부 REST API        → 직접 HTTP 호출
└── 루시드AI 네이티브     → 기존 Worker (웹검색, RAG 등)
```

### 3.2 통합 인터페이스 원칙

> **"이게 뭘 하고, 뭘 넣으면 뭐가 나오는지"만 표준화한다.**
> **"어떻게 실행되는지"는 어댑터/Runner 뒤에 숨긴다.**

```
허브가 보는 것:              실제 실행:
┌──────────────┐
│  액션 이름    │
│  입력 스키마  │ ──→  [어댑터/Runner] ──→ VBS / MISO / API / 뭐든
│  출력 스키마  │
└──────────────┘
```

### 3.3 액션 매니페스트 (action.yaml)

모든 액션은 동일한 매니페스트 형식으로 등록됩니다. 이것이 허브의 **핵심 표준**입니다.

```yaml
# ─── 기본 정보 ───
id: "monthly-sales-report"
name: "월간 매출 리포트"
description: "ERP 매출 데이터를 추출하여 엑셀 보고서를 자동 생성합니다"
version: "1.2.0"
author: "경영관리팀 홍길동"
icon: "📊"
tags: ["매출", "보고서", "ERP", "엑셀"]

# ─── 입력 정의 (허브가 UI 자동 생성) ───
inputs:
  - name: year_month
    label: "대상 연월"
    type: string
    placeholder: "2026-04"
    required: true
  - name: factory
    label: "공장"
    type: string
    placeholder: "서울공장"
    required: true

# ─── 출력 정의 ───
output:
  type: file            # text | file | structured
  format: xlsx

# ─── 실행 정보 ───
run:
  type: python           # vbs | python | bat | ps1 | miso | api | rpa
  entry: "daily_sales.py"
  args: ["{{year_month}}", "{{factory}}"]
  output_path: "output/sales_{{year_month}}_{{factory}}.xlsx"
  timeout: 300           # 초

# ─── 실행 환경 ───
runtime:
  runner: "finance-ec2"  # Runner 라벨 (로컬 실행 시)
  # 또는
  # endpoint: "https://api.miso.gs/ext/v1/chat"  # MISO/API 호출 시
  # app_id: "abc-123"

# ─── 공개 범위 ───
visibility: "team"       # private | team | public

# ─── 자동 실행 (선택) ───
triggers:
  - type: schedule
    cron: "0 9 1 * *"    # 매월 1일 09시
  - type: event
    source: "mail"
    condition: "new_mail_in_folder('뉴스레터')"

# ─── 필요 권한 ───
requires:
  connectors: ["erp"]
  permissions: ["erp:read", "file:write"]
```

### 3.4 매니페스트의 역할

| 소비자 | 매니페스트에서 보는 것 |
|--------|---------------------|
| **마켓플레이스** | name, description, tags, author → 검색/탐색 |
| **허브 UI** | inputs 정의 → 실행 폼 자동 생성 |
| **Orchestrator** | description, inputs/output → 자연어 라우팅 |
| **Runner** | run 섹션 → 실행 방법 결정 |
| **권한 관리** | requires, visibility → 접근 제어 |

---

## 4. Runner 아키텍처

### 4.1 Runner란?

Windows EC2 서버에 설치하는 **경량 상주 서비스**입니다.
허브로부터 실행 요청을 받아, 로컬에서 매크로/스크립트를 실행하고, 결과를 반환합니다.

### 4.2 왜 Runner인가?

| 대안 | 문제점 |
|------|--------|
| 허브가 SSH/WinRM으로 직접 접근 | 보안 구멍, 방화벽 이슈, 인바운드 포트 개방 필요 |
| 매크로마다 REST API 래핑 | 매크로 하나당 API 서버 하나 — IT가 매번 만들어줘야 함, 확장 불가 |
| 중앙 서버에서 원격 실행 | VBS/RPA는 로컬 환경 의존 (COM 객체, 파일 경로, 레지스트리 등) |
| **Runner 상주** | **아웃바운드 연결만, 로컬 실행, IT가 한 번만 셋팅, 매크로 무한 추가** |

### 4.3 Runner 구조

```
EC2 서버 (Windows)
├── LucidAI-Runner.exe          ← Windows Service로 자동 시작
│   ├── config.yaml             ← 허브 연결 정보
│   ├── 허브와 WebSocket 연결 유지
│   ├── 작업 큐 수신 → 로컬 실행
│   ├── stdout/stderr + 결과 파일 → 허브 반환
│   └── 하트비트 → 허브가 Runner 상태 파악
│
└── actions/                    ← 등록된 액션들
    ├── monthly-report/
    │   ├── action.yaml
    │   └── monthly_report.vbs
    ├── daily-sales/
    │   ├── action.yaml
    │   └── daily_sales.py
    └── pdf-converter/
        ├── action.yaml
        └── convert.bat
```

### 4.4 Runner 설정 (config.yaml)

```yaml
hub_url: "https://lucid-hub.lnf.co.kr"
runner_id: "finance-ec2-01"
runner_name: "재무팀 서버"
labels: ["finance", "rpa", "erp"]
workspace: "D:/actions/"
auth_token: "runner_xxxxx"
```

### 4.5 실행 흐름

```
사용자: "서울공장 4월 매출 리포트 뽑아줘"
    │
    ▼
루시드AI Core
    │  1. 의도 분류
    │  2. 사용자의 활성 액션 목록에서 매칭
    │  3. "월간 매출 리포트" 선택
    ▼
허브 → Runner (WebSocket)
    │  { action: "monthly-sales-report",
    │    args: { year_month: "2026-04", factory: "서울공장" } }
    ▼
Runner (EC2-Finance)
    │  action.yaml 읽기
    │  → type: python, entry: daily_sales.py
    │  → subprocess: python daily_sales.py "2026-04" "서울공장"
    │  → output/sales_2026-04_서울공장.xlsx 생성
    ▼
Runner → 허브 (결과 반환)
    │  { status: "success", output_file: "sales_2026-04_서울공장.xlsx" }
    ▼
사용자: "매출 리포트 생성 완료했습니다. [다운로드 📎]"
```

### 4.6 실행 방식별 라우팅

```
run.type에 따라 자동 분기:

  miso     → MISO REST API 직접 호출 (Runner 불필요)
  api      → 외부 REST API 직접 호출 (Runner 불필요)
  vbs      → Runner → cscript.exe 실행
  python   → Runner → python.exe 실행
  bat      → Runner → cmd.exe /c 실행
  ps1      → Runner → powershell.exe 실행
  rpa      → Runner → RPA 서버 API 로컬 호출
```

### 4.7 Runner 운영 모델

| 역할 | IT센터 | 현업 담당자 |
|------|--------|-----------|
| Runner 설치 | ✅ (최초 1회) | |
| config.yaml 설정 | ✅ (최초 1회) | |
| 매크로 개발 | | ✅ |
| action.yaml 작성 | | ✅ (웹 UI 폼으로 대체 가능) |
| 액션 등록/관리 | | ✅ |
| Runner 모니터링 | ✅ (허브 대시보드) | |

---

## 5. 마켓플레이스

### 5.1 등록 흐름

```
현업 담당자
    │
    │  1. 매크로/스크립트 개발 (기존 방식 그대로)
    │  2. 허브 웹 UI에서 "액션 등록"
    │     - 기본 정보 입력 (이름, 설명)
    │     - 입력값/출력값 설정
    │     - 실행 파일 및 Runner 지정
    │     - 공개 범위 선택
    ▼
허브가 action.yaml 자동 생성
    │
    ▼
공개 범위에 따라 노출
```

### 5.2 공개 범위 모델

```
● 나만 사용 (Private)
  → 등록 즉시 본인 채팅에서 사용 가능
  → 테스트/개인용

○ 우리 팀만 (Team)
  → 같은 팀원들도 사용 가능
  → 팀 내 업무 자동화

○ 전사 공개 (Public → 마켓플레이스)
  → 마켓플레이스에 등록
  → 관리자 승인 절차 가능
  → 전 직원이 검색/설치 가능
```

### 5.3 자연스러운 성장 흐름

```
"나만 사용"으로 만들어서 써봄
    → 괜찮네?
"우리 팀"으로 확대
    → 다른 팀에서도 쓰고 싶다
"전사 공개"로 마켓플레이스 등록
```

앱스토어에서 TestFlight(내부 테스트) → 정식 출시하는 것과 동일한 패턴.

### 5.4 사용자별 액션 활성화

마켓플레이스에 200개 액션이 있어도, **사용자가 직접 ENABLE한 것만** 해당 사용자의 채팅에서 활성화됩니다.

```
마켓플레이스 (전체 200개)
    │
    │  사용자가 골라서 ENABLE (설치)
    ▼
내 액션 목록 (예: 8개)
├── 일일 매출 리포트       ← 내가 설치
├── IT VOC 분석           ← 내가 설치
├── 뉴스레터 아카이버      ← 내가 설치
├── PDF 변환              ← 내가 설치
├── + 기본 Worker들        ← 웹검색, RAG 등 기본 탑재
│
│  이 안에서만 라우팅
▼
"서울공장 매출 보고서 만들어줘" → 8개 중 매칭
```

이 구조의 장점:
- **라우팅 정확도 향상**: 200개가 아닌 8개에서 매칭 → 오분류 위험 감소
- **불필요한 실행 방지**: 내가 쓰지 않는 액션이 실행될 일 없음
- **개인화**: 각 사용자가 자기 업무에 맞는 액션만 구성

---

## 6. 액션 라우팅 (의도 분류 → 액션 매칭)

### 6.1 현재 루시드AI의 의도 분류

```
사용자 발화
    ↓
Phase 1: quick_classify (정규식 기반, 즉시)
    → 매칭되면 → Worker 직행
    → 안 되면 ↓
Phase 2: LLM 분류 (Haiku, ~1초)
    → 10여 개 Worker 중 선택
```

### 6.2 허브 확장 후 라우팅

```
사용자 발화
    ↓
Phase 1: quick_classify (기본 Worker용, 정규식)
    → 매칭되면 → 기본 Worker 직행
    → 안 되면 ↓
Phase 2: 사용자 활성 액션 목록과 매칭 (LLM)
    → 활성 액션이 10~20개 수준이면 LLM에 목록 전달로 충분
    → 매칭되면 → 확인 후 실행
    → 해당 없으면 → 일반 대화로 폴백
```

### 6.3 안전장치: 실행 전 확인

되돌리기 어려운 작업(파일 생성, 외부 시스템 호출 등)은 실행 전 확인 단계를 거칩니다.

```
사용자: "서울공장 4월 매출 정리해줘"

루시드AI: 「월간 매출 리포트」 액션을 실행할까요?
         - 대상 연월: 2026-04
         - 공장: 서울공장
         [실행] [취소]

사용자: [실행] 클릭

루시드AI: 매출 리포트 생성 완료했습니다. [다운로드 📎]
```

---

## 7. 킬러 유즈케이스 (Phase 1)

### UC-1. 뉴스레터 요약 아카이빙
```
메일 수신 (뉴스레터)
    → 루시드AI가 메일 내용 조회 (MailWorker)
    → AI 요약 생성
    → L&F WIKI 부서 컬렉션에 자동 저장 (Wiki API)
```
**필요한 것**: Wiki 쓰기 API 연동, 트리거(새 메일 수신 시 or 스케줄)

### UC-2. IT VOC 데일리 분석 및 문서화
```
매일 09:00 자동 트리거
    → IT VOC 전일 해결 건 조회 (ITSupportWorker)
    → AI 분석 (패턴, 빈도, 개선점)
    → Wiki에 데일리 리포트 자동 생성/업데이트
```
**필요한 것**: Wiki 쓰기 API, 스케줄 트리거, 분석 로직

### UC-3. 회의록 자동 생성
```
회의 녹음/텍스트 입력
    → STT (음성→텍스트 변환)
    → AI 구조화 (참석자, 안건, 의사결정, 액션아이템)
    → Wiki에 회의록 자동 생성
```
**필요한 것**: STT 인프라, Wiki 쓰기 API, 구조화 프롬프트

### UC-4. 위키 기반 Q&A (RAG)
```
직원: "출장비 정산 기준이 뭐야?"
    → Wiki 문서 벡터 검색
    → 관련 규정 문서 기반 답변 생성
    → 출처 문서 링크 제공
```
**필요한 것**: Wiki 전용 RAG 파이프라인 강화 (현재 CorpRAGWorker 확장)

### 우선순위
```
UC-4 (Wiki RAG)     → 거의 있는 것, 빠르게 완성 가능
UC-1 (뉴스레터)      → Wiki 쓰기 API만 붙이면 됨
UC-2 (VOC 분석)     → Wiki 쓰기 + 스케줄 트리거
UC-3 (회의록)       → STT 인프라 필요, 가장 무거움
```

---

## 8. 실행 로드맵

### Phase 1 — 킬러 유즈케이스로 증명

**목표**: "와 이거 편하다"를 현업이 체감

- UC 1~4 구현
- Wiki 쓰기 API 연동 (Outline API)
- 스케줄 트리거 기본 구현
- 액션 매니페스트(action.yaml) 스키마 확정
- **이 단계에서 효과 못 만들면 이후 단계 의미 없음**

### Phase 2 — MISO 빌더 개방 + Runner 도입

**목표**: 현업이 직접 만들고 등록

- Runner 개발 및 배포
- 허브 웹 UI에 액션 등록 페이지 추가
- MISO 에이전트/워크플로우 연동
- VBS/Python/RPA 매크로 연동
- 공개 범위 설정 (Private → Team)
- "우리 부서도 이런 거 만들어달라" 수요가 터지는 시점에 맞춤

### Phase 3 — 마켓플레이스 오픈

**목표**: 부서 간 공유 생태계

- 전사 공개(Public) 마켓플레이스 오픈
- 액션 검색/설치/평가 시스템
- 외부 서비스 커넥터 생태계 확장
- 사용 통계/인기 액션 대시보드

---

## 9. 표준 체계 정리

### 9.1 우리가 정의해야 하는 표준

| 표준 | 내용 | 형태 |
|------|------|------|
| **액션 매니페스트** | 액션의 메타데이터, 입출력 스키마, 실행 방법 | action.yaml |
| **공개 범위 정책** | Private → Team → Public 단계별 공개 규칙 | 정책 문서 |
| **Runner 프로토콜** | 허브 ↔ Runner 통신 규격 (작업 수신, 결과 반환, 하트비트) | WebSocket/API 스펙 |

### 9.2 기존 표준을 채택하는 것

| 영역 | 채택 표준 | 이유 |
|------|----------|------|
| **도구 연동** | MCP (Model Context Protocol) | 이미 루시드AI + MISO 양쪽에서 사용 중 |
| **MISO 연동** | MISO REST API (`POST /ext/v1/chat`) | 이미 제공됨, 래핑 불필요 |
| **Agent 간 통신** | A2A (Google, 검토 수준) | 아직 초기이므로 당장 채택보다는 관찰 |

### 9.3 새로 만들 필요 없는 것

- **커넥터 표준**: MCP가 이미 역할 수행
- **MISO 호출 표준**: REST API 이미 존재 (`query + inputs + mode + user`)
- **워크플로우 정의**: MISO 내부 포맷 사용 (허브가 알 필요 없음)

---

## 10. 기술 아키텍처 상세

### 10.1 허브 시스템 구성

```
┌─── 프론트엔드 (Next.js) ───────────────────────────┐
│                                                    │
│  /chat                  채팅 인터페이스              │
│  /workspace             워크스페이스                 │
│  /actions               액션 목록/관리               │
│  /actions/new           액션 등록 (웹 UI 폼)        │
│  /marketplace           마켓플레이스 (탐색/설치)      │
│  /admin                 관리자 대시보드               │
│                                                    │
└────────────────────────────────────────────────────┘
                          │
                          ▼
┌─── 백엔드 (FastAPI) ──────────────────────────────┐
│                                                    │
│  기존 시스템:                                       │
│  ├── Orchestrator (의도 분류 + Worker 라우팅)        │
│  ├── Workers (Direct, WebSearch, RAG, Mail, ...)   │
│  ├── MCP Servers (PDF, Chart, YouTube, ...)        │
│  └── Services (Chat, Memory, Workspace, ...)       │
│                                                    │
│  신규 추가:                                         │
│  ├── Action Registry (액션 등록/조회/관리)           │
│  ├── Action Router (사용자 활성 액션 매칭)           │
│  ├── Runner Manager (Runner 연결/상태 관리)         │
│  ├── MISO Adapter (MISO API 호출)                  │
│  └── Marketplace Service (공개/설치/통계)           │
│                                                    │
└────────────────────────────────────────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌────────┐ ┌─────────┐
        │ Runner   │ │ MISO   │ │ 외부 API │
        │ (EC2)    │ │ API    │ │         │
        └──────────┘ └────────┘ └─────────┘
```

### 10.2 데이터 모델 (신규)

```sql
-- 액션 등록 정보
CREATE TABLE actions (
    id VARCHAR(36) PRIMARY KEY,           -- UUID
    slug VARCHAR(100) UNIQUE NOT NULL,    -- URL-friendly ID
    name VARCHAR(200) NOT NULL,
    description TEXT,
    author_id VARCHAR(50) NOT NULL,       -- 등록자 사번
    author_team VARCHAR(100),
    version VARCHAR(20) DEFAULT '1.0.0',
    icon VARCHAR(10),
    tags JSON,                            -- ["매출", "보고서"]
    manifest JSON NOT NULL,               -- action.yaml 전체 내용
    visibility ENUM('private', 'team', 'public') DEFAULT 'private',
    status ENUM('active', 'disabled', 'pending_review') DEFAULT 'active',
    install_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 사용자별 활성 액션
CREATE TABLE user_actions (
    user_id VARCHAR(50) NOT NULL,
    action_id VARCHAR(36) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, action_id)
);

-- Runner 등록 정보
CREATE TABLE runners (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,           -- "재무팀 서버"
    labels JSON,                          -- ["finance", "rpa"]
    team VARCHAR(100),
    host_info VARCHAR(200),               -- "10.0.1.50"
    status ENUM('online', 'offline', 'busy') DEFAULT 'offline',
    last_heartbeat DATETIME,
    auth_token_hash VARCHAR(256),
    config JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 액션 실행 이력
CREATE TABLE action_executions (
    id VARCHAR(36) PRIMARY KEY,
    action_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    runner_id VARCHAR(36),
    input_args JSON,
    status ENUM('pending', 'running', 'success', 'failed', 'timeout'),
    result JSON,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    execution_time_ms INT
);
```

---

## 11. 검증된 레퍼런스 모델

이 구조는 새로운 것이 아니라, 이미 검증된 모델:

| 플랫폼 | 유사점 | 루시드AI Hub 대응 |
|--------|--------|-----------------|
| **Slack** 앱 마켓플레이스 | 봇/워크플로우 설치해서 씀 | 마켓플레이스에서 액션 설치 |
| **MS Teams + Power Automate** | 현업이 워크플로우 만들고 조직 내 공유 | MISO에서 만들고 허브에 등록 |
| **Zapier / Make** | 커넥터 조합 자동화 + 템플릿 마켓 | Connect 레이어 + 마켓플레이스 |
| **GPTs Store** | 누구나 Agent 만들어서 올리고 남이 씀 | 액션 공개 범위 (Private→Public) |
| **GitHub Actions** | Self-hosted Runner로 로컬 실행 | Runner로 VBS/RPA 로컬 실행 |

루시드AI Hub = 이것들의 **사내 버전**, 루시드AI를 중심으로 통합.

---

## 12. 핵심 원칙

1. **"다 붙일 수 있다"가 목적이 아님** → "이거 붙이니까 내 일이 줄었다"가 목적
2. **Phase 1에서 체감 효과 먼저** → 플랫폼은 그 다음
3. **루시드AI가 허브** → Wiki, 그룹웨어, MISO, Runner 모두 루시드AI 아래의 모듈
4. **기존 자산 보존** → 매크로 코드 수정 없이, 매니페스트만 추가하면 연동
5. **점진적 공개** → 나만 → 팀 → 전사, 자연스러운 확산
6. **현업 자율성** → 비IT 담당자가 직접 등록/관리, IT는 인프라만 지원

---

## 13. 논의가 필요한 사항

- [ ] MISO와 루시드AI Core의 경계 — Agent 실행은 누가 담당하는가?
- [ ] Connect 레이어 기술 스택 — MCP 확장? API Gateway?
- [ ] Runner ↔ 허브 통신 방식 — WebSocket vs Long Polling vs gRPC
- [ ] 마켓플레이스 승인 절차 — 전사 공개 시 관리자 리뷰 프로세스
- [ ] 외부 AI 서비스 연동 시 보안/비용 관리
- [ ] 트리거 시스템 구현 — 스케줄(cron)은 쉽지만, 이벤트 기반은 설계 필요
- [ ] 액션 간 체이닝 — "A 결과를 B에 넣어서 실행" 오케스트레이션

---

*작성일: 2026-04-06*
*버전: 1.0*
*출처: 루시드AI 개발 에이전트 설계 논의 세션*
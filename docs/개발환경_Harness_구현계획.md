# 개발 환경 (Claude Code) 하네스 구현 계획

> 작성일: 2026-05-10
> 범위: KYK 사용자의 Claude Code 환경 전체 (사용자 전역 + 프로젝트 lucid 양쪽)
> 목적: lucid 프로젝트 백엔드에 적용된 하네스 엔지니어링 수준을 **개발 환경 자체**에도 동일하게 적용

## 0. 현재 상태 한 줄 요약

> 프로젝트 안에는 풀스펙 하네스, 프로젝트 밖(개발 환경)에는 빈손.

- `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/agents/`, `~/.claude/commands/`, `~/.claude/skills/`, `~/.claude/hooks/` — **모두 없음**
- 자동 메모리 디렉토리는 시스템이 가리키지만 **빈 상태**
- 프로젝트 `.claude/settings.local.json`에 4줄만 — 매 세션 권한 프롬프트 빈발
- MCP 서버 사용자/프로젝트 양쪽 모두 0건
- 정리: lucid 프로젝트의 `CLAUDE.md` 1개만 유일한 하네스 자산

## 1. 카테고리별 구현 계획

각 항목: **[우선순위]** **목적** / **위치·방법** / **예상 시간** / **주의점**

### A. 권한 · 세팅 (Settings)

#### A1. 프로젝트 settings.json 보강 ★ 우선순위 1
- **목적**: lucid 작업 중 반복되는 권한 프롬프트 제거
- **위치**: `lucid/.claude/settings.json` (팀 공유 가능, 현재 `.local.json`만 존재)
- **방법**:
  1. `/fewer-permission-prompts` 스킬 실행 → 최근 transcript에서 자주 쓴 read-only 명령 자동 추출
  2. 권장 allow 추가:
     - `Bash(npm run *)`, `Bash(npm install)`, `Bash(npm ci)`
     - `Bash(pip install -r requirements.txt)`, `Bash(python app/main.py)`, `Bash(python -m *)`
     - `Bash(pytest *)`, `Bash(uvicorn *)`
     - `Bash(git status)`, `Bash(git diff *)`, `Bash(git log *)`, `Bash(git show *)` (read-only git)
     - `Glob`, `Grep` (전체 허용 — read-only)
     - `Read(./**)`
  3. 권장 deny 추가:
     - `Bash(git push *)`, `Bash(git push --force *)` — 명시적 차단
     - `Bash(rm -rf *)`, `Bash(Remove-Item -Recurse -Force *)`
- **예상 시간**: 5분 (스킬 자동 추출 시)
- **주의점**: deny가 allow보다 우선. 운영용 .env 등은 settings로 막지 말고 `.gitignore`로 처리

#### A2. 사용자 전역 settings.json
- **목적**: 모든 프로젝트에 일관된 기본값
- **위치**: `~/.claude/settings.json`
- **방법**: `model`, `env` (예: `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`), 자주 쓰는 read-only 권한 (Glob/Grep/`git status`/`git diff`)
- **예상 시간**: 10분
- **주의점**: settings hierarchy는 user → project shared → project local 순으로 병합. user 단계는 정말 공통인 것만

#### A3. additionalDirectories (확장 워크스페이스)
- **목적**: lucid 외부 폴더 (예: 메모지, 별도 PoC 폴더) 를 같은 세션에서 읽기
- **방법**: `settings.local.json`의 `additionalDirectories`에 경로 추가
- **예상 시간**: 2분
- **주의점**: 프로젝트마다 다르게. 광범위하게 열면 의미 없음

### B. 메모리 · 컨텍스트 (Memory)

#### B1. 자동 메모리 부트스트랩 ★ 우선순위 3
- **목적**: 매 세션 "처음 만난 사람" 상태 탈피
- **위치**: `C:\Users\KYK\.claude\projects\c--Users-KYK-Documents-projects-lucid\memory\`
- **초기 적재 파일**:
  - `MEMORY.md` — 인덱스 (한 줄씩)
  - `user_role.md` — KYK 역할/스택/한국어 응답 선호 등
  - `project_lucid_overview.md` — LangGraph + FastAPI + Bedrock 스택 요지
  - `feedback_doc_style.md` — `docs/history/` 자동 기록 규칙 등 작업 스타일
- **예상 시간**: 15분
- **주의점**: 자동으로 채워지는 메모리이므로 첫 부트스트랩만 수동, 이후 사용자 피드백마다 자가 갱신

#### B2. 사용자 전역 CLAUDE.md ★ 우선순위 4
- **목적**: 모든 프로젝트 공통 규칙 (응답 한국어 기본, 빌드/테스트 요약 보고 등)
- **위치**: `~/.claude/CLAUDE.md`
- **권장 내용**:
  - "응답은 기본 한국어. 코드 주석/식별자는 영어"
  - "`docs/history/` 패턴이 있는 프로젝트는 자동으로 따른다"
  - "장기 작업은 TodoWrite로 추적, 단발 작업은 생략"
  - "Windows 환경 — PowerShell 스크립트 우선, Bash는 wrap된 경우에만"
- **예상 시간**: 10분
- **주의점**: 너무 많이 적으면 컨텍스트 낭비. 100줄 미만 권장

#### B3. CLAUDE.md import 활용
- **목적**: lucid의 거대한 CLAUDE.md를 모듈화 (현재 458줄)
- **방법**: `@docs/ARCHITECTURE.md`, `@docs/agent-hub/05_routing.md` 같은 import 사용 — 본문은 짧게, 필요 시 LLM이 import를 따라가게
- **예상 시간**: 30분 (기존 458줄 분리)
- **주의점**: import 외부 파일 경고가 떠도 한 번 승인하면 캐시됨

### C. 자동화 훅 (Hooks)

#### C1. 변경 이력 자동 실행 훅 ★ 우선순위 2
- **목적**: `CLAUDE.md`에 있는 "docs/history/ 자동 기록" 규칙을 자연어 약속이 아닌 **하드 강제**로
- **위치**: `lucid/.claude/settings.json`의 `hooks` 필드
- **이벤트**: `Stop` (대화 턴 종료) 또는 `SubagentStop`
- **방법**: `/update-config` 스킬로 작성. Stop hook이 Claude를 다시 호출해 "직전 턴에서 코드 변경이 일어났는지 검사 → 일어났으면 docs/history/ + CHANGELOG.md 갱신 누락 검증"
- **예상 시간**: 10분
- **주의점**: 무한루프 방지를 위해 hook 자체에서는 추가 hook을 트리거하지 않게 / 변경 없는 턴에서는 즉시 종료

#### C2. SessionStart 훅
- **목적**: 세션 시작 시 현재 상태 자동 브리핑 (git status, 마지막 history 파일, 미머지 PR)
- **이벤트**: `SessionStart`
- **방법**: 짧은 PowerShell 스크립트가 `git log -1`, `Get-ChildItem docs/history -Newest 1`, 미해결 TODO 등을 시스템 메시지로 주입
- **예상 시간**: 15분
- **주의점**: 출력이 너무 길면 매 세션 토큰 낭비. ~30줄 이내

#### C3. PostToolUse 훅 (자동 lint / format)
- **목적**: Write/Edit 후 자동으로 prettier/black/ruff 실행
- **이벤트**: `PostToolUse` (matcher: Write|Edit)
- **방법**: 변경된 파일 확장자에 따라 분기 — `.ts/.tsx` → `npx prettier -w`, `.py` → `ruff format` (있으면)
- **예상 시간**: 20분
- **주의점**: lint 에러로 hook이 실패하면 변경이 차단되므로 format만 수행, lint는 watch만

#### C4. Notification 훅 (Windows 토스트)
- **목적**: 백그라운드 작업 완료 / 권한 대기 시 윈도우 알림
- **이벤트**: `Notification`
- **방법**: PowerShell `BurntToast` 모듈 또는 `New-BurntToastNotification`
- **예상 시간**: 10분
- **주의점**: 알림 피로 — 정말 필요한 이벤트(승인 대기, 백그라운드 완료)에만

### D. 슬래시 커맨드 (Slash Commands)

#### D1. 프로젝트 워크플로우 커맨드 ★ 우선순위 5
- **위치**: `lucid/.claude/commands/`
- **권장 명령**:
  - `/lucid-dev` — 백엔드(`uvicorn`) + 프론트엔드(`npm run dev-turbo`) 동시 실행
  - `/lucid-worker <name>` — 새 워커 스캐폴드 생성 (base_worker 상속, INTENT 등록, history 파일 생성까지)
  - `/lucid-history <기능명>` — 오늘 날짜로 docs/history 템플릿 생성
  - `/lucid-mcp-restart` — `mcp_config.json` 변경 후 백엔드 MCP 클라이언트 재기동
  - `/lucid-token-audit` — 최근 워커 호출의 토큰 사용량 점검 (workspace memory + base_worker 압축이 잘 동작하는지)
  - `/lucid-deploy-check` — Blue/Green 배포 전 체크리스트 자동 수행
- **예상 시간**: 명령당 5–15분
- **주의점**: 명령 이름은 고유해야 함. 공식 명령(`/init`, `/review`, `/security-review`)과 충돌 X

#### D2. 사용자 전역 커맨드
- **위치**: `~/.claude/commands/`
- **권장**: `/k-한국어`, `/git-safe-push` (force 차단 검증), `/cost-summary` 등 모든 프로젝트 공통

### E. MCP 서버 (외부 도구)

#### E1. 데이터베이스 MCP ★ 우선순위 6
- **목적**: 개발 중 직접 쿼리·확인이 잦음 (lucid는 MySQL + ChromaDB + SQLite + PostgreSQL 모두 사용)
- **위치**: `lucid/.mcp.json` (팀 공유) 또는 `~/.claude.json`의 mcpServers
- **권장 서버**:
  - `mysql` (또는 `postgres`) — chat_log, workspace_memory 직접 점검
  - `sqlite` — ChromaDB 메타데이터 확인
- **방법**:
  ```json
  {
    "mcpServers": {
      "lucid-mysql": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-mysql"],
        "env": { "MYSQL_HOST": "...", "MYSQL_USER": "..." }
      }
    }
  }
  ```
- **예상 시간**: 20분 (인증·테스트 포함)
- **주의점**: **운영 DB 자격증명을 settings.json에 넣지 말 것** — `.env` + `${env:VAR}` 보간 사용. 기본은 read-only 계정

#### E2. Filesystem MCP (확장 디렉토리)
- **목적**: lucid 외부의 자료 폴더 (R&D 문서, 회의록 등) 안전 접근
- **권장**: `@modelcontextprotocol/server-filesystem`, 허용 디렉토리 화이트리스트로 제한

#### E3. Lucid 자체 MCP 서버를 dev tool로 노출
- **목적**: lucid 백엔드의 PDF/차트/RAG MCP 서버를 Claude Code에서도 직접 호출 가능하게
- **방법**: `mcp_config.json`을 그대로 Claude Code의 `.mcp.json`에 매핑 (재사용)
- **효과**: 새 워커 개발 시 도구를 즉석에서 호출해 검증

### F. 서브에이전트 (Subagents)

#### F1. 도메인 특화 subagent 정의
- **위치**: `lucid/.claude/agents/`
- **권장 정의**:
  - `langgraph-debug` — 워커 ReAct 루프 분석 / state 추적 / handoff 마커 검증
  - `bedrock-cost-analyst` — token usage 로그 분석 / Haiku vs Sonnet 비용 비교
  - `mcp-tool-validator` — 새 MCP 도구의 schema·반환·에러 처리 점검
  - `lucid-worker-reviewer` — 새 워커 추가 시 base_worker 일관성 / INTENT_TO_WORKER 등록 / docs/history 누락 점검
- **예상 시간**: agent당 15–30분
- **주의점**: subagent는 자체 컨텍스트를 가지므로 "맥락 없이 던져진" 상황에 강해야 함

### G. 스킬 (Custom Skills)

#### G1. 프로젝트 specific skills
- **위치**: `lucid/.claude/skills/`
- **권장**:
  - `lucid-init` — 새 워커/MCP 추가 시 부트스트랩 (파일 생성, 등록, 테스트, history 4단 자동화)
  - `lucid-token-audit` — 토큰 사용량 분석 + 압축/캐싱 적용 누락 탐지
- **차별점**: slash command와 달리 skill은 LLM이 트리거 조건을 자율 판단. "새 워커를 만들어줘"라고만 해도 자동 발동

### H. 상태바 · 키바인딩

#### H1. statusline 커스터마이즈
- **위치**: `~/.claude/statusline.sh` (또는 PowerShell 버전)
- **표시 후보**: 현재 git 브랜치, last `docs/history` 파일, 누적 토큰 사용량, 현재 모델
- **방법**: `/statusline` 슬래시 명령으로 설정 (statusline-setup 에이전트가 도와줌)
- **예상 시간**: 10분

#### H2. keybindings.json
- **위치**: `~/.claude/keybindings.json`
- **권장**: 자주 쓰는 chord — `Ctrl+K Ctrl+L` (lucid-dev), `Ctrl+K Ctrl+H` (lucid-history) 등
- **예상 시간**: 5분

### I. 출력 스타일 (Output Styles)

#### I1. 작업 모드별 스타일
- **explanatory mode** — 새 영역 학습 시 (예: 처음 만지는 프론트 영역)
- **learning mode** — 의도적으로 사용자가 직접 코드 작성하고 싶을 때
- **위치**: 시스템 활성화된 plugin (`explanatory-output-style`, `learning-output-style`)이 이미 켜진 상태로 보임 — 즉시 활용 가능

### J. 장기 자동화 (Loop / Schedule)

#### J1. 일일 / 주간 자동 작업
- **방법**: `/schedule` 스킬로 routine 등록 (cron schedule)
- **권장**:
  - **매일 18:00**: 그날 변경된 파일 → `CHANGELOG.md` 자동 점검 / 누락 history 발견 시 알림
  - **매주 월 09:00**: 미사용 import / dead code 정리 후보 리스트
  - **매주 금 17:00**: 워크스페이스 메모리 일관성 점검 (롤링 요약이 정상 갱신되는지)
- **예상 시간**: routine당 10분

#### J2. /loop 활용 (단기 폴링)
- **예시**: 백엔드 빌드/테스트가 길어질 때 `/loop 3m /lucid-test-status` 같이 짧은 폴링

### K. 1P (Anthropic 공식) 플러그인 활성화

시스템 config에 노출된 plugin 목록 중 즉시 가치 있는 것:
- **`security-guidance`** — 보안 검토 자동 보강 (lucid의 security_guard와 별개로, 코드 변경 시점에 적용)
- **`code-review`** — PR 전 사전 검토
- **`commit-commands`** — 커밋 메시지 일관성
- **`hookify`** — 위 C1~C4 hook 작성 보조
- **`claude-md-management`** — CLAUDE.md 자동 정리 (현재 458줄 정리에 유용)
- **`pr-review-toolkit`** — `/ultrareview`와 다른 경량 PR 검토
- **`pyright-lsp`** — Python 타입 체크 통합 (lucid 백엔드 즉시 효과)
- **`typescript-lsp`** — TS 타입 체크 (lucid 프론트엔드)

활성화: `/plugin` 명령 또는 marketplace UI

### L. 관측 / 텔레메트리

#### L1. 토큰 사용량 추적
- **방법**: lucid의 `docs/history/2026-03-10_TokenUsageMonitoring.md` 흐름을 Claude Code 자체 사용량에도 적용
- **권장**: PostToolUse hook으로 매 도구 호출 후 사용량 누적 → 일일 요약을 `~/.claude/projects/.../memory/`의 reference 메모로 적재

### M. 워크트리 / 격리

#### M1. 큰 변경 시 worktree 강제
- **방법**: 사용자 글로벌 메모리에 "파일 5개 이상 동시 수정 시 `Agent({isolation: 'worktree'})` 사용" 규칙
- **효과**: 실패 시 깔끔히 폐기 가능 / 동시 작업 안전

## 2. 단계별 로드맵 (제안)

### Phase 1 — 즉효 (총 30분)
1. A1: 프로젝트 settings.json 보강 (5분)
2. C1: 변경 이력 자동 hook (10분)
3. B1: 자동 메모리 부트스트랩 (15분)

→ 이 3개만 해도 매 세션 권한 프롬프트가 사라지고, 누락 없이 history가 적재되며, 매 세션 사용자 컨텍스트를 자동 회복.

### Phase 2 — 워크플로우 가속 (총 1.5시간)
4. B2: 사용자 전역 CLAUDE.md (10분)
5. D1: lucid-dev / lucid-worker / lucid-history 슬래시 커맨드 (45분)
6. E1: 데이터베이스 MCP (20분)
7. K: 1P 플러그인 활성화 (pyright/typescript-lsp, claude-md-management, hookify) (15분)

### Phase 3 — 심화 자동화 (총 2시간+)
8. C2/C3: SessionStart + PostToolUse hooks
9. F1: 도메인 특화 subagent 4종
10. G1: 커스텀 skill 2종
11. J1: 정기 routine 등록
12. M1: 워크트리 규칙 정착

## 3. 위험 / 주의점

- **권한 deny가 allow보다 우선**: 잘못된 deny는 정상 작업도 막음. 처음엔 deny 최소화
- **Hook 무한루프**: Stop hook이 Stop을 다시 트리거하지 않게 — 보호 로직 필수
- **MCP 자격증명 유출**: settings.json은 git에 들어갈 수 있음. `${env:...}` 보간 + `.gitignore` 필수
- **CLAUDE.md 비대화**: 470줄 넘으면 잘림 / 토큰 낭비. import 분리 (B3) 우선
- **자동 메모리 신뢰 한계**: 메모리에 적힌 파일 경로는 stale일 수 있음 — 추천 전 `Glob`/`Read`로 검증 필수 (시스템 instruction의 "Before recommending from memory" 규칙)

## 4. 한 줄 결론

**Phase 1만 해도 lucid 작업 속도는 바로 30~50% 빨라집니다.** lucid 백엔드 하네스 설계 노하우를 그대로 자기 개발 환경에도 이식하면 됩니다.

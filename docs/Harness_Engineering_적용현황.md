# 루시드AI 프로젝트 — 하네스 엔지니어링 적용 현황

> 작성일: 2026-05-10
> 범위: `LucidNextGen/backend` 에이전트 파이프라인 전체
> 비교 기준: Anthropic "Effective harnesses for long-running agents", Martin Fowler "Harness engineering for coding agent users", Addy Osmani "Agent Harness Engineering" (2026)

## 0. 하네스 엔지니어링 핵심 개념 (2026 최신)

> **Agent = Model + Harness.** 모델은 두뇌, 하네스는 골격(권한·메모리·도구·루프·관측·핸드오프). 신뢰할 수 있는 production agent의 차이는 모델 성능이 아니라 **하네스 설계**에서 나옵니다.

핵심 패턴:
- **계획 분해(Plan → DAG)**: 복합 요청을 의존성 있는 sub-task로 쪼갬
- **상태 공유(Blackboard / 스냅샷)**: 병렬/순차 task 간 결과 인계
- **메모리 계층(롤링 요약 / 핵심 사실)**: 장기 연속성
- **권한·검증(가드 / HITL)**: 위험 행위 차단·승인
- **컨텍스트 관리(캐싱 / 압축 / 요약)**: 토큰 폭주·context rot 방지
- **관측(타이밍 / 내레이션 / 마커)**: 사용자/운영자 가시성
- **세션 브리징(긴 작업의 핸드오프)**: 컨텍스트 윈도우를 넘어 작업 지속

## 1. 적용 컴포넌트 매핑

### A. Planner → Executor → Synthesizer 파이프라인
| 컴포넌트 | 파일 | 역할 |
|---|---|---|
| Planner | `backend/app/agents/planner.py` | 요청을 Task DAG(JSON)로 분해. `is_trivial`이면 단일 task, 복합은 `depends`로 의존성 명시 |
| Executor | `backend/app/agents/executor.py` | 위상정렬 + `asyncio.gather` 병렬 (`MAX_PARALLEL_TASKS=10`, `TASK_TIMEOUT_SECONDS=300`). `_StreamTagFilter`로 청크 경계 안전한 태그 정화 |
| Synthesizer | `backend/app/agents/synthesizer.py` | Haiku로 sub-task 결과 합성. hallucination 금지 / 중복 제거 / 승인 대기 표시 강제 |
| Blackboard | `backend/app/agents/blackboard.py` | Task 결과 공유 저장소. `asyncio.Lock`으로 race 방지, **요청 생명주기 동안만 유효** |

### B. Orchestrator 다단 Phase 구조 (`backend/app/agents/orchestrator.py`)

| Phase | 역할 |
|---|---|
| -1 | Security Guard 사전 검사 |
| 0a / 0b | User Memory + Workspace Memory 로드 (컨텍스트 주입) |
| 0.5 | External Agent Router (워크스페이스 부착 외부 에이전트 우회) |
| 1 / 1.0 | Intent Classifier(Haiku) **또는** Planner-Executor 신경로 |
| 1.5 / 1.8 | CLARIFY 모드 + Workspace-first 라우팅 오버라이드 |
| 2 | Worker dispatch + **tool fallback** (도구 0개 → DirectWorker) |
| 4.5 / 5 / 6 | Workspace fallback / **HANDOFF**(cross-worker 데이터 요청) / **NO_RESULTS fallback**(2순위 워커 자동 실행) |

### C. 라우팅 Single Source of Truth
`backend/app/agents/routing_guide.py` — `DOMAIN_ROUTING_GUIDE`를 `intent_classifier`와 `planner` 두 분류기가 동일하게 주입. 2026-04-30 운영에서 두 경로의 라우팅 결함이 따로 수정되던 문제를 단일 원천화로 해결.

### D. 메모리 계층
- **User Memory** — 모든 세션 공유, 핵심사실 누적
- **Workspace Memory** — 롤링 요약(~500자) + 핵심사실(최대 10개), 10메시지마다 비동기 갱신
- **Conversation Summarization** — `base_worker.py` 멀티턴 토큰 누적 방지 (12메시지/15K자 임계치)
- **Tool result compaction** — `COMPACT_KEEP_RECENT_PAIRS=1`, ReAct 루프 토큰 폭증 방지

### E. 컨텍스트 / 캐시 최적화
- `CachedChatBedrockConverse` — system prompt에 **Bedrock cachePoint 자동 주입**, 입력 토큰 90% 절감
- `AGENT_RECURSION_LIMIT=20` — 도구 호출 루프 폭주 방지
- Region fallback / Inference profile 자동 폴백

### F. 보안 가드 (다층 방어)
`backend/app/agents/security_guard_agent.py` — rule-based 1차 → Haiku LLM 2차. 일일 한도 / 타임아웃 / 한도 초과 시 graceful degradation. 위협 분류(INJECTION / JAILBREAK / DATA_EXFIL / PRIVILEGE_ESCALATION / MALICIOUS_CONTENT)와 0–100 심각도.

### G. HITL (Human-in-the-loop) 승인
Planner가 쓰기 작업(예약·결재·메일 발송 등)에 `needs_confirm=true`를 강제 → Executor가 해당 task를 일시 중단 → Synthesizer가 사용자에게 **"진행할까요?"** 표로 제시.

### H. 관측 가능성 / UX
- `narrator.py` — 도구 호출을 1줄 한국어 내레이션으로 변환 (Haiku, fire-and-forget)
- `orchestrator_timing` 이벤트로 단계별 ms 측정 (classify / worker / executor / synthesizer / fallback)
- 마커 기반 제어 흐름: `<!--NO_RESULTS-->`, `<!--HANDOFF:intent-->`

### I. 장기 실행 (cron-driven agents)
`cron_runner.py` + `cron_scheduler.py` — Anthropic의 "long-running agent" 패턴 응용. 새 `chat_session`(auto_generated=1)을 발급하고, 결과를 `user_notifications`에 적재해 **세션 간 핸드오프**를 구현.

### J. Worker 격리 / 도메인 배타성
- 워커별 도구 필터링 (`filter_tools`), 도메인별 단일 워커 원칙
- IT/회계는 규정 docs + VOC를 한 워커에 통합
- Tool fallback / Region fallback / Inference profile 자동 폴백

### K. 운영 자기 문서화
`CLAUDE.md` 422–457줄 — 코드 변경 시 `docs/history/YYYY-MM-DD_*.md` + `CHANGELOG.md` 자동 업데이트 규칙. Anthropic의 "progress tracking file" / "session bootstrapping" 패턴과 일치.

## 2. 업계 권장 패턴 대비 커버리지

| 권장 패턴 | 적용 여부 | 위치 / 비고 |
|---|---|---|
| Plan → DAG 분해 | ✅ | `planner.py` |
| 병렬 실행 + 의존성 | ✅ | `executor.py` (`asyncio.gather`) |
| Blackboard / 상태 공유 | ✅ | `blackboard.py` |
| 결과 합성 / 중복 제거 | ✅ | `synthesizer.py` |
| 장기 메모리 (롤링 요약) | ✅ | `memory_service.py` |
| 컨텍스트 캐싱 | ✅ | `CachedChatBedrockConverse` |
| 멀티턴 압축 / 요약 | ✅ | `base_worker.py` |
| 보안 가드 (LLM-as-judge) | ✅ | `security_guard_agent.py` |
| HITL 승인 게이트 | ✅ | `needs_confirm` |
| Tool / Region 폴백 | ✅ | tool_fallback, region_fallback |
| Cross-agent 핸드오프 | ✅ | HANDOFF 마커 / cron_runner |
| 관측 / 타이밍 이벤트 | ✅ | `orchestrator_timing`, narrator |
| 세션 브리징 (자동화) | ✅ | cron_runner + user_notifications |
| **Worktree 격리 (코드 변경형)** | ➖ | 본 시스템은 read/write 분리 + needs_confirm으로 대체 |
| **Init agent / 부트스트랩 진단** | ➖ | 운영 자동화 없음 — 다음 개선 후보 |

## 3. 한 줄 요약

루시드AI는 **Planner-Executor-Synthesizer + Blackboard + 다층 메모리 + 가드 + HITL + 폴백 그래프 + 캐싱·압축**까지, 2026년 기준 하네스 엔지니어링이 권장하는 거의 모든 패턴을 LangGraph + Bedrock 위에 자체 구현한 케이스입니다.

## 4. 참고 자료

- [Effective harnesses for long-running agents — Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Harness engineering for coding agent users — Martin Fowler](https://martinfowler.com/articles/harness-engineering.html)
- [Agent Harness Engineering — Addy Osmani](https://addyosmani.com/blog/agent-harness-engineering/)
- [Skill Issue: Harness Engineering for Coding Agents — HumanLayer](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents)
- [Building Claude Code with Harness Engineering — Fareed Khan](https://levelup.gitconnected.com/building-claude-code-with-harness-engineering-d2e8c0da85f0)
- [awesome-harness-engineering — GitHub](https://github.com/ai-boost/awesome-harness-engineering)

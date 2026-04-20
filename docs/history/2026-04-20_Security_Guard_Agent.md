# 2026-04-20 Security Guard Agent

## 개요
악의적 사용자 입력(프롬프트 인젝션, jailbreak, 데이터 탈취, 권한 탈취 시도 등)을 탐지·차단하고 관리자에게 이메일로 알리는 보안관 에이전트 추가. 누적 위반 시 자동 승격 차단(WARN→TEMP_BLOCK→PERM_BLOCK)과 `/admin/report` 내 보안 모니터링 탭 제공.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/migrations/add_security_guard_tables.sql | 신규 | 3개 테이블 (events, blocks, llm_daily_usage) |
| backend/app/services/security_guard_service.py | 신규 | 핵심 서비스 (rule + rate + block + noti) |
| backend/app/agents/security_guard_agent.py | 신규 | LLM 분류기 (Haiku, 일일 한도) |
| backend/app/api/routes/admin_security.py | 신규 | 관리자 API 7개 |
| backend/app/agents/orchestrator.py | 수정 | Phase -1 Security Check 추가 |
| backend/app/agents/a2a_streaming.py | 수정 | security_blocked 이벤트 SSE 전달 |
| backend/app/api/routes/chat.py | 수정 | 차단 사용자 조기 단절 게이트 |
| backend/app/api/routes/chat_a2a.py | 수정 | A2A 경로 차단 게이트 |
| backend/app/main.py | 수정 | admin_security 라우터 등록 |
| frontend/lib/api/security.ts | 신규 | API 클라이언트 |
| frontend/components/dashboard/security-tab.tsx | 신규 | 보안 대시보드 탭 |
| frontend/app/admin/report/page.tsx | 수정 | 탭 구조 추가 (서비스/보안) |
| frontend/hooks/use-simple-chat.ts | 수정 | security_blocked 이벤트 처리 |
| docs/Security_Guard_Agent_설계안.md | 신규 | 설계 문서 |

## 상세 내용

### 3-Layer 탐지
1. **Rule-based** (모든 요청, 정규식 27개): INJECTION/JAILBREAK/DATA_EXFIL/PRIVILEGE/MALICIOUS
2. **Rate-limit** (in-memory sliding window): 분당 20회/40회 + 동일 메시지 5회 연속
3. **LLM-based** (Haiku, rule 의심 30+ 시만): 문맥 기반 재판정, 일일 한도 1000회

### 5-Tier 대응
| 점수 | 동작 | 알림 |
|------|------|------|
| 0-29 | PASS | 없음 |
| 30-49 | WARN | 로그 |
| 50-69 | BLOCK_REQUEST | 로그 |
| 70-84 | TEMP_BLOCK (24h) | 관리자 메일 |
| 85-100 | PERM_BLOCK | 관리자 메일 |

**누적 승격**: WARN 5회/24h → TEMP_BLOCK, TEMP_BLOCK 3회/30d → PERM_BLOCK

### 통합 지점
- **Orchestrator Phase -1**: intent 분류보다 먼저 체크 → 위협 시 워커 실행 전 단절
- **chat.py / chat_a2a.py**: MCP 로딩 전 조기 단절 (이미 차단된 사용자)
- **차단 캐시**: TTL 60초 (관리자 해제 반영 최대 1분 지연 허용)

### 주요 환경변수
```env
SECURITY_GUARD_ENABLED=true
SECURITY_LLM_THRESHOLD=30             # 이 이상 시 LLM 호출
SECURITY_BLOCK_REQUEST_THRESHOLD=50
SECURITY_TEMP_BLOCK_THRESHOLD=70
SECURITY_PERM_BLOCK_THRESHOLD=85
SECURITY_WARN_LIMIT=5                 # 24h 내 WARN N회 → TEMP_BLOCK
SECURITY_TEMP_BLOCK_LIMIT=3           # 30d 내 TEMP_BLOCK N회 → PERM_BLOCK
SECURITY_TEMP_BLOCK_HOURS=24
SECURITY_RATE_WARN_PER_MIN=20
SECURITY_RATE_BLOCK_PER_MIN=40
SECURITY_LLM_DAILY_LIMIT=1000         # 비용 폭탄 방지
SECURITY_LLM_TIMEOUT_SEC=3
SECURITY_NOTIFY_MIN_SEVERITY=70
SECURITY_ADMIN_EMAILS=admin@lf.co.kr
SECURITY_WHITELIST_USER_IDS=          # 디버깅용
```

### 관리자 API (`/api/v1/admin/security/*`)
- `GET /events` — 이벤트 목록 (필터: user, threat, action, severity, 날짜)
- `GET /events/{id}` — 이벤트 상세
- `GET /blocks` — 차단 사용자 목록
- `DELETE /blocks/{user_id}` — 차단 해제
- `GET /stats` — 집계 통계 (대시보드용)
- `POST /dry-run` — 판정 테스트 (차단 없이 분류만)
- `GET /llm-usage` — 오늘 LLM 호출 수/한도

### 프론트엔드
- `/admin/report` 페이지에 **탭** 추가 (서비스 리포트 / 보안 모니터링)
- 보안 탭 구성:
  - KPI 카드 (총 이벤트, 경고, 거부, 차단, 현재 차단자)
  - LLM 사용량 (일일 한도 대비 %)
  - 일별 이벤트 추이 (LineChart)
  - 위협 유형 분포 (PieChart)
  - 상위 위반 사용자 Top 10
  - 현재 차단 사용자 (해제 버튼)
  - 최근 50건 이벤트 (상세 모달)
  - 판정 테스트 (Dry-Run) — 패턴 튜닝용

### 사용자 응답
차단 시 사용자 메시지에 **위협 타입 + 해제 예정 시각**을 노출하여 투명성 확보:
```
⛔ 계정이 일시 차단되었습니다.
사유: 프롬프트 인젝션 시도
해제 예정: 2026-04-21 14:30
반복 시 영구 차단될 수 있습니다.
```

## 결정 사항 및 주의점

### 의도적 선택
- **Dry-run 없이 즉시 활성화**: 사용자 요청. 대신 모니터링 강화 + 낮은 임계값에 WARN 배치로 오탐 관찰 가능
- **INPUT만 검사**: 사용자 요청. Post-exec 검사는 제외 (결과에서 PII 탐지 등)
- **Haiku LLM**: 비용/지연 최소화. rule 의심 시만 호출로 대부분 요청엔 영향 無
- **일일 LLM 한도 1000회**: 악성 사용자의 반복 공격에 의한 비용 폭탄 방지
- **이메일 알림**: 기존 `email_service.py` (SMTP) 재활용
- **in-memory rate limit**: blue/green 독립 카운팅, 단일 프로세스 기준 — 멀티프로세스 정밀 제어 필요 시 Redis 전환

### 알려진 제약
- **오탐 가능성**: Rule 패턴은 한국어 편중 + 단순 매칭 → 업무 표현이 걸릴 수 있음 (예: "시스템 프롬프트 작성법 알려줘"는 rule 65점이지만 LLM이 통과시킬 것으로 기대). 운영 중 로그 보고 패턴 조정 필요
- **LLM 한도 초과 시**: rule 점수만으로 판정 → 특히 정교한 공격은 탐지 누락 가능
- **rate limit 프로세스 독립**: blue/green 2개 프로세스 운영 시 실 분당 한도는 2배로 계산됨
- **초기 2주 운영 모니터링 필수**: `SECURITY_WHITELIST_USER_IDS`에 관리자/본인 ID 추가해두고 대시보드에서 오탐 케이스 확인 후 패턴 튜닝

### 운영 시작 체크리스트
1. [ ] DB 마이그레이션 실행 (`migrations/add_security_guard_tables.sql`)
2. [ ] `.env`에 `SECURITY_ADMIN_EMAILS` 설정
3. [ ] `.env`에 `SECURITY_WHITELIST_USER_IDS`에 관리자 사번 추가 (오탐 격리)
4. [ ] SMTP 설정(`SMTP_HOST`, `SMTP_FROM_EMAIL`) 확인 — 없으면 노티 미발송
5. [ ] blue/green 재시작
6. [ ] `/admin/report` → 보안 탭에서 실시간 모니터링

### 향후 개선 과제
- Rule + LLM 점수 결합 방식 개선 (현재 max 기준 → LLM NONE 판정 시 rule 점수 감쇠)
- 오탐/정탐 피드백 UI (대시보드에서 이벤트를 "오탐" 마킹 → 패턴 튜닝 데이터 누적)
- Post-exec 검사 (옵션 확장 시)
- Redis 기반 멀티프로세스 rate limiter
- 이상 패턴 자동 학습 (주 단위 집계 후 신규 rule 제안)

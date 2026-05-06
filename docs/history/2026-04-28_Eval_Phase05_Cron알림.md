# 2026-04-28 Eval Phase 0.5 — Cron + 회귀 알림 메일

## 개요
Phase 0(엔진 + POC 케이스)에 이어 cron 자동 실행 + 어제 대비 신규 실패만 메일 알림하는 워크플로 구축. 매일 03:00 활성 운영 슬롯(blue/green)에 e2e 실행, 결과는 `results/latest.json` + DB(`eval_runs`/`eval_results`)에 누적, 신규 회귀나 회복이 있을 때만 관리자 메일 발송.

## 변경 파일 요약

| 파일 | 유형 | 설명 |
|---|---|---|
| backend/tests/eval/diff.py | 신규 | 이전/현재 실행 결과 비교 → new_failures/new_case_failures/recovered/persistent_failures/errors 분류 |
| backend/tests/eval/notifier.py | 신규 | DiffReport → HTML 메일 본문 + smtplib 직접 발송 (EmailService 의존 X) |
| backend/tests/eval/run.py | 수정 | `--notify-on-regression` 플래그, 실행 전 latest.json → previous.json 회전, 실행 후 diff + notify |
| backend/tests/eval/reporter.py | 수정 | `RESULTS_DIR` export (run.py에서 회전 경로용) |
| backend/tests/eval/register_cron.bat | 신규 | `schtasks /create`로 매일 03:00 SYSTEM 권한 등록 |
| backend/tests/eval/run_daily.bat | 신규 | cron entry point — .env에서 EVAL_API_KEY 로드, 활성 슬롯 자동 감지(`deploy/state.txt`), 로그 파일 기록 |
| backend/tests/eval/cases/web_search.yaml | 신규 | tavily_search 호출 회귀 2건 |
| backend/tests/eval/cases/corp_rag.yaml | 신규 | search_hr_docs/search_it_docs 회귀 2건 |
| backend/tests/eval/cases/routing.yaml | 신규 | CLARIFY/URLFetch/YouTube 라우팅 회귀 3건 |

## 상세 내용

### Diff 분류
케이스를 case_id 기준으로 비교:
- **new_fail**: 이전 PASS → 이번 FAIL → 진짜 회귀 의심 (메일 알림)
- **new_case_fail**: 이전엔 없던 케이스가 FAIL → 케이스 작성 시 검증 단계 (메일 알림)
- **recovered**: 이전 FAIL → 이번 PASS → 좋은 소식 (메일 알림)
- **error**: HTTP/네트워크 에러 → 인프라 이슈 (메일 알림)
- **persistent_fail**: 이전·이번 모두 FAIL → 이미 알림 갔음 (조용히 details로 첨부)
- **persistent_pass**: 늘 PASS → noise (기록 X)

### 회전 전략
실행 전: `results/latest.json`이 있으면 `results/previous.json`으로 복사 → `save_json()`이 새 latest로 덮어씀 → diff는 새 latest vs previous 비교. file 기반이라 DB 의존 없음, deterministic.

### 메일 본문
HTML 카드 형식, 5개 섹션(신규 실패 / 신규 케이스 실패 / 인프라 에러 / 회복 / 지속 실패). 각 카드는 case_id + intent/worker + duration_ms + 실패한 assertion + 응답 200자 미리보기. 지속 실패는 `<details>`로 접어둠(noise 차단).

### 수신자
환경변수 우선순위: `EVAL_ALERT_EMAILS` (쉼표 구분) > `ADMIN_ALERT_EMAIL` (.env에 이미 `wg0403@landf.co.kr` 있음) > 메일 발송 스킵.

### Cron entry point (`run_daily.bat`)
1. `C:\Services\LFChatbot_prod\deploy\state.txt`에서 활성 슬롯(blue/green) 읽음 → `EVAL_BACKEND_URL` 자동 결정 (8001/8002)
2. `backend/.env`에서 `EVAL_API_KEY=` 라인 파싱 → 환경변수 set
3. `EVAL_DEFAULT_EMPNO=A2304013` (관리자 본인)
4. `python -m tests.eval.run --all --persist --notify-on-regression --triggered-by cron`
5. stdout/stderr를 `tests/eval/results/eval_daily.log`에 append

### 케이스 확장 (총 13개)
- direct: 3 (Phase 0)
- web_search: 2 (tavily_search 호출 회귀)
- corp_rag: 2 (search_hr_docs/search_it_docs 호출 회귀)
- routing: 3 (CLARIFY/URLFetch/YouTube cross-cutting 라우팅)

## 결정 사항 및 주의점

### 알림함은 Phase 1로 미룸
관리자 알림함이 frontend `MOCK_PERSONAL` 하드코딩(LocalStorage 기반)이라 영속화하려면 백엔드 테이블 + API + 프론트 fetch 전환이 필요. Phase 0.5 범위가 너무 커지므로 Phase 1(`/admin` 통합 콘솔)에서 함께 처리. 그때는 별도 alert 테이블 만들지 않고 `eval_results` WHERE status=fail을 직접 쿼리해 보여주는 게 데이터 흐름이 깔끔.

### EmailService 의존 안 함
notifier.py는 backend의 `EmailService`를 import하지 않고 smtplib + dotenv로 직접 발송. 이유: eval은 가벼운 도구라 backend 전체 import 트리(DBUtils, langchain 등)에 묶이면 venv 격리/배포 단순성 손해. SMTP 설정은 backend `.env`와 동일 (SMTP_HOST/PORT/USERNAME/PASSWORD/USE_TLS/FROM_EMAIL).

### 운영 슬롯 자동 감지
dev 8099가 아니라 운영 활성 슬롯(blue=8001, green=8002)에서 실행. `deploy/state.txt`로 매번 결정 — 무중단 전환 후에도 자동으로 새 슬롯에 붙음.

### 회귀 예외 케이스
- **case yaml의 id를 변경**하면 diff에서 별개 케이스로 인식 → "이전 케이스 사라짐 + 새 케이스 등장"으로 잘못 알림. 운영 정착 후 id는 변경 금지.
- **첫 실행 (previous 없음)**: 모든 FAIL을 new로 분류. 이메일에 "최초 실행" 배너 표시.

### 운영 적용 체크리스트
1. `backend/.env`에 `EVAL_API_KEY` 이미 추가됨 (Phase 0)
2. `EVAL_ALERT_EMAILS` 환경변수 추가(선택, 없으면 ADMIN_ALERT_EMAIL 사용)
3. `deploy.bat`이 backend/.env를 양쪽 슬롯으로 동기화하는지 확인 — 안 하면 운영 슬롯 .env에도 EVAL_API_KEY 수동 복사 필요
4. 관리자 권한 cmd에서 `register_cron.bat` 실행 → schtasks 등록
5. 수동 트리거: `schtasks /run /tn "LFChatbot-EvalDaily"` → 로그 확인 → 메일 수신 확인 (변화 있을 시만)

### 다음 단계 (Phase 1)
- pii-search 삭제, `/admin` 통합 콘솔로 격상
- `/admin/eval` 탭: 트렌드 차트(워커별 30일 pass rate), 실행 히스토리 카드, 실패 케이스 모달 + triage 액션
- 알림함 영속화: `eval_results` WHERE status=fail을 `MOCK_PERSONAL`을 대체하는 새 backend API로 노출
- Phase 0.5에서 만든 데이터(13 케이스 × 매일 1회 cron 누적)가 트렌드 차트 데이터로 사용됨

# 2026-03-05 일일 개발 요약 스케줄러 (Nightly Summary)

## 개요
매일 밤 23:00 KST에 당일 CHANGELOG.md + docs/history/ 변경 기록을 LLM(Haiku)으로 요약하여 보고서를 생성하고, HTML 메일로 발송하며, 자동으로 git commit+push하는 APScheduler 기반 스케줄러.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/utils/nightly_summary_scheduler.py` | 신규 | 스케줄러 메인 클래스 |
| `backend/app/main.py` | 수정 | lifespan에 4번째 스케줄러 등록 |
| `backend/app/api/routes/report.py` | 수정 | `POST /nightly-summary/run-now` 수동 실행 API |
| `docs/summary/` | 신규 | 일일 보고서 저장 디렉토리 |

## 상세 내용

### 실행 흐름
```
23:00 KST (CronTrigger, timezone=Asia/Seoul)
  ↓
1. CHANGELOG.md에서 ## [YYYY-MM-DD] 섹션 파싱
  ↓ (항목 없으면 스킵 — 메일도 안 보냄)
2. 링크된 docs/history/*.md 파일 + 당일 날짜 파일 읽기
  ↓
3. Bedrock Haiku로 종합 요약 보고서 생성 (max_tokens=2000)
  ↓
4. docs/summary/YYYY-MM-DD.md 파일 저장
  ↓
5. git add → commit → push (실패해도 계속)
  ↓
6. Markdown → HTML 변환 → EmailService로 발송
```

### NightlySummaryScheduler 클래스
- `start()`: CronTrigger(hour, timezone=Asia/Seoul) 등록
- `stop()`: 스케줄러 종료
- `run_now(target_date)`: 수동 즉시 실행 (테스트/디버깅용, 특정 날짜 지정 가능)
- `_execute(target)`: 메인 로직 (파싱 → LLM → 저장 → git → 메일)
- `_parse_changelog()`: 정규식으로 CHANGELOG 섹션 파싱
- `_read_history_files()`: 링크된 history + 당일 날짜 파일 자동 수집
- `_generate_summary()`: Bedrock Haiku 직접 호출
- `_markdown_to_html()`: 간이 마크다운→HTML 변환 (헤딩, 볼드, 코드, 리스트, 수평선)

### HTML 메일 템플릿
- 제목: `[Lucid AI] 일일 개발 보고서 — YYYY-MM-DD`
- 헤더: 그라데이션 배경 (#182F54 → #4472C4)
- 본문: 구조화된 HTML (마크다운 변환)
- 푸터: 자동 생성 안내 + 생성 시각

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NIGHTLY_SUMMARY_ENABLED` | `true` | 기능 on/off |
| `NIGHTLY_SUMMARY_HOUR` | `23` | 실행 시각 (0-23) |
| `NIGHTLY_SUMMARY_RECIPIENT` | `wg0403@landf.co.kr` | 수신자 이메일 |

### 기존 인프라 활용
- **APScheduler**: 기존 3개 스케줄러와 동일 패턴 (ReportEmailScheduler 참고)
- **EmailService**: `email_service.py`의 SMTP 발송 싱글턴
- **BedrockService**: `bedrock_service.py`의 `generate_text_haiku()` 직접 호출
- 새 의존성 없음

## 결정 사항 및 주의점
- git 실패 시 로그만 남기고 메일 발송은 계속 진행 (안전 장치)
- CHANGELOG에 당일 항목이 없으면 완전 스킵 (보고서 미생성, 메일 미발송)
- `zoneinfo.ZoneInfo("Asia/Seoul")` 사용 (Python 3.9+ 내장, pytz 불필요)
- 마크다운→HTML 변환은 간이 정규식 기반 (외부 라이브러리 미사용)
- `run_now(target_date)`: 과거 날짜를 지정하여 특정 날짜 보고서 재생성 가능

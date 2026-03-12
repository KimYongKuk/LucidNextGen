# 2026-03-10 토큰 사용량 모니터링 시스템

## 개요
CloudWatch가 cross-region inference 환경에서 토큰 메트릭을 부정확하게 기록하는 문제가 발생하여, 모든 LLM 호출의 토큰을 자체적으로 로깅하고 대시보드에서 모델별/워커별/사용자별 토큰 사용량을 모니터링할 수 있도록 구현.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/migrations/add_token_usage_log.sql` | 추가 | token_usage_log 테이블 생성 |
| `backend/app/services/token_usage_service.py` | 추가 | 토큰 로깅 싱글톤 서비스 (버퍼 + batch INSERT) |
| `backend/app/services/bedrock_service.py` | 수정 | generate_text/generate_text_haiku에 caller 파라미터 + usage 추출 |
| `backend/app/services/memory_service.py` | 수정 | 4개 Haiku 호출에 caller 전달 |
| `backend/app/agents/intent_classifier.py` | 수정 | LLM 분류 후 usage_metadata 로깅 |
| `backend/app/agents/workers/base_worker.py` | 수정 | Worker 스트리밍 완료 후 토큰 로깅 |
| `backend/app/services/chat_log_service.py` | 수정 | title 생성 시 caller 전달 |
| `backend/app/services/report_service.py` | 수정 | get_token_usage() 추가, get_user_ranking() 토큰 JOIN |
| `backend/app/api/routes/report.py` | 수정 | /token-usage 엔드포인트 추가 |
| `frontend/lib/api/report.ts` | 수정 | TokenUsageData 타입 + API 추가 |
| `frontend/components/dashboard/token-usage.tsx` | 추가 | 토큰 모니터링 대시보드 섹션 |
| `frontend/components/dashboard/user-ranking.tsx` | 수정 | 토큰 컬럼 추가 |
| `frontend/app/admin/report/page.tsx` | 수정 | TokenUsage 섹션 렌더 |

## 상세 내용

### 아키텍처
```
[LLM 호출 지점]
  ├── intent_classifier (Haiku) ──┐
  ├── base_worker (Sonnet/Haiku) ─┤
  ├── memory_service (Haiku x4) ──┼──→ TokenUsageService.log()
  ├── title_generation (Sonnet) ──┤        │
  └── bedrock_service (직접) ─────┘    asyncio.create_task
                                           │
                                    [내부 버퍼 + 5초/20건 flush]
                                           │
                                    token_usage_log (MySQL)
                                           │
                                    ReportService.get_token_usage()
                                           │
                                    /api/v1/admin/report/token-usage
                                           │
                                    <TokenUsage /> 대시보드 컴포넌트
```

### token_usage_log 테이블
- `caller`: 호출자 식별 (intent_classifier, DirectWorker, memory_ws_summary 등)
- `model_id`: 전체 Bedrock 모델 ID
- `model_type`: "sonnet" | "haiku" (자동 판별)
- `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`
- 인덱스: created_at, model_type, caller, user_id

### TokenUsageService
- 싱글톤, fire-and-forget 방식 (응답 지연 없음)
- 내부 버퍼 + 주기적 batch INSERT (5초 또는 20건)
- 에러 시 로그만 남기고 무시

### 대시보드 UI
- KPI 카드 3개: 총 토큰, Input, Output
- 모델별 도넛 차트 (Sonnet vs Haiku)
- 일별 추이 라인차트
- 워커별 토큰 사용량 테이블
- 사용자 랭킹에 토큰 컬럼 추가

## 결정 사항 및 주의점
- CloudWatch 대신 자체 로깅을 선택한 이유: cross-region inference에서 CloudWatch 메트릭이 분산 기록되어 부정확
- Sonnet 4.6 TPD 한도: 10,800,000 토큰 (조정 불가, AWS Support 케이스 필요)
- bedrock_service의 streaming API(`stream_chat`, `stream_text_haiku`)는 응답에 usage가 없어 로깅 불가 → Worker는 LangChain의 `on_chat_model_end` 이벤트에서 수집
- `caller` 파라미터가 없으면(기본값 "") 로깅하지 않아 기존 동작에 영향 없음

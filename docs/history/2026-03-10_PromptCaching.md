# 2026-03-10 Bedrock Prompt Caching

## 개요
AWS Bedrock Prompt Caching을 도입하여 Agent loop 내 반복되는 system prompt 전송 비용을 절감.
`CachedChatBedrockConverse` 서브클래스로 system 블록에 `cachePoint` 마커를 자동 주입.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/base_worker.py | 추가/수정 | `CachedChatBedrockConverse` 서브클래스, cache 메트릭 트래킹 |
| backend/app/agents/workers/direct_worker.py | 수정 | `ChatBedrockConverse` → `CachedChatBedrockConverse` 교체 |
| backend/app/agents/a2a_streaming.py | 수정 | `cache_read_tokens`/`cache_write_tokens` 수집 및 전달 |
| backend/app/api/routes/chat.py | 수정 | cache 메트릭 DB metadata에 저장 |

## 상세 내용

### 문제
- LangGraph `create_react_agent`는 매 agent step마다 동일한 system prompt를 재전송
- 조직도 조회 1건에 20K 토큰 소비 (system prompt 4,000 × 3~5회 = 12,000~20,000 토큰)
- 일일 10.8M 토큰 한도 중 system prompt 반복이 80% 차지

### 해결 방법
`ChatBedrockConverse`를 서브클래싱하여 `_generate()`와 `_stream()` 오버라이드:
- `_messages_to_bedrock()` 호출 후 system 블록 끝에 `{"cachePoint": {"type": "default"}}` 추가
- 나머지 로직은 원본과 동일

### 비용 모델
| 항목 | Sonnet 단가 | Haiku 단가 |
|------|------------|-----------|
| 일반 input | $3.00/1M | $0.25/1M |
| Cache write | $3.75/1M (+25%) | $0.30/1M |
| Cache read | $0.30/1M (-90%) | $0.03/1M |

### 예상 효과 (도구 호출 3회 기준)
- Before: system 4,000 × 3 = 12,000 input tokens
- After: 4,000 (write) + 400 × 2 (read) = 4,800 input tokens → **60% 절감**

### 캐시 메트릭 데이터 흐름
```
CachedChatBedrockConverse._stream()
  → Bedrock API response: cacheReadInputTokens, cacheWriteInputTokens
  → langchain-aws _extract_usage_metadata(): input_token_details.cache_read/cache_creation
  → base_worker on_chat_model_end: total_cache_read_tokens/total_cache_write_tokens
  → token_usage event yield
  → a2a_streaming.py 집계
  → _internal_collected JSON
  → chat.py metadata["cache_read_tokens"]/["cache_write_tokens"]
  → chat_log_new.metadata (MySQL JSON)
```

### 로그 확인 방법
```
[OrgChartWorker] [TOKEN #1] in=4,500 out=200 cache_write=4,000 (cumul: in=4,500 out=200)
[OrgChartWorker] [TOKEN #2] in=900 out=150 cache_read=4,000 (cumul: in=5,400 out=350)
[OrgChartWorker] [TOKEN_TOTAL] input=5,400 output=350 cache_read=4,000 cache_write=4,000 llm_calls=2
```

## 결정 사항 및 주의점
- `langchain-aws` 내부 함수(`_messages_to_bedrock` 등)에 의존 → 버전 업그레이드 시 호환성 확인 필요 (현재 0.2.20)
- Haiku 전처리 LLM (visualization/ppt/xlsx worker의 대화 요약)은 단발 호출이므로 캐싱 미적용 (기존 `ChatBedrockConverse` 유지)
- intent_classifier.py도 단발 분류이므로 캐싱 미적용
- system prompt 1,024 토큰 미만이면 cachePoint가 무시됨 (에러 아님)
- 캐시 TTL: AWS 관리 (기본 5분), 같은 요청 내 agent loop는 수초 간격으로 확실히 hit

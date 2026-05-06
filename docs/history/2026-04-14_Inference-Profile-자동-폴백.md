# 2026-04-14 Inference Profile 자동 폴백

## 개요
Worker LLM 호출 시 일일 토큰 한도(`tokens per day`) 초과로 ThrottlingException 발생 시, `us.*` ↔ `global.*` inference profile prefix를 자동 전환하여 별도 한도를 사용하도록 폴백 로직을 추가했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/core/region_fallback.py | 수정 | us↔global prefix 전환 방식으로 전면 개편 |
| backend/app/agents/workers/base_worker.py | 수정 | Worker stream에 throttling 감지 → prefix 전환 재시도 |
| backend/app/agents/intent_classifier.py | 수정 | intent 분류 Haiku 호출에 prefix 전환 재시도 |
| backend/app/services/bedrock_service.py | 수정 | 모든 메서드에 prefix 전환 폴백 추가 |

## 상세 내용

### 문제
- `base_worker.py`의 `CachedChatBedrockConverse`가 LangGraph `create_react_agent`를 통해 Bedrock `converse_stream`을 호출
- 기존 `bedrock_service.py`의 모델 체인 폴백은 직접 호출용이며, Worker 경로에는 적용되지 않았음
- ThrottlingException 발생 시 catch 없이 그대로 전파 → `orchestrator_producer`에서 미처리 예외로 종료
- `claude-sonnet-4-6`은 on-demand 직접 호출 불가 (inference profile 필수) → 기존 리전 전환(us-west-2) 방식 사용 불가

### 해결: Inference Profile Prefix 전환
- `us.anthropic.*` (US cross-region)과 `global.anthropic.*` (Global inference)는 **별도 일일 한도**
- throttling 시 prefix를 반대쪽으로 전환하여 재시도
- `swap_inference_prefix()` 함수: 양방향 전환 (`us.` ↔ `global.`)
- 같은 리전(us-east-1)의 같은 boto3 client로 호출 가능 (리전 변경 불필요)

### 폴백 흐름
```
Worker stream_response()
  └─ agent.astream_events() 호출
      └─ ThrottlingException 발생
          └─ is_throttling_error() 감지
              └─ swap_inference_prefix(us.* → global.*)
                  └─ activate_fallback() (이후 요청도 자동 전환)
                      └─ agent 재생성 + 재시도
                          └─ 성공 → 정상 응답
                          └─ 실패 → 예외 전파
```

### 자동 복구
- 폴백 활성화 후 다음 날 KST 09:00 (UTC 00:00) 자동 복구
- AWS 일일 토큰 한도 리셋 시점과 일치
- 수동 복구: `get_region_fallback_manager().reset_to_primary()`

### 적용 범위
| 호출 경로 | 폴백 방식 |
|-----------|-----------|
| Worker (base_worker.py) | try/except → prefix 전환 → agent 재생성 재시도 |
| IntentClassifier (Haiku) | try/except → prefix 전환 → LLM 재생성 재시도 |
| bedrock_service.stream_chat | 모델 체인 소진 후 prefix 전환 재시도 |
| bedrock_service.generate_text | 모델 체인 소진 후 prefix 전환 재시도 |
| bedrock_service.converse_with_tools | 모델 체인 소진 후 prefix 전환 재시도 |
| bedrock_service.generate_text_haiku | 즉시 prefix 전환 재시도 |
| bedrock_service.stream_text_haiku | 즉시 prefix 전환 재시도 |

## 결정 사항 및 주의점
- on-demand(`anthropic.*`) 직접 호출은 sonnet-4-6에서 `ValidationException` 발생 — inference profile 필수
- EU(`eu.*`), APAC(`apac.*`) 프로필은 AWS 계정에서 활성화되지 않아 사용 불가
- `us.*`와 `global.*`만 사용 가능 (계정에 등록된 프로필 37개 중 Claude 관련 8개)
- `bedrock_service.py`의 `client` 프로퍼티를 항상 primary client 반환으로 변경 (prefix 전환이므로 리전 변경 불필요)

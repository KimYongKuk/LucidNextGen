# 2026-03-30 OpenAI-호환 Chat Completions API

## 개요
사내 다른 서비스들이 OpenAI SDK(`openai` 라이브러리)를 그대로 사용하여 Bedrock 기반 Claude 모델을 호출할 수 있도록 OpenAI-compatible API 엔드포인트를 추가했다. 별도 IAM 자격증명을 사용하여 기존 루시드AI 챗봇의 AWS 쿼터와 분리 운영한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/api/routes/openapi_compat.py` | 신규 | `/v1/chat/completions`, `/v1/models` 엔드포인트 |
| `backend/app/services/openapi_bedrock_service.py` | 신규 | 별도 IAM의 Bedrock 클라이언트 (스트리밍/논스트리밍) |
| `backend/app/api/dependencies/api_key_auth.py` | 신규 | Bearer 토큰 기반 API Key 인증 미들웨어 |
| `backend/app/services/token_usage_service.py` | 수정 | `api_key_name` 파라미터 추가 (서비스별 사용량 추적) |
| `backend/app/main.py` | 수정 | 라우터 등록 (prefix 없이 `/v1/...`) |
| `backend/.env` | 수정 | `OPENAPI_AWS_*`, `OPENAPI_KEYS`, 모델 매핑 환경변수 |
| `backend/migrations/add_api_key_name_to_token_usage_log.sql` | 신규 | `api_key_name` 컬럼 + 인덱스 |

## 상세 내용

### 아키텍처
```
[사내 서비스] → POST /v1/chat/completions (Bearer sk-xxx)
                     ↓
              API Key 인증 (OPENAPI_KEYS)
                     ↓
              OpenAPIBedrockService (별도 IAM)
                     ↓
              AWS Bedrock (us-east-1)
                     ↓
              OpenAI 형식 응답 + 토큰 로깅
```

### 엔드포인트
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/v1/chat/completions` | POST | Chat Completions (스트리밍/논스트리밍) |
| `/v1/models` | GET | 사용 가능 모델 목록 |

### 모델 매핑
| OpenAI 모델명 | Bedrock 모델 ID |
|---------------|-----------------|
| `claude-sonnet` | `us.anthropic.claude-sonnet-4-6` |
| `claude-haiku` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

### 클라이언트 사용 예시
```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-lucid-common-2026",
    base_url="http://서버IP:8000/v1"
)

# Non-streaming
response = client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "안녕하세요"}]
)

# Streaming
for chunk in client.chat.completions.create(
    model="claude-haiku",
    messages=[{"role": "user", "content": "안녕하세요"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="")
```

### API Key 관리
- `.env`의 `OPENAPI_KEYS` 환경변수에 `서비스명:키` 형식으로 등록
- 현재: `svc-common:sk-lucid-common-2026` (공용 키 1개)
- 서비스 추가 시 쉼표로 구분하여 추가

### 토큰 사용량 추적
- `token_usage_log` 테이블의 `api_key_name` 컬럼으로 서비스별 추적
- `caller` 필드: `openapi:서비스명` 형식 (예: `openapi:svc-common`)
- 현재는 추적만, 향후 일일 할당량 제한 추가 가능

## 결정 사항 및 주의점
- **쿼터 분리**: 현재 같은 AWS 계정 내 별도 IAM이므로 쿼터는 공유됨. 완전 분리를 위해서는 별도 AWS 계정(Organizations) 필요
- **기존 서비스 영향 없음**: 별도 BedrockService 인스턴스, 별도 boto3 클라이언트 사용
- **리전 폴백 미적용**: OpenAPI 서비스는 단순 리트라이(2회)만 적용. 기존 챗봇의 리전폴백과 독립
- **환경변수 `OPENAPI_KEYS` 변경 시 서버 재시작 필요** (모듈 로드 시 1회 파싱)

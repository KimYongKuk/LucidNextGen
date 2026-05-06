# Lucid AI API Guide

> **OpenAI-compatible Chat Completions API**
> 사내 서비스에서 OpenAI SDK를 그대로 사용하여 Claude 모델을 호출할 수 있습니다.

---

## 1. 기본 정보

| 항목 | 값 |
|------|-----|
| Base URL | `http://192.168.90.30:8000/v1` |
| 인증 | `Authorization: Bearer {API_KEY}` |
| 프로토콜 | HTTP (사내망 전용) |
| 응답 형식 | JSON (OpenAI 호환) |

---

## 2. 사용 가능한 모델

| 모델명 | 설명 | 용도 |
|--------|------|------|
| `claude-sonnet` | Claude Sonnet 4.6 | 복잡한 추론, 코드 생성, 긴 문서 작성 |
| `claude-haiku` | Claude Haiku 4.5 | 빠른 응답, 분류, 요약, 간단한 질의응답 |

**선택 기준:**
- 품질이 중요하면 → `claude-sonnet`
- 속도/비용이 중요하면 → `claude-haiku`

---

## 3. 빠른 시작

### Python (OpenAI SDK)

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-lucid-common-2026",
    base_url="http://192.168.90.30:8000/v1"
)

response = client.chat.completions.create(
    model="claude-sonnet",
    messages=[
        {"role": "system", "content": "당신은 친절한 어시스턴트입니다."},
        {"role": "user", "content": "파이썬에서 리스트 중복 제거하는 방법 알려줘"}
    ]
)

print(response.choices[0].message.content)
```

### Python (스트리밍)

```python
stream = client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "FastAPI의 장점을 설명해줘"}],
    stream=True,
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
```

### cURL

```bash
curl http://192.168.90.30:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-lucid-common-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet",
    "messages": [
      {"role": "user", "content": "안녕하세요"}
    ]
  }'
```

### JavaScript / TypeScript

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-lucid-common-2026",
  baseURL: "http://192.168.90.30:8000/v1",
});

const response = await client.chat.completions.create({
  model: "claude-haiku",
  messages: [{ role: "user", content: "안녕하세요" }],
});

console.log(response.choices[0].message.content);
```

### C# / .NET

```csharp
using OpenAI;
using OpenAI.Chat;

var client = new ChatClient(
    model: "claude-sonnet",
    credential: new ApiKeyCredential("sk-lucid-common-2026"),
    options: new OpenAIClientOptions { Endpoint = new Uri("http://192.168.90.30:8000/v1") }
);

var response = await client.CompleteChatAsync("안녕하세요");
Console.WriteLine(response.Value.Content[0].Text);
```

---

## 4. API 레퍼런스

### POST /v1/chat/completions

Chat Completions 생성. 스트리밍 및 논스트리밍 모두 지원합니다.

#### Request

```json
{
  "model": "claude-sonnet",
  "messages": [
    {"role": "system", "content": "시스템 프롬프트 (선택)"},
    {"role": "user", "content": "사용자 메시지"},
    {"role": "assistant", "content": "이전 AI 응답 (멀티턴 시)"},
    {"role": "user", "content": "후속 질문"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 4096
}
```

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `model` | string | O | - | `claude-sonnet` 또는 `claude-haiku` |
| `messages` | array | O | - | 대화 메시지 배열 |
| `stream` | boolean | X | `false` | SSE 스트리밍 활성화 |
| `temperature` | float | X | `0.7` | 창의성 (0.0 ~ 1.0) |
| `max_tokens` | integer | X | `4096` | 최대 응답 토큰 수 (Sonnet: ~8192, Haiku: ~4096) |

#### Messages 역할

| role | 설명 |
|------|------|
| `system` | AI의 행동 지침. 여러 개 가능 (합쳐짐) |
| `user` | 사용자 입력 |
| `assistant` | AI의 이전 응답 (멀티턴 대화 시) |

#### Response (논스트리밍)

```json
{
  "id": "chatcmpl-abc123...",
  "object": "chat.completion",
  "created": 1711800000,
  "model": "claude-sonnet",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "응답 내용..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 150,
    "total_tokens": 175
  }
}
```

#### Response (스트리밍, SSE)

```
data: {"id":"chatcmpl-abc123...","object":"chat.completion.chunk","created":1711800000,"model":"claude-sonnet","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123...","object":"chat.completion.chunk","created":1711800000,"model":"claude-sonnet","choices":[{"index":0,"delta":{"content":"응답"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123...","object":"chat.completion.chunk","created":1711800000,"model":"claude-sonnet","choices":[{"index":0,"delta":{},"finish_reason":"stop"},"usage":{"prompt_tokens":25,"completion_tokens":150,"total_tokens":175}}]}

data: [DONE]
```

| finish_reason | 의미 |
|---------------|------|
| `stop` | 정상 완료 |
| `length` | max_tokens 도달 |

---

### GET /v1/models

사용 가능한 모델 목록을 반환합니다.

#### Response

```json
{
  "object": "list",
  "data": [
    {"id": "claude-sonnet", "object": "model", "created": 1700000000, "owned_by": "lucid-ai"},
    {"id": "claude-haiku", "object": "model", "created": 1700000000, "owned_by": "lucid-ai"}
  ]
}
```

---

## 5. 활용 예시

### 텍스트 요약

```python
def summarize(text: str) -> str:
    response = client.chat.completions.create(
        model="claude-haiku",  # 요약은 Haiku로 충분
        messages=[
            {"role": "system", "content": "주어진 텍스트를 3문장으로 요약하세요."},
            {"role": "user", "content": text}
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content
```

### 멀티턴 대화

```python
history = [
    {"role": "system", "content": "당신은 IT 헬프데스크 어시스턴트입니다."}
]

while True:
    user_input = input("질문: ")
    if user_input == "quit":
        break

    history.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="claude-sonnet",
        messages=history,
    )

    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    print(f"AI: {reply}\n")
```

### JSON 구조화 출력

```python
response = client.chat.completions.create(
    model="claude-sonnet",
    messages=[
        {"role": "system", "content": "반드시 JSON 형식으로만 응답하세요."},
        {"role": "user", "content": "다음 문장에서 인물, 장소, 날짜를 추출하세요: '김철수는 2026년 3월 30일 서울에서 회의를 진행했다.'"}
    ],
    temperature=0.0,
)

import json
result = json.loads(response.choices[0].message.content)
```

### LangChain 연동

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="claude-sonnet",
    api_key="sk-lucid-common-2026",
    base_url="http://192.168.90.30:8000/v1",
)

response = llm.invoke("LangChain이 뭐야?")
print(response.content)
```

---

## 6. 에러 처리

### 에러 응답 형식

```json
{
  "error": {
    "message": "에러 설명",
    "type": "에러 유형",
    "code": "에러 코드"
  }
}
```

### 에러 코드

| HTTP 코드 | type | 원인 | 대처 |
|-----------|------|------|------|
| 401 | `invalid_request_error` | API Key 누락 또는 잘못됨 | `Authorization: Bearer` 헤더 확인 |
| 400 | `invalid_request_error` | 잘못된 모델명 또는 파라미터 | `model`을 `claude-sonnet` 또는 `claude-haiku`로 |
| 429 | `rate_limit_error` | Bedrock 쓰로틀링 | 잠시 후 재시도 (자동 리트라이 2회 내장) |
| 500 | `server_error` | 서버 내부 오류 | 관리자 문의 |

### Python 에러 핸들링 예시

```python
from openai import APIError, AuthenticationError, RateLimitError

try:
    response = client.chat.completions.create(
        model="claude-sonnet",
        messages=[{"role": "user", "content": "안녕"}]
    )
except AuthenticationError:
    print("API Key가 잘못되었습니다.")
except RateLimitError:
    print("요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
except APIError as e:
    print(f"서버 오류: {e.message}")
```

---

## 7. 주의사항

- **사내망 전용**: `192.168.90.30`은 사내 네트워크에서만 접근 가능합니다.
- **토큰 사용량 추적 중**: 모든 API 호출의 토큰 사용량이 자동 기록됩니다.
- **모델 제한**: 현재 `claude-sonnet`과 `claude-haiku`만 지원합니다.
- **이미지 입력**: 현재 텍스트만 지원합니다 (Vision 추후 지원 예정).
- **API Key 관리**: Key 분실 시 관리자에게 재발급 요청하세요.

---

## 8. 문의

| 항목 | 연락처 |
|------|--------|
| API Key 발급/재발급 | Lucid AI 관리자 |
| 기술 문의 | Lucid AI 팀 |
| API 상태 확인 | `GET http://192.168.90.30:8000/health` |

# MISO API Reference

> 작성일: 2026-04-15
> Base URL: `http://api.miso.landf.co.kr`
> 인증: `Authorization: Bearer {MISO_API_KEY}`

---

## 1. Workflow API

워크플로우를 실행하고 결과를 받습니다. Blocking(JSON) 또는 Streaming(SSE) 모드를 선택할 수 있습니다.

### Endpoint

```
POST /ext/v1/workflows/run
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `inputs` | required | object | 앱에서 정의된 입력 변수 값 객체 |
| `mode` | required | string | `streaming` 또는 `blocking` |
| `user` | required | string | 최종 사용자 식별자 |
| `files` | optional | array\<object\> | 이미지/파일 입력 목록 |

### Response (blocking)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 워크플로우 실행 ID |
| `workflow_id` | string | 워크플로우 ID |
| `status` | string | 실행 상태 (`running` / `succeeded` / `failed` / `stopped`) |
| `inputs` | object | 입력 변수 값 |
| `outputs` | object | 출력 변수 값 |
| `error` | string \| null | 에러 메시지 (실패 시) |
| `total_steps` | number | 실행된 총 노드 수 |
| `total_tokens` | number | 사용된 총 토큰 수 |
| `created_at` | string | 실행 시작 시각 (ISO8601) |
| `finished_at` | string | 실행 완료 시각 (ISO8601) |
| `elapsed_time` | number | 실행 소요 시간 (초) |

### SSE Events (streaming)

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `workflow_started`, `node_started`, `node_finished`, `text_chunk`, `workflow_finished` 등 |
| `workflow_run_id` | string | 워크플로우 실행 ID |
| `data` | object | 이벤트별 payload |

### 요청 예시

```bash
curl -X POST 'http://api.miso.landf.co.kr/ext/v1/workflows/run' \
  -H 'Authorization: Bearer {MISO_API_KEY}' \
  -H 'Content-Type: application/json' \
  -d '{
  "inputs": {},
  "mode": "blocking",
  "user": "abc-123"
}'
```

### 응답 예시

```json
{
  "id": "workflow_run_id",
  "workflow_id": "workflow_id",
  "status": "succeeded",
  "inputs": {},
  "outputs": {
    "결과": "워크플로우 실행 결과가 여기에 표시됩니다"
  },
  "error": null,
  "total_steps": 0,
  "total_tokens": 0,
  "created_at": "2026-04-15T09:34:09.192Z",
  "finished_at": "2026-04-15T09:34:09.192Z",
  "elapsed_time": 1.23
}
```

---

## 2. Chat API

메시지를 전송하고 응답을 받습니다. Blocking(JSON) 또는 Streaming(SSE) 모드를 선택할 수 있습니다.

### Endpoint

```
POST /ext/v1/chat
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `query` | required | string | 사용자의 질문/프롬프트 |
| `inputs` | optional | object | 앱에서 정의된 입력 변수 값 객체 (기본값: `{}`) |
| `mode` | required | string | `streaming` 또는 `blocking` |
| `conversation_id` | optional | string | 이전 대화 이어받기용 conversation ID |
| `user` | required | string | 최종 사용자 식별자 |
| `files` | optional | array\<object\> | 이미지/파일 입력 목록 |
| `auto_gen_name` | optional | bool | 대화 제목 자동 생성 여부 (기본값: `true`) |

### Response (blocking)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 메시지 ID |
| `conversation_id` | string | 대화 ID |
| `answer` | string | 모델의 최종 응답 텍스트 |
| `agent_thoughts` | array | 에이전트 내부 추론 로그 (옵션) |
| `created_at` | string | 응답 생성 시각 (ISO8601) |

### SSE Events (streaming)

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `message`, `agent_message`, `agent_thought`, `message_replace`, `message_end` 등 |
| `workflow_run_id` | string | 워크플로우 실행 ID |
| `data` | object | 이벤트별 payload |

### 요청 예시

```bash
curl -X POST 'http://api.miso.landf.co.kr/ext/v1/chat' \
  -H 'Authorization: Bearer {MISO_API_KEY}' \
  -H 'Content-Type: application/json' \
  -d '{
  "inputs": {},
  "query": "질문 또는 사용자 입력",
  "mode": "blocking",
  "conversation_id": "",
  "user": "abc-123"
}'
```

### 응답 예시

```json
{
  "id": "message_id",
  "conversation_id": "conversation_id",
  "answer": "모델의 응답 텍스트",
  "agent_thoughts": [],
  "created_at": "2026-04-15T09:43:48.515Z"
}
```

---

## 3. Files (공통)

Workflow, Chat 모두 `files` 파라미터로 파일 입력을 지원합니다.

### 지원 파일 타입

| 타입 | 확장자 |
|------|--------|
| Document | TXT, MD, MARKDOWN, PDF, HTML, XLSX, XLS, DOCX, CSV, EML, MSG, PPTX, PPT, XML, EPUB |
| Image | JPG, JPEG, PNG, GIF, WEBP, SVG |
| Audio | MP3, M4A, WAV, WEBM, AMR |
| Video | MP4, MOV, MPEG, MPGA |
| Custom | 기타 확장자 |

### 파일 전달 방식

| 방식 | 필드 | 설명 |
|------|------|------|
| `remote_url` | `url` | URL을 통한 파일 전달 |
| `local_file` | `upload_file_id` | 파일 업로드 API를 통해 사전 업로드한 파일의 ID |

---

## 4. Errors (공통)

| 코드 | 에러 | 설명 |
|------|------|------|
| 400 | `invalid_param` | 잘못된 파라미터 입력 |
| 400 | `app_unavailable` | 앱 설정 정보를 사용할 수 없음 |
| 400 | `provider_not_initialize` | 모델 인증 정보 미설정 |
| 400 | `model_currently_not_support` | 현재 모델 사용 불가 |
| 400 | `workflow_request_error` | 워크플로우 실행 실패 (Workflow 전용) |
| 400 | `completion_request_error` | 텍스트 생성 요청 실패 (Chat 전용) |
| 404 | `conversation_not_found` | conversation을 찾을 수 없음 (Chat 전용) |
| 500 | `internal_server_error` | 내부 서버 오류 |

---

## 5. 허브 연동 메모

### 두 API 유형의 차이

| 구분 | Workflow API | Chat API |
|------|-------------|----------|
| 용도 | 정해진 파이프라인 실행 | 대화형 질의응답 |
| 입력 | `inputs` (구조화된 파라미터) | `query` (자연어) + `inputs` |
| 출력 | `outputs` (구조화된 결과) | `answer` (텍스트) |
| 대화 유지 | 없음 (단발성 실행) | `conversation_id`로 이어받기 가능 |
| 상태 추적 | `status` 필드 (running/succeeded/failed/stopped) | 없음 (즉시 응답) |

### Lucid 허브 서비스 유형 매핑

```
MISO Workflow → 서비스 유형: Trigger형 (실행 → 결과)
MISO Chat     → 서비스 유형: Agent형 (대화형 응답)
```

# 2026-05-06 MisoWorker Workflow 응답 추출 + 입력 매핑 multi-row + 파일 업로드

## 개요
1. **응답 추출 수정**: 워크스페이스에 부착된 MISO Workflow Agent를 호출하면 MISO 측 로그상 `outputs.answer`가 정상적으로 채워져 있음에도 사용자 채팅에는 `(워크플로우 출력이 비어있습니다)`만 표시되던 문제 수정. 원인은 MISO Workflow blocking 응답이 `outputs`를 최상위가 아닌 `data.data.outputs`에 중첩해서 내려주는 것.
2. **등록 폼 Multi-row 입력 매핑**: 변수명만 받던 단일 입력을 `[{name, type, source}, ...]` 다중 행 매핑으로 확장. 텍스트/문단/목록/숫자/단일 파일 5종 타입 지원.
3. **파일 변수 자동 매핑 (단일 + 다중)**: 파일 타입 변수는 사용자가 채팅창에 첨부한 업로드 파일을 자동으로 MISO에 업로드하고 reference로 매핑. ITSupportWorker의 `_list_uploaded_files`/`register_works_voc` 패턴 차용 — `data/user_uploads/{date}/{user_id}/`에서 원본 읽어 `POST /ext/v1/files/upload`로 업로드 후 `upload_file_id` 받아 inputs에 매핑. ChatRequest 스키마 변경 없이 워커가 user_id로 디스크 직접 조회. **단일 파일**(`file` 타입)은 mtime 최신 1개, **다중 파일**(`files` 타입, MISO Array[File])은 시간 윈도우(`{{recent_files}}`, 기본 10분) 또는 N개 한정(`{{recent_files:3/5/10}}`) 모드 지원. 한 호출 최대 10개 안전 상한.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/miso_worker.py | 수정 | `_extract_answer` nested 구조 fallback / `_build_request_body` async + list 매핑 / `_resolve_mapped_value` 6종 타입 처리(text/paragraph/list/number/file/files) / `_find_latest_user_file`·`_find_recent_user_files`·`_resolve_user_file_by_name`·`_upload_file_to_miso` 신규 / `FileMappingError` 신설 / 환경변수 `MISO_FILE_UPLOAD_TIMEOUT`·`MISO_RECENT_FILES_WINDOW_SEC`·`MISO_RECENT_FILES_MAX` |
| frontend/app/agent-store/new/miso/page.tsx | 수정 | 단일 변수명 입력 → multi-row 매핑 테이블(변수명·타입·소스). 6종 타입 셀렉트(텍스트/문단/목록/숫자/단일 파일/다중 파일). 다중 파일 시간 윈도우 옵션 4종(전체/최근 3·5·10개). 안내 박스에 단일/다중 차이 명시 |

## 상세 내용

### 1. `_extract_answer` — nested 응답 구조 대응
- `data.outputs`가 비어 있으면 `data.data.outputs`도 시도하도록 보강.
- chat 모드도 동일하게 nested `data.data.answer` fallback 추가 (응답 구조 변화 대응).

```python
outputs = data.get("outputs")
if not outputs:
    inner = data.get("data")
    if isinstance(inner, dict):
        outputs = inner.get("outputs")
outputs = outputs or {}
```

### 2. 진단 로그 보강
- workflow 모드일 때 `data.data` 키와 `outputs` 미리보기를 별도로 print → 응답 구조 변동 시 빠른 진단.

### 3. 등록 폼 Multi-row Input 매핑
- `verifyState.kind === "valid" && verifyState.mode === "workflow"`일 때만 노란색 배경 박스로 매핑 테이블 노출.
- 행 단위 컬럼: **변수명 / 타입 / 소스 / 삭제**. "변수 추가" 버튼으로 행 추가 — 다중 입력 워크플로우 대응.
- 타입 선택지: 텍스트 / 문단 / 목록 / 숫자 / 단일 파일.
- 타입에 따라 source 드롭다운 옵션이 동적 변경:
  - 텍스트·문단: `{{message}}` (사용자 발화 그대로)
  - 목록: `{{message_lines}}` (줄바꿈으로 분리) / `{{message}}` (1개 항목)
  - 숫자: `{{message_number}}` (발화에서 첫 숫자 추출)
  - 단일 파일: `{{latest_file}}` (가장 최근 업로드 파일)
- 변수명 중복 검증 (제출 전).
- 행이 0개면 백엔드 best-effort 그대로 동작 (하위호환).

### 4. 파일 변수 호출 흐름 (핵심)
- **공통**: 매칭된 파일을 `POST {MISO_BASE_URL}/ext/v1/files/upload`에 multipart로 업로드 → `upload_file_id` 추출(응답 wrapping 변동 대비 `id`/`upload_file_id`/`data.id`/`data.upload_file_id` 4개 위치 시도). MisoWorker는 `_USER_UPLOAD_DIR = backend/data/user_uploads/{date}/{user_id}/`에서 원본을 찾음.
- **단일 파일** (`file`):
  - `{{latest_file}}` — mtime 최신 1개 → file ref dict
  - `{{file:파일명.ext}}` — 명시 파일명 매칭 1개 → file ref dict
  - inputs 매핑: `{name: {transfer_method: "local_file", upload_file_id: "...", type: "document"}}`
- **다중 파일** (`files`, MISO `Array[File]`):
  - `{{recent_files}}` — `MISO_RECENT_FILES_WINDOW_SEC`(기본 600초) 내 모든 파일을 mtime 최신 순으로 묶어 업로드 → file ref **배열**
  - `{{recent_files:N}}` — 시간 윈도우 무시, mtime 최신 순 N개 (1≤N≤`MISO_RECENT_FILES_MAX`=10)
  - inputs 매핑: `{name: [{transfer_method, upload_file_id, type}, ...]}`
- 파일이 없으면 `FileMappingError` → 사용자에게 "채팅창에 파일을 먼저 첨부해주세요" 친절한 안내.

## 결정 사항 및 주의점

- **MISO API 응답 구조의 두 가지 형태**:
  - 최상위형: `{"workflow_run_id": ..., "outputs": {"answer": "..."}}`
  - 중첩형: `{"workflow_run_id": ..., "data": {"outputs": {"answer": "..."}}}`
  - MISO 워크플로우 blocking 응답은 후자가 표준이며, MISO Studio의 `로그` 화면에서 보이는 outputs는 `data.outputs` 아래 값임. SDK/문서 시점에 따라 응답 wrapping이 달라 보일 수 있어 양쪽 모두 시도하는 것이 안전.
- **prefix(`@slug`) 제거는 그대로 유지** — MISO에 query를 보낼 때 `@chick-workflow1`이 붙은 채로 전달되어도 워크플로우가 무시하고 정상 응답하지만, 우리는 여전히 정제된 발화를 보내는 게 깔끔.
- **다중 변수 지원 완료**: 변수 1개 가정을 풀고 multi-row 매핑으로 확장. `topic` + `tone` 같이 입력 변수가 여러 개인 워크플로우도 한 번에 등록 가능.
- **input_mapping 양 형태 모두 호환**: legacy dict(`{변수명: "{{message}}"}`)와 신형 list(`[{name, type, source}, ...]`) 모두 `_build_request_body`가 처리 → 기존 등록된 Agent도 수정 없이 동작.
- **파일 흐름 ChatRequest 변경 X**: ITSupportWorker처럼 워커가 `user_id`로 디스크 직접 조회하는 방식 채택. 프론트가 file_id를 메시지로 백엔드에 보내야 하는 추가 채팅 스키마 변경 없이 동작 — `/v1/upload/file`이 이미 원본을 보존하기 때문.
- **자동 매핑 정책**: 가장 최근 업로드 파일(latest mtime)을 무조건 사용. 같은 세션에서 여러 파일을 올린 뒤 워크플로우를 호출하면 마지막 파일이 들어감. 명시적 선택이 필요하면 `{{file:파일명}}` 토큰을 후속에 노출 예정 (현재 폼에는 노출 안됨).
- **재제출 흐름에선 미노출**: 작성자 재제출(ResubmitStatusPanel)은 이름/설명/시스템 프롬프트만 편집 가능. 입력 매핑 수정이 필요하면 현재는 삭제 후 재등록.
- **MISO 파일 업로드 응답 구조 변동**: `id`/`upload_file_id`/`data.id`/`data.upload_file_id` 4개 위치를 순차 시도. SDK/문서 시점에 따라 wrapping이 다를 수 있어 양보 처리.
- **타임아웃 분리**: 파일 업로드는 워크플로우 호출보다 오래 걸릴 수 있어 `MISO_FILE_UPLOAD_TIMEOUT`(기본 120초) 별도 환경변수 도입.

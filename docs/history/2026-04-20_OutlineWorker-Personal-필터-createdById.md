# 2026-04-20 OutlineWorker Personal 필터 `createdById` 버그 수정

## 개요
본인 Personal 컬렉션 문서(예: 김용국 > 사내시스템 접속정보)가 챗봇에서 **전부** "접근 권한 없음" 에러로 치환되던 버그. 원인은 MCP 서버가 `createdBy`를 **사용자 이름 문자열**로 반환하는데, 필터 코드는 `createdBy`를 dict로 가정하고 `.get("id")`를 호출해 **AttributeError가 나거나 항상 빈 문자열 반환** → 본인 문서도 "남의 것"으로 판정 → 에러 치환.

오늘 오전에 커밋한 `2026-04-20_OutlineWorker-Personal-리포맷.md` 프롬프트 수정은 **오진에 따른 부적절한 처치**였음 (제거는 하지 않음 — 해롭지 않고 안전망 효과 있음).

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/outline_server/server.py | 수정 | `get_document`, `_format_document_summary` 반환 객체에 `createdById` (UUID) 필드 추가 |
| backend/app/agents/workers/outline_worker.py | 수정 | `_filter_result_by_personal_collection`에서 `createdBy.id` 대신 `createdById`로 비교 |

## 상세 내용

### 증상
- Personal > 김용국 하위 문서에 대해 챗봇이 `get_document` 2회 호출 후 "문서 조회 중 오류가 발생하고 있어요" 응답
- 같은 증상이 동일 컬렉션의 모든 문서에서 재현됨 (사용자 확인)
- [TOOL_OUTPUT] 로그에는 원본 본문이 찍혀 있어 "안전 거절(safety refusal)"로 오판했음

### 진단 과정
1. 토큰 델타 분석: `get_document` tool result가 LLM에 **단 44토큰**만 추가됨 (2회 연속 동일). 실제 본문이면 200~500토큰은 되어야 하는데 이는 `{"error": "해당 문서에 대한 접근 권한이 없습니다."}`(약 36자) 크기와 정확히 일치.
2. Outline DB 직접 조회:
   - `SELECT * FROM users WHERE "empCode" = 'A2304013'` → `id = 1ad48f7f-4b33-...` (매핑 OK)
   - `SELECT * FROM documents WHERE id = '5d253f24-...'` → `createdById = 1ad48f7f-4b33-...` (**매핑 OK, 동일 user**)
   - 즉 로직상 필터가 통과해야 정상
3. MCP 서버 코드 확인: `server.py:425` 에서 `"createdBy": doc.get("createdBy", {}).get("name", "")` — **이름 문자열** 반환
4. 필터 코드: `(data.get("createdBy") or {}).get("id", "")` — dict 가정 → string `"wg0403"`에 `.get("id")` 호출 시 AttributeError
5. LangGraph ToolNode가 AttributeError를 잡아 ToolMessage를 짧은 에러 메시지로 치환 → LLM에 44토큰 전달
6. [TOOL_OUTPUT] 로그가 헷갈린 이유: `on_tool_end` 이벤트는 `secured_ainvoke` wrapper 내부의 `_original()` 호출 완료 시점에 발화 — 즉 **필터 적용 이전 raw 결과**가 로깅됨. 필터가 결과를 치환한 후의 내용은 별도 로그 없음.

### 수정 내용

#### 1. MCP 서버 — `createdById` 추가
- `_format_document_summary()` (search/recent에서 공용) 및 `get_document()` 반환 객체에 UUID 필드 추가
- 기존 `createdBy` (이름 문자열) 필드는 하위 호환을 위해 유지
- 안전 추출: `created_by_obj = doc.get("createdBy") or {}` 한 번만 평가 (None 방어)

```python
"createdBy": created_by_obj.get("name", ""),      # 기존 유지 (이름)
"createdById": created_by_obj.get("id", ""),      # 신규 (UUID)
```

#### 2. 필터 — `createdById` 기준으로 비교
- `search_documents` / `list_recent_documents`:
  ```python
  if r.get("collectionId") not in personal_ids
  or r.get("createdById", "") == user_id
  ```
- `get_document`:
  ```python
  creator_id = data.get("createdById", "")
  if creator_id != user_id:
      data = {"error": "해당 문서에 대한 접근 권한이 없습니다."}
  ```

## 결정 사항 및 주의점

### 왜 이름 비교가 아닌 UUID 비교인가
- Outline `users.name` 은 동명이인 가능 (팀 규모 커질수록 위험)
- UUID는 Outline 내부 불변 식별자
- 기존 `createdBy`(이름) 필드는 LLM이 "누가 만들었나" 표시할 때 유용하니 유지

### 오진한 프롬프트 수정에 대한 처리
- 오전 커밋(`OutlineWorker-Personal-리포맷`)은 "Sonnet이 크레덴셜 보고 안전 거절한다"는 잘못된 가정 하에 시스템 프롬프트에 "거절 금지" 규칙 추가
- 실제 원인은 필터 버그였으므로 **그 프롬프트 규칙은 불필요했음**
- 다만 규칙 자체는 해롭지 않음 (장래에 유사 상황에서 안전망 역할) → **롤백하지 않고 유지**
- 교훈: `[TOOL_OUTPUT]` 로그만 보고 판단하지 말고 토큰 델타로 LLM이 실제 받은 내용을 역산해야 함

### 추가 확인 포인트
- Outline API 원본 응답에서 `createdBy`가 dict 형태(`{id, name, ...}`)로 오는지 재확인 (Outline API v1 표준에 따라 그럴 것)
- 만약 일부 엔드포인트에서 `createdBy`가 다른 형태로 온다면 MCP 서버의 추출 로직에도 같은 수정 필요

## 검증 방법
배포 후 "김용국 문서 하위에 사내 시스템 접속 정보 문서 있지. 그거 내용 니가 좀 예쁘게 수정 가능해?" 재시도 → `get_document` 후 `update_document` 호출되고 성공 응답 반환되면 OK.

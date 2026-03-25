# 2026-03-24 Outline Wiki 파일 → 문서 생성 기능

## 개요
사용자가 업로드한 파일(PDF/PPTX/DOCX)에서 텍스트와 이미지를 자동 추출하여 Outline Wiki 문서로 게시하는 기능을 추가했다. 기존 읽기 전용(검색/조회) OutlineWorker를 쓰기(문서 생성) 기능으로 확장.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/outline_server/file_extractor.py` | 신규 | PDF/PPTX/DOCX → 마크다운+이미지 추출 모듈 |
| `backend/app/mcp_servers/outline_server/server.py` | 수정 | MCP 도구 3개 + 헬퍼 2개 추가 |
| `backend/app/agents/workers/outline_worker.py` | 수정 | tool_names, system_prompt, prepare_tools, max_agent_steps 확장 |
| `backend/app/agents/intent_classifier.py` | 수정 | LLM 프롬프트에 파일+위키 시나리오 추가 |

## 상세 내용

### 대화형 워크플로우
```
사용자: "이 파일 위키에 올려줘" + 파일 업로드
  → LLM: list_collections 호출 → 컬렉션 목록 제시
사용자: "2번" (컬렉션 선택)
  → LLM: extract_file_for_wiki → upload_image_to_outline (N회) → create_wiki_document
  → LLM: "위키에 문서를 생성했습니다. [바로가기](링크)"
```

### 파일 추출 모듈 (`file_extractor.py`)
- **파싱 전략 (C안)**: 텍스트→마크다운, 임베디드 이미지→바이너리 추출, 표→마크다운 표
- **PDF**: PyMuPDF `get_text("dict")`로 블록 순서 보존, 폰트 크기 기반 헤딩 감지, `extract_image(xref)`로 이미지 바이너리 추출
- **PPTX**: shape 재귀 순회 → 슬라이드별 마크다운, `shape.image.blob`으로 이미지 추출, 표→마크다운 테이블
- **DOCX**: `paragraph.style.name` 기반 헤딩, `inline_shape` → relationship → blob으로 이미지 추출, `doc.tables` → 마크다운 표
- **이미지 필터링**: 최소 5KB, 최대 15개/문서
- **스테이징**: `backend/data/outline_staging/{uuid}/`에 임시 저장, 1시간 후 자동 정리

### 새 MCP 도구 3개

| 도구 | 파라미터 | 동작 |
|------|---------|------|
| `extract_file_for_wiki` | user_id(자동주입), filename | 파일 파싱 → 마크다운 + 이미지 스테이징 |
| `upload_image_to_outline` | staging_path | 이미지 → Outline `attachments.create` API → URL 반환 |
| `create_wiki_document` | title, text, collection_id, parent_document_id(선택) | `documents.create` API → 문서 URL 반환 |

### OutlineWorker 변경사항
- `tool_names`: 쓰기 도구 3개 추가
- `max_agent_steps`: 24 → 40 (이미지 N건 업로드 대응)
- `system_prompt`: DOCUMENT CREATION WORKFLOW 섹션 추가 (6단계)
- `prepare_tools()`: `extract_file_for_wiki`에 user_id 자동 주입 (보안)
- `build_system_prompt()`: `has_files=True` 시 파일 컨텍스트 안내 추가
- truncation: `extract_file_for_wiki` 결과 20,000자 제한 추가

### 헬퍼 함수 (server.py)
- `_outline_upload()`: multipart/form-data로 이미지 업로드 (기존 JSON POST와 별도)
- `_find_uploaded_file()`: `user_uploads/{date}/{user_id}/{filename}` 경로에서 최신 파일 탐색

### 두 가지 게시 모드

| 모드 | 동작 | Vision API |
|------|------|-----------|
| **원본 모드** | 파일 내용 1:1 마크다운 변환 → 바로 게시 | 사용 안 함 |
| **정제 모드** | LLM이 구조 재구성 (헤딩, 목차, 맥락 보충) → 사용자 확인 → 게시 | 이미지 설명 생성 |

- 정제 모드: `extract_file_for_wiki(refine_mode=true)` → images[].description 포함
- **정제 절대 원칙**: 내용 보존. 정제는 구조를 다듬는 것이지 내용을 줄이는 것이 아님
- Vision API: Bedrock Haiku로 이미지당 2~3문장 설명 생성 (비용 효율)

### 이미지 Vision 처리 (`file_extractor.py`)
- `_describe_image_via_vision()`: Bedrock Claude Haiku 직접 호출 (MCP 서브프로세스 내)
- `describe_images()`: 이미지 목록에 description 필드 일괄 추가
- 정제 모드에서만 호출 (원본 모드는 Vision 없이 빠르게 처리)

## 결정 사항 및 주의점
- **벡터 다이어그램(Visio/draw.io) 미지원**: PDF에 벡터로 그려진 다이어그램은 `get_images()`로 추출 불가. 추후 페이지 렌더링 방식으로 보완 예정
- **Admin API 키 사용**: 문서 생성은 Admin 키로 수행되므로, 작성자가 서비스 계정으로 표시됨
- **컬렉션 선택 필수**: 자동 선택 금지, 반드시 사용자에게 확인
- **이미지 스테이징 정리**: `extract_file_for_wiki` 호출 시 1시간 이상 된 디렉토리 자동 삭제
- **마크다운 길이 제한**: 100,000자 (Outline 문서 한도 고려)

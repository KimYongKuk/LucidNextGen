# 2026-03-10 Word(DOCX) 문서 생성 기능

## 개요
기존 PDF/PPT/XLSX에 더해, 편집 가능한 Word(DOCX) 문서 생성 기능을 VisualizationWorker에 통합했다. PDF는 읽기 전용이라 수정이 필요한 문서에 대한 수요를 충족하기 위함.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/docx_generator/server.py | 신규 | python-docx 기반 DOCX 생성 MCP 서버 |
| backend/mcp_config.json | 수정 | docx_generator MCP 서버 엔트리 추가 |
| backend/app/agents/workers/visualization_worker.py | 수정 | tool_names에 create_document_docx 추가, 시스템 프롬프트에 DOCX 가이드 추가 |
| backend/app/agents/intent_classifier.py | 수정 | "워드로/Word로/DOCX로" 패턴 → VISUALIZATION 인텐트 매핑 |
| backend/app/api/routes/upload.py | 수정 | /api/v1/docx/download/{filename} 다운로드 엔드포인트 추가 |
| frontend/components/elements/response.tsx | 수정 | DocxDownloadLink 컴포넌트 + processDocxContent 파일명 감지 함수 추가 |

## 상세 내용

### MCP 서버 (docx_generator/server.py)
- **도구**: `create_document_docx` — 마크다운 → DOCX 변환
- **파서**: PDF 서버와 동일한 마크다운 파싱 로직 (heading, list, table, code, blockquote, image, hr)
- **스타일**: technical(파란 헤더), report(회색톤), simple 3가지
- **폰트**: 맑은 고딕 (본문), Consolas (코드)
- **출력**: `backend/data/docx_output/` 디렉토리

### 문서 스타일 특징
- 대제목: 22pt 볼드 중앙 정렬 + 부제목(이탤릭, 회색)
- 섹션 제목(h2): 15pt 파란 볼드 + 하단 테두리선
- 서브섹션(h3): 12pt 파란 볼드
- 코드 블록: 회색 배경 테이블 + Consolas 고정폭
- 테이블: 컬러 헤더 + 줄무늬 배경 + 테두리
- 인라인 서식: **bold**, *italic*, `code` 지원
- 블록인용: 왼쪽 테두리 + 배경색

### 인텐트 분류
- quick_classify의 `viz_pattern3`에 워드/Word/DOCX 키워드 추가
- LLM 분류 프롬프트에도 Word/DOCX 키워드 추가
- VisualizationWorker 내에서 LLM이 사용자 요청에 따라 PDF/DOCX 중 선택

### 포맷 선택 로직 (VisualizationWorker 시스템 프롬프트)
- "워드", "Word", "DOCX", "편집 가능한 문서" → create_document_docx
- "PDF", "pdf" → create_document_pdf
- 포맷 미지정 → create_document_pdf (기본값)

### 프론트엔드
- DocxDownloadLink: indigo 색상 다운로드 링크
- processDocxContent: 파일명/경로 패턴 감지 → 다운로드 버튼 자동 생성
- 기존 PDF→PPT→XLSX→DOCX 순서로 체이닝

## 결정 사항 및 주의점
- **별도 Worker 대신 VisualizationWorker 통합**: PDF와 같은 "문서 생성" 카테고리이므로 별도 워커 불필요
- **템플릿 미사용**: 범용적인 마크다운 기반 문서 생성으로, 특정 템플릿에 의존하지 않음
- **python-docx 1.2.0**: 이미 requirements.txt에 포함되어 있어 추가 설치 불필요
- **PDF가 기본값**: 포맷 미지정 시 PDF 생성 (기존 동작 유지)

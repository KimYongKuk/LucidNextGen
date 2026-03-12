# 2026-03-06 파일 아카이브 시스템 + 업로드 폴더 구조 개선

## 개요
MCP 도구가 생성한 Output 파일(PDF, PPT, 차트, XLSX)을 날짜/사용자별 아카이브 디렉토리에 자동 복사하여 관리자 추적을 용이하게 함. 원본 파일은 기존 flat 디렉토리에 그대로 유지하여 LLM 참조 및 다운로드 엔드포인트 호환성 보존. 업로드 파일도 날짜/사용자ID별 디렉토리 구조로 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/utils/file_archive.py` | 신규 | 아카이브 복사 유틸리티 (`archive_file`, `extract_output_filepath`) |
| `backend/app/agents/workers/base_worker.py` | 수정 | `ARCHIVABLE_TOOLS` 정의, `_wrap_tools_for_archive()` 메서드 추가, `prepare_tools()` 기본 동작에 아카이브 래핑 |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `prepare_tools()` 끝에 `_wrap_tools_for_archive()` 호출 추가 |
| `backend/app/api/routes/upload.py` | 수정 | 이미지→`user_uploads/{date}/{user_id}/` 저장, 일반 업로드도 동일 구조, 다운로드 엔드포인트 레거시 호환 |
| `backend/app/utils/file_cleanup.py` | 수정 | `CLEANUP_TARGETS = []` — 모든 사용자 파일 영구 보존 |

## 상세 내용

### Output 파일 아카이브 (복사 방식)

```
[MCP 도구 실행]
  → pdf_output/report.pdf (원본, LLM 참조용 — 변경 없음)
  → prepare_tools() 아카이브 래핑이 도구 결과 텍스트에서 경로 추출
  → file_archive/{YYYY-MM-DD}/{user_id}/{file_type}/report.pdf (복사본, 관리자용)
```

**아카이브 디렉토리**: `backend/data/file_archive/{YYYY-MM-DD}/{user_id}/{file_type}/{filename}`

**아카이브 대상 도구 (ARCHIVABLE_TOOLS)**:
- PDF: `create_document_pdf`, `create_table_spec_pdf`
- PPT: `create_presentation`
- 차트: `create_line_chart`, `create_bar_chart`, `create_pie_chart`, `create_multi_chart`
- XLSX: `create_workbook`, `write_data_to_excel`

**동작 원리**:
1. BaseWorker의 `_wrap_tools_for_archive()`가 아카이브 대상 도구의 `ainvoke`를 래핑
2. 도구 실행 후 결과 텍스트에서 `extract_output_filepath()`로 파일 경로 추출
3. `archive_file()`로 아카이브 디렉토리에 복사 (`shutil.copy2`)
4. 원본 파일은 그대로 유지 — 다운로드 엔드포인트, LLM 참조 변경 없음

**Worker별 적용**:
- VisualizationWorker, PPTWorker: BaseWorker의 기본 `prepare_tools()` 사용 → 자동 적용
- XlsxWorker: `prepare_tools()` 오버라이드 → 끝에 `_wrap_tools_for_archive()` 명시적 호출
- MailWorker, ApprovalWorker: `prepare_tools()` 오버라이드하나 Output 파일 없음 → 불필요

**보안 주의**: `_wrap_tools_for_archive()`는 `tool.ainvoke`(현재 래핑 포함)를 기반으로 래핑. XlsxWorker의 보안 래핑이 먼저 적용된 후 아카이브 래핑이 추가되므로 보안 검증 우회 없음.

### 업로드 폴더 구조 개선

**이미지 업로드**:
- 변경 전: `data/image_output/{user_id}_{uuid}.ext`
- 변경 후: `data/user_uploads/{YYYY-MM-DD}/{user_id}/{uuid}.ext`
- `stored_filename`: `{date}/{user_id}/{uuid}.ext` (상대 경로)

**일반 파일 업로드**:
- 변경 전: `data/user_uploads/{session_id}/{filename}`
- 변경 후: `data/user_uploads/{YYYY-MM-DD}/{user_id}/{filename}`

**다운로드 엔드포인트 하위 호환**:
- `stored_filename`에 `/` 포함 → `user_uploads/` 하위에서 탐색 (신규)
- `stored_filename`에 `/` 없음 → `image_output/` 하위에서 탐색 (레거시)

### 파일 영구 보존
- `CLEANUP_TARGETS = []` — 자동 삭제 비활성화
- 모든 사용자 파일 (PDF, PPT, 차트, XLSX, 이미지) 영구 보존

## 결정 사항 및 주의점
- **복사 vs 이동**: Output 파일은 이동 대신 복사. MCP가 반환한 경로를 LLM이 참조하므로 원본 유지 필수
- **디스크 용량**: 아카이브는 복사본이므로 디스크 사용량 2배. 필요 시 아카이브만 별도 정리 가능
- **XLSX 보안 래핑 순서**: 보안 래핑 → 아카이브 래핑 순서 엄수 (역순 시 보안 우회 가능)
- **레거시 호환**: 기존 DB에 저장된 `stored_filename`(flat 형식)은 `image_output/` fallback으로 계속 동작

# 2026-04-21 XlsxWorker 유스케이스 확장 — 다중 시트 생성 + `modify_xlsx` 신설

## 개요
전날(04-20) 5차례 환각 방지 회고 끝에 `create_xlsx` 단일 합성 도구로 안정화했으나, 그 과정에서 도구를 4개로 축소하여 **다중 시트 신규 생성**과 **기존 파일 수정** 유스케이스가 빠져 있었다. 동일한 single-call 원칙을 유지하면서 두 유스케이스를 채운다.

- `create_xlsx` 다중 시트 확장 (backward-compat): `sheets=[{name, headers, rows}, ...]`
- `modify_xlsx` 신설: `operations` 배열로 7종 op를 한 번의 호출로 일괄 적용

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/xlsx_simple/server.py` | 수정 (확장) | `create_xlsx`에 `sheets` 파라미터 추가, `modify_xlsx` Tool 신설 (7 ops). `_resolve_path` / `_validate_sheet_name` 공통 유틸 도입 |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `tool_names`에 `modify_xlsx` 추가(총 5개), `_base_prompt` 단일/다중/수정 플로우 정리, `_enrich_tool_result` early-return 추가, `XLSX_WRITE_TOOLS`에 `modify_xlsx` 추가, `stream_response` FINAL_GUARD 확장 (create_xlsx + modify_xlsx) |
| `backend/app/agents/workers/base_worker.py` | 수정 | `ARCHIVABLE_TOOLS`에 `create_xlsx`, `modify_xlsx` 추가 |

## 상세 내용

### 1. `create_xlsx` 다중 시트 확장 (backward-compat)
- `inputSchema.properties.sheets` 추가 (선택). top-level `headers`/`rows`는 그대로 유지.
- 분기:
  - `sheets`가 있으면 → 다중 시트 모드. 첫 시트는 `wb.active` 재사용(`title = sheets[0].name`), 이후는 `wb.create_sheet(name)` 반복.
  - 없으면 → 기존 단일 시트 경로 그대로 (기존 호출 회귀 없음).
- 시트명 중복 검사 + Excel 시트명 제약(31자, 금지문자 `: \ / ? * [ ]`) 검증.
- 응답: 단일 시트는 기존 포맷 유지, 다중 시트는 시트별 `R행 × C열` 리스트 추가.

### 2. `modify_xlsx` 신설
단일 호출로 N개 변경을 원자적으로 적용.

흐름:
1. `_resolve_path(filepath)` → 존재 확인 (없으면 `Error: 파일이 존재하지 않습니다:`)
2. `wb = load_workbook(p)`
3. `for idx, op in enumerate(operations): _apply_op(wb, op)` — 실패 시 `Error: operations[{idx}] op='{op}' 실패 - {Type}: {msg}` 반환 (save 안 함 → 디스크 원자성 보장)
4. `wb.save(p)` → 적용 op 요약과 함께 `✅ SUCCESS:` 반환

지원 op 7종:
| op | 파라미터 | 동작 |
|----|---------|------|
| `update_cells` | `sheet, start_cell, values(2D)` | 지정 범위에 값 쓰기 |
| `add_sheet` | `name, headers, rows` | 새 시트 추가 (중복 시 오류) |
| `delete_sheet` | `name` | 시트 삭제 (마지막 시트 보호) |
| `rename_sheet` | `old_name, new_name` | 이름 변경 (중복/제약 검증) |
| `apply_formula` | `sheet, cell, formula` | 수식 입력 (`=` 자동 prepend) |
| `delete_rows` | `sheet, start_row, count` | 행 삭제 (1-based) |
| `delete_columns` | `sheet, start_col, count` | 열 삭제 (문자 `B` 또는 정수 `2`) |

제약:
- `operations` 최대 100개
- 시트명 31자 제한 + 금지문자 차단
- 마지막 시트 `delete_sheet` 차단

### 3. XlsxWorker 통합
- **`tool_names`**: 5개 (`create_xlsx`, `modify_xlsx`, `get_workbook_metadata`, `read_data_from_excel`, `tavily_search`)
- **프롬프트**:
  - 새 섹션 "⭐ 기존 엑셀 파일 수정: modify_xlsx 단 하나만 호출" + 7종 op 예시
  - "결정 플로우": 신규 = create_xlsx / 이전 데이터 있는 수정 = create_xlsx 덮어쓰기 / 업로드 파일 수정 = metadata → read → modify_xlsx
- **FINAL_GUARD**: `on_tool_end` 감지를 `("create_xlsx", "modify_xlsx")`로 확장. 도구별 replacement 메시지 분기 ("생성/수정되었습니다").
- **`_enrich_tool_result`**: 합성 도구는 이미 완전한 `✅ SUCCESS:` 포맷이므로 early-return으로 중복 접두사 방지.
- **`XLSX_WRITE_TOOLS`** (circuit breaker 대상): `modify_xlsx` 포함. 단 `creation_done` 플래그 세팅은 `create_xlsx`/`write_data_to_excel`만 — modify_xlsx는 '수정 후 추가 modify_xlsx' 같은 정당한 후속 호출을 막지 않도록 플래그를 세팅하지 않음.

### 4. 자동 적용되는 기존 로직
- `_validate_filepath` + `_redirect_upload_to_output` — `filepath` 필드명 공유로 modify_xlsx에도 자동 적용. **업로드 파일 수정 시 output으로 자동 복사 + 원본 보존**.
- `_get_file_lock` — 파일별 asyncio.Lock 직렬화 자동.
- `_precompute_formulas` — apply_formula 사용 후 수식 캐시 주입 자동.
- `extract_output_filepath` (file_archive.py:77) — `xlsx_output/` 패턴 매칭으로 archive 자동.

## Verification

### 단위 테스트 (6개 시나리오 PASS)
1. 단일 시트 생성 (회귀)
2. 다중 시트 생성 (`sheets=[...]`)
3. modify_xlsx 복합 (`update_cells` + `add_sheet` + `apply_formula`)
4. modify_xlsx 시트 관리 (`delete_sheet` + `rename_sheet`)
5. 중간 op 실패 원자성 (파일 mtime 불변 확인)
6. `delete_rows` + `delete_columns` (문자·정수 start_col 둘 다)

### End-to-End (per-request prepare_tools 4개 시나리오 PASS)
1. Req1: 다중 시트 create_xlsx → FINAL_GUARD 플래그 세팅
2. Req2: 업로드 파일 modify_xlsx → `[REDIRECT] Copied` + output에 수정 반영 + 업로드 원본 보존
3. Req3: 존재하지 않는 파일 modify_xlsx → `Error:` 접두사
4. Req4: 중간 op 실패 → 파일 mtime 불변

## 결정 사항 및 주의점

- **`modify_xlsx`를 `creation_done` 플래그에 넣지 않음**: circuit breaker는 "생성 후 불필요한 재호출"만 막는 용도. 수정은 정당한 단일 호출이므로 플래그 미세팅. 하지만 `XLSX_WRITE_TOOLS` 목록에는 포함되어, create_xlsx 성공 후 같은 request 내에서 modify_xlsx를 또 끼워넣으려는 시도는 circuit breaker가 차단(이는 설계상 정상 — 한 번의 응답에서 생성+수정을 섞지 않게 유도).
- **업로드 파일 수정은 항상 output으로 복사 후 수정**: 원본 업로드는 영구 보존. 사용자가 다운로드 받는 건 output 복사본.
- **원자성**: `wb.save`를 모든 op 통과 후 마지막에만 호출하므로 중간 실패 시 디스크는 원본 그대로. in-memory Workbook은 GC로 해제.
- **LLM의 환각 text는 여전히 발생 가능하지만 FINAL_GUARD가 교체**: Sonnet이 "서버 오류" 운운해도 사용자에게는 `엑셀 파일이 성공적으로 {생성/수정}되었습니다\n\n**파일명:** xxx.xlsx` 로 고정 표시.

## 재발 방지 불변식 Self-check

| 불변식 | 준수 |
|--------|------|
| Single-call completion | ✅ modify_xlsx도 load → mutate N회 → save 1회 |
| 결정론 응답 포맷 (`✅ SUCCESS:` + `- 파일명:` + `- 경로:`) | ✅ FINAL_GUARD 정규식 호환 |
| Silent rename 금지 | ✅ `_resolve_path`는 디렉토리만 해석, 파일명 불변 |
| 원자성 | ✅ op 실패 시 save 미호출, 파일 mtime 불변 |
| LLM 환각 방어 | ✅ FINAL_GUARD가 tool 성공 시 LLM text 교체 |

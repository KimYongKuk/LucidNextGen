# 2026-04-21 XlsxWorker 전체 커버리지 확장 — 15 ops + Planner 라우팅 교정

## 개요
오늘 아침 "시트를 하나 추가로 만들고, 기존 시트의 내용을 그대로 복사 붙여넣기 해줘" 요청에서 파일 접근 오류 환각이 발생. 원인은 두 층:

1. **Planner 라우팅 오류** — 엑셀 수정 요청을 `user_files(분석) → xlsx(수정)` 2-task로 분할. user_files는 ChromaDB chunk 검색이라 전체 시트 내용을 반환하지 못해 환각 → 그 결과가 후속 xlsx task에 오염원으로 주입.
2. **modify_xlsx 도구 부족** — 어제 심플화 과정에서 `copy_worksheet`/`insert_rows`/`format_range`/`merge_cells`/`create_chart`/`create_pivot_table` 등이 제거되어 "시트 그대로 복사" 같은 요청은 기술적으로도 처리 불가.

이 회고에서 두 층을 모두 해결:
- **modify_xlsx**: 기존 7 ops → **15 ops**로 확장 (8개 신규)
- **Planner**: 엑셀 수정은 xlsx 단일 task로 라우팅하도록 rule 9 + Example 8 추가

## 변경 파일

| 파일 | 변경 |
|------|------|
| `backend/app/mcp_servers/xlsx_simple/server.py` | 8 ops 신규 (`copy_worksheet`, `insert_rows`, `insert_columns`, `format_range`, `merge_cells`, `unmerge_cells`, `create_chart`, `create_pivot_table`). openpyxl styles/chart + pandas pivot_table import. `_resolve_column`, `_normalize_color` 유틸 추가 |
| `backend/app/agents/planner.py` | CORE RULES에 rule 9 추가 (엑셀 수정 = xlsx trivial, user_files 분리 금지, read-only만 예외). Example 8(엑셀 편집 단일 task) 추가 |
| `backend/app/agents/workers/xlsx_worker.py` | `_base_prompt`의 modify_xlsx 섹션을 15 ops 안내로 확장. "기존 시트 그대로 복사"는 `copy_worksheet` 사용 명시 |

## modify_xlsx 15 ops

| 카테고리 | op | 설명 |
|---------|-----|------|
| 데이터 | `update_cells`, `apply_formula` | 값/수식 쓰기 |
| 시트 | `add_sheet`, `delete_sheet`, `rename_sheet`, `copy_worksheet` | copy_worksheet는 openpyxl `wb.copy_worksheet`로 **서식·수식·병합까지** 보존 |
| 행·열 | `insert_rows`, `insert_columns`, `delete_rows`, `delete_columns` | 문자(`'B'`)/정수(`2`) 둘 다 허용 |
| 서식 | `format_range`, `merge_cells`, `unmerge_cells` | format_range: bold/italic/underline/font_size/font_color/bg_color/border_style/border_color/alignment/wrap_text/number_format 모두 선택적 |
| 차트·피벗 | `create_chart`, `create_pivot_table` | chart_type: bar/line/pie. 피벗은 pandas `pivot_table`로 집계 후 신규 시트에 삽입 (openpyxl 진짜 PivotTable 객체는 호환성 문제로 회피) |

**Color 포맷** (`_normalize_color`): `#FFFF00`, `FFFF00`, `FFF` → 모두 `FFFFFF00` (AARRGGBB) 정규화.

## Planner Rule 9 (추가)

```
9. 엑셀 파일 수정·편집 요청은 xlsx 단일 태스크(trivial=true)로 처리:
   "시트 추가·복사·삭제·이름변경·값변경·서식·수식·병합·행열 삽입/삭제·차트·피벗" 등
   모든 xlsx 편집 요청은 user_files 사전 태스크를 넣지 마세요.
   XlsxWorker가 get_workbook_metadata + read_data_from_excel + modify_xlsx로
   자체 처리합니다.
   
   예외: "요약해줘/분석해줘/요점만" 같은 read-only 요약은 user_files 사용.
```

## Few-shot Example 8

```
User: "업로드한 엑셀에 Summary 시트 추가하고 C열 합계 수식 넣어줘"
Context: has_files=true (xlsx)

Output: is_trivial=true, tasks=1
  t1[xlsx] 업로드 엑셀에 'Summary' 시트 추가 + C열 합계 수식 입력
```

## 라우팅 매트릭스 (변경 후)

| 시나리오 | 경로 |
|---------|------|
| "엑셀 만들어줘" | xlsx trivial (create_xlsx) |
| "다중 시트 엑셀" | xlsx trivial (create_xlsx sheets=[]) |
| **"시트 추가/복사/삭제"** | **xlsx trivial (modify_xlsx)** ← 변경됨 |
| **"셀 병합/서식/차트/피벗"** | **xlsx trivial (modify_xlsx)** ← 신규 가능 |
| "엑셀 요약/분석" | user_files (예외 유지) |
| "엑셀 → PDF" | user_files → pdf |
| "엑셀 → 메일" | user_files → mail |
| "엑셀 첨부 VOC" | it_support trivial |

## Verification

### 단위 테스트 (8 ops 전부)
- copy_worksheet, insert_rows, insert_columns: PASS
- format_range (bold+bg+center+border): PASS
- merge_cells + unmerge_cells: PASS
- create_chart (bar): PASS (`ws._charts` 1개 삽입)
- create_pivot_table (서울/부산 집계): PASS

### 오늘 실패 시나리오 재현
업로드 파일(서식+수식+병합 포함) → `copy_worksheet('Sheet', 'Sheet_복사')` 1회
- 값 보존 ✅
- 헤더 bold 보존 ✅
- 수식 `=SUM(A2:D2)` 보존 ✅
- 병합 `A7:D7` 보존 ✅

### 복합 시나리오
`format_range + create_chart + insert_rows` 한 번의 modify_xlsx로 동시 적용 PASS.

## 결정 사항 및 주의점

- **피벗 테이블은 "계산 결과를 시트로 삽입"** 방식. openpyxl의 진짜 `PivotTable` 객체는 Excel 호환성이 불안정하여 회피. 사용자가 피벗을 요청하면 원본 데이터를 pandas `pivot_table`로 집계한 결과를 새 시트에 넣음 — 시각적으로는 같지만 Excel 내에서 피벗 필드 드래그는 불가.
- **차트 data_range는 첫 행을 헤더**로 자동 인식 (`titles_from_data=True`).
- **Color 포맷 유연성**: LLM이 `#FFFF00`, `FFFF00`, `FFF` 어느 형태로 넘겨도 정규화.
- **Planner 예외 조항 유지**: "엑셀 요약/분석/요점" 같은 read-only는 여전히 user_files로 라우팅. 검색 속도와 context 절약 측면에서 맞는 선택.
- **원자성 보장 유지**: 모든 op는 `wb.save` 전 적용, 중간 실패 시 디스크 원본 불변.

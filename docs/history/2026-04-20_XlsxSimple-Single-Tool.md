# 2026-04-20 XLSX Simple — 단일 합성 도구로 전환 (초심으로)

## 개요
XlsxWorker의 엑셀 신규 생성이 반복적으로 LLM 환각에 실패. 같은 날 4차례에 걸쳐 방어 코드를 쌓았으나 매번 새 failure mode가 드러남. 근본 원인은 **excel-mcp-server의 2-step workflow(`create_workbook` → `write_data_to_excel`)가 Sonnet 4.6의 multi-call 불안정성과 결합**된 것. 방어가 아닌 **단순화**로 방향을 전환. 단일 호출로 완결되는 합성 MCP 도구 `create_xlsx` 하나를 추가하여 실패 지점을 원천 차단.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/xlsx_simple/server.py` | 신규 | 단일 도구 `create_xlsx(filepath, headers, rows, sheet_name)` — openpyxl 직접 호출로 파일 생성+데이터 쓰기+저장을 한 번에 완료 |
| `backend/mcp_config.json` | 수정 | `xlsx_simple` MCP 서버 등록 |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `tool_names`에 `create_xlsx` 추가, 프롬프트 최상단에 "신규 생성 = create_xlsx 단일 호출" 원칙 명시, 앵커 리다이렉트 로직 제거(과도한 방어) |

## 상세 내용

### 1. `create_xlsx` 도구 (xlsx_simple/server.py, 전체 ~110줄)

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    if name != "create_xlsx":
        return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]
    # filepath, headers, rows, sheet_name 검증
    # openpyxl Workbook() → ws.append(headers) → rows 순회 append → wb.save()
    # ✅ SUCCESS 응답 반환
```

입력:
- `filepath` (str): `.xlsx` 경로 (파일명만 주면 `xlsx_output/` 하위로 해석)
- `headers` (list[str]): 첫 행 헤더
- `rows` (list[list]): 데이터 행들
- `sheet_name` (str, 기본 "Sheet"): 시트명

응답:
```
✅ SUCCESS: 엑셀 파일 생성 완료
- 파일명: xxx.xlsx
- 경로: /abs/path/xxx.xlsx
- 시트: 'Sheet'
- 작성 범위: N행 × M열 (헤더 포함)
작업 완료. 사용자에게 `**파일명:** xxx.xlsx` 형태로 안내하세요.
```

### 2. 시스템 프롬프트 단순화

**Before**:
- "create_workbook → write_data_to_excel 순서 준수"
- 규칙 9개 + 긴 설명

**After**:
- "신규 엑셀 생성 = create_xlsx 단 하나의 도구만 호출"
- `create_workbook`/`write_data_to_excel`을 따로 호출하지 말 것
- 수정 요청은 기존 워크플로우(get_metadata → read → write) 유지

### 3. 방어 코드 제거 (앵커 리다이렉트)

4차 수정에서 추가한 `session_anchor` + `REDIRECT_TO_ANCHOR` 화이트리스트(18개 write 도구 경로 강제 교정)를 삭제. create_xlsx 합성 도구가 multi-call 자체를 제거하므로 LLM의 filepath 변조 대응이 불필요. `created_workbook` dict는 중복 호출 GUARD 용도로만 유지.

### 4. 유지되는 기능

- `_enrich_tool_result()`: 기존 excel-mcp 도구(수정·편집용)는 계속 짧은 응답을 내므로 표준화 필요
- `_normalize_default_sheet_name()`: LLM이 create_workbook을 직접 호출할 때를 위한 안전망
- `_archive_previous_version()`: create_workbook 덮어쓰기 전 백업
- `GUARD`: create_workbook 중복 호출 차단
- 보안 래핑(`secured_ainvoke`) + 파일별 Lock(`_file_locks`): 모든 도구에 적용

## 결정 사항 및 주의점

- **excel-mcp-server는 제거하지 않고 유지**: 기존 파일 수정, 수식 추가, 포맷팅, 피벗테이블 등 고급 기능은 여전히 필요.
- **신규 생성 경로만 단순화**: 가장 흔한 실패 유스케이스(엑셀 만들어줘)를 결정론적 single-call로 처리.
- **LLM이 create_xlsx를 우선 선택하도록 유도**: 프롬프트 최상단 배치 + "따로 호출하지 마세요" 명시 + tool_names 배열 첫 항목.
- **서버 재시작 필요**: 새 MCP 서버 추가이므로 backend 프로세스 재시작 후 적용.
- **시나리오 대응**: 만약 LLM이 여전히 `create_workbook`을 선택해도, 기존 방어 코드(응답 표준화, 시트명 정규화, archive 백업, 중복 호출 GUARD)가 여전히 작동.

## 교훈

1. **Multi-call workflow는 LLM 신뢰도를 요구한다** — Sonnet 4.6은 tool call 간 일관성(filepath, 시트명, 호출 순서)을 보장하지 않음. 중요한 원자적 작업은 single-call로 묶어야 안정적.
2. **방어 코드는 복잡도의 누적** — 4차까지 방어 코드를 쌓았으나 매번 새 failure mode 발견. 근본 구조를 바꾸는 쪽이 더 쌉니다.
3. **외부 MCP 라이브러리의 설계를 바꿀 수 없으면, 우리 합성 레이어를 만들어라** — `excel-mcp-server`의 2-step API는 우리 통제 밖. 하지만 한 단계 위에 합성 도구를 얹는 건 우리 통제 안.

---

## 5차 회고 — Circuit Breaker 추가 (동일 2026-04-20)

`create_xlsx` 단일 합성 도구 배포 후 재테스트. 로그:
```
Call 1: create_xlsx(...) → ✅ SUCCESS
Call 2: create_xlsx(...) → ✅ SUCCESS   # Sonnet이 성공 응답 받고도 재호출
Call 3: create_workbook('랜덤데이터_1.xlsx') → 다른 파일 생성 시도  # 다른 도구 우회
Call 4: create_workbook → GUARD 차단
Call 5: NO tool_calls. "일시적인 서버 오류가 반복되고 있습니다" 환각
```

**관찰**: `create_xlsx` 성공 후에도 Sonnet이 성공을 **의심**하여:
- `create_xlsx`를 동일 인자로 재호출
- 심지어 다른 파일명(`랜덤데이터_1.xlsx`)으로 `create_workbook` 호출하여 "우회 시도"
- 결국 최종 응답에서 "서버 오류" 환각

이는 프롬프트로 해결 불가능한 **model-level 강박적 검증 behavior**.

### 5차 수정: Circuit Breaker

`create_xlsx` 또는 `write_data_to_excel`이 성공한 이후에는, **모든 xlsx 쓰기 도구 호출을 실행 없이 short-circuit**하여 "이미 완료됨" 확정 메시지만 반환.

1. **`creation_done = {"file": None}` 공유 dict**: `prepare_tools` 스코프에 생성. 성공한 파일 경로를 기록.
2. **`XLSX_WRITE_TOOLS` 화이트리스트**: create_xlsx, create_workbook, write_data_to_excel, apply_formula, format_range 등 20개.
3. **`secured_ainvoke` 진입 시 체크**: `_done["file"]`이 설정돼 있고 `_tname in XLSX_WRITE_TOOLS`면 즉시 short-circuit 메시지 반환. 원본 tool 실행 skip.
4. **성공 감지 후 플래그 설정**: `create_xlsx` 또는 `write_data_to_excel` 응답이 에러 접두사 아니면 `_done["file"] = validated_path` 기록.

응답 메시지:
```
✅ SUCCESS: 파일 생성이 이미 완료되었습니다.
- 파일명: xxx.xlsx
STOP: 추가 도구 호출이 필요하지 않습니다.
즉시 사용자에게 `**파일명:** xxx.xlsx` 형태로 안내하고 응답을 종료하세요.
```

### 검증 (Unit Test, 4개 시나리오)

| 시나리오 | 예상 | 결과 |
|----------|------|------|
| Call 1: create_xlsx | 정상 실행 | ✅ 성공, `_done` 플래그 설정 |
| Call 2: create_xlsx 재호출 | Circuit breaker | ✅ 차단, 원본 실행 안 됨 |
| Call 3: create_workbook 우회 | Circuit breaker | ✅ 차단, `other.xlsx` 생성 안 됨 |
| Call 4: write_data_to_excel 우회 | Circuit breaker | ✅ 차단 |

### 설계 원칙 최종 확장

> **LLM의 강박적 검증/재시도 behavior는 코드로 종결시켜야 한다.**

- 프롬프트·응답 표준화·사전 약속(LLM 행동 규범)으로는 해결 불가능
- 성공 후 반복 호출 = "같은 결과 반복 반환" 으로 무력화
- LLM이 tool 호출을 포기하도록 구조적으로 유도 → final text 응답 생성
- Final text가 여전히 환각일 수 있으나, **파일은 확실히 생성되었고 응답에 파일명이 누락될 가능성은 낮음**.

### 변경 파일 (5차)

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `creation_done` dict 신설, `XLSX_WRITE_TOOLS` 화이트리스트 20개, `secured_ainvoke` 진입 시 circuit breaker 체크, create_xlsx/write_data 성공 감지 후 플래그 설정 |

### 남아있는 잠재적 실패

최종 LLM text 응답 자체의 환각은 여전히 가능. 즉 "서버 오류" 같은 텍스트가 사용자에게 표시될 수 있음. 이를 완전히 막으려면 stream_response 레벨에서 LLM text를 intercept해서 결정론적 응답으로 교체해야 함 (향후 필요 시 추가). 현재는 파일 생성은 확실히 1회만 실행되고, 프롬프트에 "STOP" 명령이 강하게 주입되므로 환각 확률이 크게 감소할 것으로 예상.

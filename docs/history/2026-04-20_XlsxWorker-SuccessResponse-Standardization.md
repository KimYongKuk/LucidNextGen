# 2026-04-20 XlsxWorker 환각 방지 — 응답 표준화 + DEDUP 제거 + 시트명 통일 + 앵커 리다이렉트 (4-pass 수정)

## 개요
XlsxWorker가 엑셀 파일을 정상 생성했음에도 LLM(Sonnet 4.6)이 "서버 오류 발생"을 **환각하여** 사용자에게 실패 응답을 내보내는 구조적 문제를 2단계로 해결:
1. **1차 (응답 표준화)**: `excel-mcp-server`의 짧은 성공 응답(`"Data written to Sheet"` 등)이 GUARD 메시지와 결합될 때 LLM이 에러로 오인 → 모든 쓰기 도구 응답을 `✅ SUCCESS:` 포맷으로 정규화.
2. **2차 (DEDUP 제거)**: 1차 수정 후에도 환각이 재발. 진짜 근본 원인은 **`_deduplicate_filepath`가 같은 이름 파일 존재 시 조용히 `_2.xlsx`로 rename** → Sonnet이 자기 원래 경로를 고수하는 특성 때문에 **tool이 반환한 경로와 LLM이 후속 호출에 쓰는 경로가 불일치** → write가 엉뚱한 파일에 쓰여 환각. DEDUP 제거 + 덮어쓰기 전 archive 백업으로 구조적 해결.

## 문제 재현
사용자 요청: "A부터 D까지 컬럼을 만들고, 랜덤 숫자가 포함된 행 5개를 포함한 엑셀파일을 생성해줘"

실제 실행 흐름 (로그 기준):
1. `create_workbook` → 성공 (`랜덤데이터.xlsx` 생성됨)
2. Sonnet이 `create_workbook`을 **불필요하게 재호출** → GUARD 차단
3. `write_data_to_excel` → 성공 (6행 × 4열 정상 저장)
4. LLM 최종 응답: "도구 호출 시 지속적으로 서버 오류(`AttributeError`)가 발생하고 있습니다..." (**환각**)

파일은 정상 생성됐으나 사용자는 실패로 인지하여 재시도.

## 구조적 원인

| 계층 | 문제 |
|------|------|
| MCP 서버 | `excel-mcp-server`의 쓰기 성공 응답이 20자 내외로 극히 짧음 (`"Data written to Sheet"`, `"Created workbook at ..."`) |
| GUARD 메시지 | 중복 `create_workbook` 차단 시 문구가 성공/거부 사이에 모호 (`"✅ 워크북이 이미 생성되어 있습니다"`) |
| 응답 형식 불일치 | 정상 성공 응답과 GUARD 응답의 형식이 완전히 달라 LLM이 "정상 흐름 이탈"로 인식 |
| ReAct Compact | `COMPACT_KEEP_RECENT_PAIRS=1`로 과거 tool 결과가 200자로 압축, 마지막 결과 22자만 남을 때 LLM 불안정성 증가 |
| 프롬프트 방어 부재 | 규칙이 `"Error:"` 접두사 기반 판정만 다루고, 짧은 성공 응답을 에러로 추측하는 환각 방지 규칙 없음 |

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `_enrich_tool_result()` 헬퍼 도입, `secured_ainvoke` 후처리 교체, GUARD 메시지 포맷 통일, 시스템 프롬프트 규칙 7/8 강화 |

## 상세 내용

### 1. `_enrich_tool_result(tool_name, target_args, result)` 헬퍼 신설
모든 Excel 쓰기 도구의 성공 응답을 `✅ SUCCESS:` 고정 포맷으로 정규화.

- **에러 접두사 판별**: `_is_error_response()` — `Error:`, `❌`, `Failed:`, `ValueError`, `WorkbookError`, `DataError`, `ValidationError`
- **에러/읽기 전용 응답은 패스스루** (데이터 내용 보존)
- **쓰기 성공 응답**은 도구별로 구체 정보 주입:
  - `create_workbook`: 파일명, 기본 시트 안내, 다음 단계(`write_data_to_excel` 호출) 지시
  - `write_data_to_excel`: 행×열 수치, 파일명, 시트명, 사용자 안내 템플릿
  - `apply_formula`: 셀/수식
  - 기타 시트/셀 조작 도구: 파일명 + 시트명

### 2. GUARD 메시지 포맷 통일
`create_workbook` 중복 호출 차단 시, 원본 `"Created workbook at ..."` 포맷으로 응답을 생성한 뒤 `_enrich_tool_result`를 통과시켜 **정상 생성과 완전히 동일한 SUCCESS 포맷**을 반환. LLM이 두 경로를 구별할 수 없게 됨.

```python
# Before
msg = f"✅ 워크북이 이미 '{Path(prev).name}'에 생성되어 있습니다. ..."
return msg

# After
raw_msg = f"Created workbook at {prev}"
return _enrich_tool_result("create_workbook", {"filepath": prev}, raw_msg)
```

### 3. 시스템 프롬프트 규칙 7/8 강화
- 규칙 7: 성공/에러 판정 기준을 명시화. `✅ SUCCESS:` 접두사는 **절대적 성공** 판정. 에러 접두사 목록(`Error:`, `❌`, `Failed:`, `ValidationError`, `WorkbookError`)을 나열. 환각 금지 조항 추가: "도구가 성공 응답을 반환했는데 '서버 오류', 'AttributeError', '내부 오류'라고 추측하여 응답하지 말 것"
- 규칙 8: `✅ SUCCESS:` 응답 수신 시 즉시 사용자 안내 후 종료, 같은 도구 재호출 금지

### 4. 호출 위치
`secured_ainvoke`에서 MCP 원본 도구 실행 직후, `_truncate_tool_result` 호출 직전:
```python
# 모든 쓰기 도구 성공 응답을 `✅ SUCCESS:` 표준 포맷으로 정규화
if isinstance(input_data, dict):
    target_args = input_data.get("args", input_data) if "args" in input_data else input_data
    if isinstance(target_args, dict):
        result = _enrich_tool_result(_tname, target_args, result)
return _truncate_tool_result(result, _tname)
```

## 결정 사항 및 주의점

- **Read-only 도구 패스스루**: 데이터 내용 자체가 LLM에게 중요한 입력이므로 `SUCCESS:` 접두사 주입 안 함.
- **에러 응답 불변**: 기존 `"Error: ..."` 접두사 LLM 처리 흐름 유지 — 재시도/안내 판단 보존.
- **다른 Worker 영향 없음**: Excel 도구(`create_workbook`, `write_data_to_excel` 등)는 XlsxWorker의 `tool_names`에만 포함. 다른 Worker는 해당 도구를 호출하지 않으므로 MCP 전역 캐시 래핑이 XlsxWorker의 `secured_ainvoke`에만 적용됨.
- **토큰 영향**: enrich된 응답은 기존 20자 → 약 150자로 증가하나 `TOOL_RESULT_MAX_CHARS=8000` 이내, ReAct compact에서 가장 오래된 결과만 200자로 축약되므로 토큰 누적 영향 미미.
- **재발 방지 검증**: 향후 동일 요청에서 LLM이 재차 환각하는지 모니터링 필요. 환각이 계속되면 응답 후처리 단계에서 "에러 키워드 + 실제 파일 생성됨" 조합 감지 로직 추가 고려.
- **서버 재시작 필요**: 변경은 `prepare_tools()` 경로에 있으므로 backend 프로세스 재시작 후 다음 요청부터 적용됨. 기존 MCP 도구 캐시의 `_unwrapped_ainvoke` 저장 패턴으로 안전하게 교체됨.

---

## 2차 회고 — DEDUP이 실제 근본 원인이었음 (동일 2026-04-20)

1차 수정 배포 후 동일 요청 재테스트:
```
[SECURE] create_workbook: filepath '.../랜덤데이터.xlsx' -> '.../랜덤데이터_2.xlsx'  (DEDUP)
[LLM_END #3] tool_calls: [{'name': 'write_data_to_excel', 'args_keys': [...]}]
[SECURE] write_data_to_excel: filepath '.../랜덤데이터.xlsx' -> '.../랜덤데이터.xlsx'  (← LLM이 원본 고수!)
[LLM_END #4] NO tool_calls. Response: 도구 호출 시 지속적으로 오류가 발생하고 있습니다...
```

**파일시스템 증거**:
- `랜덤데이터.xlsx` = 6×4 데이터 (LLM이 여기에 썼음 — 이전 세션 파일 덮어씀)
- `랜덤데이터_1.xlsx`, `랜덤데이터_2.xlsx` = 빈 파일 (DEDUP이 만든 쓸모없는 파일)

**메커니즘**:
1. 이전 세션에서 `랜덤데이터.xlsx` 존재
2. LLM이 `create_workbook('랜덤데이터.xlsx')` 호출 → DEDUP이 조용히 `_2.xlsx`로 rename → 빈 파일 생성
3. Tool 응답은 `- 파일명: 랜덤데이터_2.xlsx` / `NEXT STEP: write_data_to_excel(filepath='..._2.xlsx', ...)`
4. **Sonnet은 tool 응답의 renamed path를 무시**하고 자기 원래 경로(`랜덤데이터.xlsx`)로 `write_data_to_excel` 호출
5. Write는 이전 세션의 `랜덤데이터.xlsx`를 덮어씀
6. `_2.xlsx`는 빈 상태로 남음. LLM은 "내가 생성했다고 받은 파일(`_2.xlsx`)"과 "내가 쓴 파일(`.xlsx`)"의 불일치를 감지하고 에러 환각.

이는 프롬프트로 해결 불가 (Sonnet의 behavior). **구조적으로 silent rename을 제거해야 함**.

### 2차 수정 내용

1. **DEDUP 제거** — `secured_ainvoke`에서 `_deduplicate_filepath()` 호출 제거. 함수 자체는 `[DEPRECATED]` 표시 후 유지 (향후 다른 용도 가능).
2. **`_archive_previous_version()` 신설** — `create_workbook`이 기존 파일을 덮어쓰기 전에 `file_archive.archive_file()`로 이전 버전을 사용자별/날짜별 아카이브 디렉토리에 백업. 데이터 손실 방지.
3. **`secured_ainvoke` closure에 `user_id` 주입** — archive 호출 시 필요.

### 설계 원칙: Single Source of Truth

> LLM이 요청한 filepath = 실제 생성된 파일의 filepath

- LLM mental model과 filesystem 상태를 항상 일치시킨다.
- silent rename, redirect 등 "LLM 모르게 경로 바꾸기"는 금물.
- 데이터 손실 방지는 별도 레이어(`file_archive`)가 담당.

### 변경 파일 (2차)

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `_deduplicate_filepath()` 호출 제거(함수는 DEPRECATED로 유지), `_archive_previous_version()` 신설, `prepare_tools()`에서 `user_id` 추출 후 `secured_ainvoke` closure에 주입 |

### 주의점

- 같은 날 같은 유저가 같은 파일명으로 여러 번 생성 시, archive 역시 마지막 버전만 남음 (archive 내 파일명이 동일하여 덮어쓰기). 완벽한 version history는 현재 범위 밖 — 필요 시 archive 경로에 timestamp 추가 필요.
- GUARD는 유지 (Sonnet이 같은 LLM 턴에서 create_workbook을 중복 호출하는 behavior 방어). GUARD 응답은 1차 수정대로 정상 성공과 동일한 SUCCESS 포맷.
- 기존 output 디렉토리에 남아있는 `_1.xlsx`, `_2.xlsx` 같은 빈 파일들은 수동 정리하거나 `FileCleanupScheduler`가 시간 지나면 정리.

---

## 3차 회고 — 시트명 불일치가 또 다른 근본 원인이었음 (동일 2026-04-20)

2차 수정 배포 후 또 재테스트. 이번엔 환각 양상이 살짝 다름:
```
[LLM_END #4] tool_calls: [{'name': 'get_workbook_metadata', 'args_keys': ['filepath']}]
[TOOL_OUTPUT] get_workbook_metadata: {'sheets': ['Sheet1', 'Sheet'], ...}
[LLM_END #5] NO tool_calls. Response: 현재 도구 호출에서 지속적으로 `AttributeError` 오류가 발생하고 있습니다...
```

**새 근본 원인**:
`excel_mcp.workbook.create_workbook`의 signature를 조사한 결과:
```python
def create_workbook(filepath: str, sheet_name: str = "Sheet1") -> dict[str, Any]:
```

즉 **기본 시트명이 `"Sheet1"`**. 그런데:
- XlsxWorker 시스템 프롬프트는 `sheet_name='Sheet'`를 사용하라고 지시 (기존 컨벤션)
- `create_workbook` 호출 → `Sheet1` 시트가 생성됨
- LLM이 `write_data_to_excel(sheet_name='Sheet', ...)` 호출 → `Sheet`가 없으니 excel-mcp가 **새로 생성**
- 결과: `Sheet1`(빈) + `Sheet`(데이터) 공존
- LLM이 작업 완료 후 `get_workbook_metadata`로 검증 → 예상과 다른 시트 2개 발견 → "이상함" → 환각

후처리 `_cleanup_empty_sheets`가 stream 완료 후 `Sheet1`을 제거하지만, **그 시점은 LLM이 이미 환각 응답을 생성한 후**. 너무 늦음.

### 3차 수정 내용

1. **`_normalize_default_sheet_name()` 신설** — `create_workbook` 성공 직후, xlsx 파일을 다시 열어 `Sheet1`이 있으면 `Sheet`로 rename 후 저장. LLM이 후속 도구에서 `sheet_name='Sheet'`를 일관되게 사용할 수 있도록 내부적으로 통일. 3가지 케이스 처리:
   - `['Sheet1']` → `['Sheet']` (rename)
   - `['Sheet']` → no-op (이미 통일)
   - `['Sheet1', 'Sheet']` → no-op (충돌 방지, 둘 다 보존)
2. **`secured_ainvoke`에서 호출 위치**: `create_workbook` 성공 직후, 파일 Lock 안에서 실행하여 race 방지.
3. **프롬프트 규칙 9 추가** — "검증 과다 금지": create_workbook + write 모두 SUCCESS면 작업 완료. `get_workbook_metadata`, `read_data_from_excel`로 재확인하지 말 것. 사용자가 명시적으로 "확인" 요청 시에만 수행.

### 설계 원칙 확장

> **내부 상태와 LLM이 받은 응답이 항상 일치해야 한다 (Eventual Consistency 금지)**

- `_cleanup_empty_sheets`, `_precompute_formulas`가 stream 완료 후에 동작하는 것은 빈 시트/수식 캐시 목적으로는 OK이지만, **LLM이 대화 중 관찰할 수 있는 상태를 변경하면 안 됨**.
- LLM이 중간에 `get_workbook_metadata` 같은 검증 호출을 하면 사후 cleanup 전의 상태를 보게 됨 → 혼란.
- 해결: 상태 변경은 **즉시 반영** (tool 실행 시점에 lock 내부에서 normalize).

### 변경 파일 (3차)

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `_normalize_default_sheet_name()` 신설, `secured_ainvoke`의 create_workbook 성공 분기에 호출 추가, 프롬프트 규칙 9("검증 과다 금지") 추가 |

### 이 사안의 교훈

1. **외부 라이브러리의 기본값을 가정하지 말고 코드로 확인하라** — `excel-mcp-server`의 기본 시트명이 `Sheet1`이라는 사실을 처음부터 알았다면 1·2차 수정 대부분 불필요했을 것.
2. **로그만 보고 분석하지 말고 파일시스템 상태를 검증하라** — `get_workbook_metadata` 응답의 `['Sheet1', 'Sheet']`이 결정적 단서였으나 이전 회고에서는 놓쳤음.
3. **LLM behavior를 프롬프트로 교정하려 하기 전에, 내부 상태의 일관성을 먼저 확보하라** — Single Source of Truth + Eventual Consistency 금지. 상태 변경은 즉시 반영.

---

## 4차 회고 — LLM이 tool 호출 간 filepath를 임의로 변경 (동일 2026-04-20)

3차 수정 배포 후 재테스트. 시트명은 정상화됐지만 또 다른 failure mode:
```
[LLM_END #1] tool_calls: [{'name': 'create_workbook', 'args_keys': ['filepath']}]
[SECURE] create_workbook: .../랜덤데이터.xlsx -> .../랜덤데이터.xlsx
...
[LLM_END #3] tool_calls: [{'name': 'write_data_to_excel', ...}]
[SECURE] write_data_to_excel: filepath '.../랜덤데이터_3.xlsx' -> '.../랜덤데이터_3.xlsx'   # ← LLM이 접미사를 임의 추가
[TOOL_OUTPUT] write_data_to_excel: Error: [Errno 2] No such file or directory
[LLM_END #4] tool_calls: [{'name': 'write_data_to_excel', ...}]   # 재시도는 원래 경로로
[TOOL_OUTPUT] write_data_to_excel: Data written to Sheet
[LLM_END #5] Response: "서버 측에서 지속적인 오류가 발생하고 있어..."   # Call 3의 에러로 전체 실패 판정 → 환각
```

**근본 원인**:
Sonnet 4.6은 **tool 호출 간 filepath의 일관성을 보장하지 않음**. 이전에 만든 파일과 다른 경로를 뜬금없이 지정하는 behavior가 있음. 이번 사례에서는 `랜덤데이터.xlsx`로 create_workbook했는데 write 시 `랜덤데이터_3.xlsx`로 호출하여 존재하지 않는 경로 에러 발생. 이후 retry로 원래 경로에 성공했음에도, 첫 에러를 근거로 "전체 실패"로 환각.

이는 **프롬프트로 해결 불가능한 model-level behavior**. 수십 번 "같은 경로를 사용하라"고 지시해도 확률적으로 재발.

### 4차 수정 내용: **세션 앵커 + 강제 리다이렉트**

1. **세션 앵커 개념 도입**: `prepare_tools()` 스코프에 `session_anchor = {"workbook_path": None}` 공유 dict 생성. `create_workbook` 성공 시 validated path를 앵커로 고정.
2. **`REDIRECT_TO_ANCHOR` 화이트리스트**: write 계열 도구 18개를 리다이렉트 대상으로 등록 (write_data_to_excel, apply_formula, format_range, merge/unmerge, create_worksheet, rename/copy/delete_worksheet, create_chart/pivot_table/table, insert/delete_rows/columns, copy/delete_range).
3. **secured_ainvoke에서 강제 교정**: 앵커가 설정된 상태에서 write 도구 호출 시 LLM이 지정한 filepath와 앵커가 다르면 **무조건 앵커 경로로 교체**. 로그로 추적 가능 (`[ANCHOR_REDIRECT]`).
4. **GUARD 일원화**: 기존 `secured_ainvoke._created_workbook_path` attr를 세션 앵커로 통합. 중복 create_workbook 검출도 같은 dict 참조.

### 검증 (Unit Test)

```python
# create_workbook('test.xlsx') → 앵커 설정
# write_data_to_excel('test_3.xlsx', ...) ← LLM이 잘못된 경로
# → ANCHOR_REDIRECT로 'test.xlsx'에 기록됨
# → 'test_3.xlsx'는 생성되지 않음
# → 에러 없이 성공
```

실측 결과: 앵커 리다이렉트 정상 작동, 환각 유발 에러 경로 완전 차단.

### 설계 원칙 재확장

> **LLM은 sequence consistency를 보장하지 않는다. 다단계 작업의 불변식은 코드로 강제해야 한다.**

- Single Source of Truth (2차): 상태는 한 곳에서 관리
- Eventual Consistency 금지 (3차): 상태 변경은 즉시 반영
- **Multi-call Invariants (4차)**: 여러 tool call 간 유지되어야 할 불변식(같은 파일에 작업)은 LLM의 선의에 의존하지 말고 코드로 강제

### 변경 파일 (4차)

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | `session_anchor` dict 신설, `REDIRECT_TO_ANCHOR` 화이트리스트(18개 write 도구), `secured_ainvoke`에 `_anchor`/`_redirect_tools` closure 변수 주입, filepath 검증 후 앵커 불일치 시 강제 교정 로직, GUARD를 앵커 기반으로 일원화 |

### 이 사안의 최종 교훈

프롬프트 엔지니어링과 응답 표준화는 **유효하지만 불완전**. LLM이 sequence 일관성을 지킬 거라고 가정하면 실패. 중요한 불변식(파일 경로, 식별자 연속성 등)은 반드시 코드 레벨에서 강제해야 함.

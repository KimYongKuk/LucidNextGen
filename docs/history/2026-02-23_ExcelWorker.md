# 2026-02-23 Excel(XLSX) Worker 모듈

## 개요

외부 MCP 서버 `excel-mcp-server==0.1.7`(PyPI, haris-musa, MIT)을 활용하여 Excel 파일 생성/수정 기능을 추가. LLM(Sonnet)이 자연어를 해석하여 24개의 MCP 도구를 다단계 호출하는 구조.

**지원 시나리오:**
- 사용자가 수치/데이터 전달 → 새 엑셀 생성 → 다운로드
- 엑셀 파일 업로드 → 수정 요청 → 수정본 다운로드

---

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/xlsx_worker.py` | **신규** | 핵심 워커 (Sonnet, 24 도구, 파일 Lock, Upload→Output 리다이렉트) |
| `backend/app/agents/workers/__init__.py` | 수정 | XlsxWorker 등록 |
| `backend/app/agents/workers/base_worker.py` | 수정 | `max_agent_steps` property, 루시드AI 16번 기능 |
| `backend/app/agents/state.py` | 수정 | `Intent.XLSX` + `INTENT_TO_WORKER` 매핑 + `has_session_xlsx` 필드 |
| `backend/app/agents/intent_classifier.py` | 수정 | XLSX quick_classify (2단계) + LLM 프롬프트 + `has_session_xlsx` 컨텍스트 |
| `backend/app/agents/a2a_streaming.py` | 수정 | `TOOL_STATUS_MESSAGES` + `MULTI_STEP_TOOLS` + `_has_session_xlsx()` + heartbeat 수정 |
| `backend/app/api/routes/upload.py` | 수정 | xlsx 원본 저장 + 다운로드 엔드포인트 |
| `backend/mcp_config.json` | 수정 | `excel_server` 엔트리 |
| `backend/requirements.txt` | 수정 | `excel-mcp-server==0.1.7` |
| `frontend/components/elements/response.tsx` | 수정 | `XLSXDownloadLink` + `processXLSXContent` |

---

## 1. XlsxWorker (`backend/app/agents/workers/xlsx_worker.py`)

### 클래스 구조

```
XlsxWorker(BaseWorker)
├── name = "XlsxWorker"
├── tool_names = [24개]
├── use_sonnet = True
├── max_agent_steps = 50 (= 최대 25회 도구 호출)
├── system_prompt / _base_prompt
├── build_system_prompt()        ← output_dir, available_files, 날짜, 메모리 주입
├── prepare_tools()              ← filepath 보안 검증 + asyncio.Lock (핵심!)
├── stream_response()            ← Haiku 사전 요약 (VisualizationWorker 패턴)
├── _summarize_history_if_needed()
├── _format_messages_for_summary()
└── _list_available_files()      ← 세션별 업로드 + output 디렉토리 스캔
```

### 경로 상수

```python
XLSX_UPLOAD_DIR = backend/data/xlsx_upload/   # 업로드 원본 (세션별)
XLSX_OUTPUT_DIR = backend/data/xlsx_output/   # 생성/수정 결과물
```

### 24개 도구 목록

| 카테고리 | 도구 |
|----------|------|
| Workbook | `create_workbook`, `create_worksheet`, `get_workbook_metadata` |
| Data | `read_data_from_excel`, `write_data_to_excel` |
| Formula | `apply_formula`, `validate_formula_syntax` |
| Format | `format_range`, `merge_cells`, `unmerge_cells`, `get_merged_cells` |
| Chart | `create_chart` |
| Pivot | `create_pivot_table` |
| Table | `create_table` |
| Sheet mgmt | `copy_worksheet`, `delete_worksheet`, `rename_worksheet` |
| Row/Col | `insert_rows`, `insert_columns`, `delete_sheet_rows`, `delete_sheet_columns` |
| Range | `copy_range`, `delete_range`, `validate_excel_range`, `get_data_validation_info` |

### `prepare_tools()` — 3가지 보안/안정성 메커니즘

#### (A) filepath 검증 (`_validate_filepath`)
- `..` 포함 경로 차단
- 절대경로 → `allowed_dirs` (upload/output) 내인지 확인
- 상대경로/파일명만 → `XLSX_OUTPUT_DIR` 기준으로 해석
- 허용 디렉토리: `[XLSX_OUTPUT_DIR, XLSX_UPLOAD_DIR/{session_id}]`

#### (B) 파일별 asyncio.Lock (`_file_locks` + `_get_file_lock`)
LangGraph의 `ToolNode`는 한 LLM 응답에서 여러 `tool_calls`를 **병렬 실행**한다. 같은 xlsx 파일에 동시에 `load_workbook`/`save`하면 ZIP 아카이브가 손상된다 ("Bad magic number for central directory").

**해결**: 파일 경로별 `asyncio.Lock`으로 동시 접근을 직렬화.

```python
_file_locks: Dict[str, asyncio.Lock] = {}  # 모듈 레벨

def _get_file_lock(filepath: str) -> asyncio.Lock:
    normalized = str(Path(filepath).resolve()).replace("\\", "/").lower()
    if normalized not in _file_locks:
        _file_locks[normalized] = asyncio.Lock()
    return _file_locks[normalized]

# secured_ainvoke 내부:
if resolved_filepath:
    lock = _get_file_lock(resolved_filepath)
    async with lock:
        result = await _original(input_data, config, **kwargs)
        return result
```

**증거 (서버 로그):**
```
[TIMING] Tool 'write_data_to_excel' started at 10184ms
[TIMING] Tool 'create_worksheet' started at 10184ms  ← 동시!
[TIMING] Tool 'create_worksheet' started at 10184ms  ← 동시!
→ "Bad magic number for central directory"
```

#### (C) 파일명 중복 방지 (`_deduplicate_filepath`)
`create_workbook` 호출 시 파일이 이미 존재하면 `_1`, `_2` 접미사를 붙여 기존 파일 보호.

```
매출보고서.xlsx (존재) → 매출보고서_1.xlsx
매출보고서_1.xlsx (존재) → 매출보고서_2.xlsx
```

### 시스템 프롬프트 핵심 규칙

| 규칙 # | 내용 |
|--------|------|
| 2 | 즉시 도구 호출 — 사전 안내 없이 바로 도구 호출. 첫 응답에서 반드시 도구 호출 |
| 6 | `write_data_to_excel`의 data = `List[List]` (Dict 금지). 첫 행은 헤더 |
| 7 | 서식(`format_range`)은 사용자가 명시적으로 요청한 경우에만 |
| 8 | 도구 호출 최소화 (단순 작성 = create_workbook + write_data 만) |
| 9 | 한 번에 하나의 도구만 호출 (파일 손상 방지, belt-and-suspenders) |
| 10 | **할루시네이션 절대 금지** — 도구 호출 없이 "적용했습니다" 등 금지. BAD/GOOD 예시 포함 |

### Haiku 사전 요약
- 임계값: 6 메시지 AND 5000 자 초과 시
- 마지막 메시지를 제외한 히스토리를 Haiku로 요약 → [요약, 현재 메시지] 2개로 압축
- VisualizationWorker와 동일 패턴

---

## 2. BaseWorker 확장

### `max_agent_steps` property 추가
```python
@property
def max_agent_steps(self) -> int:
    return AGENT_RECURSION_LIMIT  # 기본 20 = 최대 10회 도구 호출

# XlsxWorker에서 override:
@property
def max_agent_steps(self) -> int:
    return 50  # = 최대 25회 도구 호출
```

LangGraph의 `recursion_limit`은 **LLM 호출 + 도구 실행 = 2 step** 단위. 기본 20은 멀티시트 Excel에 부족 (시트당 최소 2~3 도구 호출 필요).

### 루시드AI 소개 업데이트
16번 항목 추가: `**엑셀(XLSX) 생성/수정** - 엑셀 파일 새로 생성, 기존 파일 수정, 서식 적용, 차트/피벗테이블`

---

## 3. 인텐트 분류

### state.py
- `Intent.XLSX = "xlsx"` 추가
- `INTENT_TO_WORKER`: `Intent.XLSX: "XlsxWorker"` 매핑

### intent_classifier.py

**quick_classify 정규식 (2단계):**

패턴 1 — "엑셀" 키워드 + 액션 동사 (세션 xlsx 파일 불필요):
```python
xlsx_pattern = r'(엑셀|excel|xlsx|xls|스프레드시트).{0,20}(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내)'
xlsx_pattern2 = r'(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내).{0,20}(엑셀|excel|xlsx|xls|스프레드시트)'
```

패턴 2 — 세션 xlsx 파일 존재 + 수정/서식 키워드 (엑셀 키워드 없이도 매칭):
```python
# has_session_xlsx=True일 때만 발동
xlsx_modify_keywords = r'(서식|포맷|테두리|배경색|글꼴|볼드|bold|정렬|색상|수식|formula|합계|sum|필터|filter|셀\s?병합|merge|행\s?추가|열\s?추가|행\s?삭제|열\s?삭제|데이터\s?추가|시트\s?추가|시트\s?삭제|피벗|pivot)'
```

- 워크스페이스에 파일이 있으면 모든 패턴에서 LLM에 위임
- `has_session_xlsx`는 `a2a_streaming.py`의 `_has_session_xlsx()`가 `xlsx_upload/{session_id}/` 스캔하여 결정

**LLM 분류기 프롬프트:**
- CONTEXT에 `has_session_xlsx` 추가
- PRIORITY RULE 2.5에 세션 xlsx + 수정 요청 → xlsx 규칙 추가
- EXAMPLES에 `has_session_xlsx=True` 조건부 예시 4건 추가

**On/Off:** `XLSX_WORKER_ENABLED` 환경변수 (기본: true)

---

## 4. MCP 서버 설정

### mcp_config.json
```json
"excel_server": {
  "command": "excel-mcp-server",
  "args": ["stdio"],
  "transport": "stdio",
  "description": "Excel(XLSX) 파일 생성/읽기/수정/서식/차트/피벗테이블",
  "enabled": true
}
```

**주의:** `excel-mcp-server`는 Typer CLI로 `sse`, `streamable_http`, `stdio` 3개 서브커맨드를 가짐. `args: []` (빈 배열)로 설정하면 help만 출력하고 종료 → MCP 연결 실패. **반드시 `["stdio"]` 지정.**

### requirements.txt
```
excel-mcp-server==0.1.7
```

**httpx 충돌:** `mcp-server-fetch`가 `<0.28` 요구, `excel-mcp-server`가 `>=0.28.1` 요구 → `0.28.1`로 설치 (pip warning만, 실제 동작 문제 없음)

---

## 5. 파일 업로드/다운로드

### upload.py 변경

**업로드 시 xlsx 원본 디스크 저장:**
```python
if file.filename.lower().endswith(('.xlsx', '.xls')):
    xlsx_dir = XLSX_UPLOAD_DIR / (session_id or "no_session")
    xlsx_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = xlsx_dir / file.filename
    with open(xlsx_path, "wb") as f:
        f.write(file_content)
```
- ChromaDB 처리(텍스트 추출 → RAG)는 그대로 유지
- XlsxWorker가 직접 파일을 조작하기 위해 원본 바이너리 저장 필요

**다운로드 엔드포인트:**
```
GET /api/v1/xlsx/download/{filename}
```
- `..` 차단, 파일명만 추출
- `XLSX_OUTPUT_DIR`에서 서빙
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

---

## 6. 스트리밍 UX (`a2a_streaming.py`)

### TOOL_STATUS_MESSAGES 추가
```python
"create_workbook": "📊 엑셀 파일을 생성하고 있습니다.",
"write_data_to_excel": "📊 데이터를 입력하고 있습니다.",
"read_data_from_excel": "📊 엑셀 데이터를 읽고 있습니다.",
"get_workbook_metadata": "📊 엑셀 파일 구조를 확인하고 있습니다.",
"format_range": "📊 서식을 적용하고 있습니다.",
"apply_formula": "📊 수식을 적용하고 있습니다.",
"create_chart": "📊 엑셀 차트를 생성하고 있습니다.",
"create_pivot_table": "📊 피벗테이블을 생성하고 있습니다.",
"create_table": "📊 엑셀 테이블을 생성하고 있습니다.",
```

### MULTI_STEP_TOOLS (18개)
Excel 도구는 한 요청에서 여러 번 반복 호출됨 → 매 호출마다 "취합 완료!" 표시하면 혼란스러움.

**동작:**
- 첫 호출: 일반 `TOOL_STATUS_MESSAGES` 표시
- 반복 호출: `📊 엑셀 작업 진행 중... (단계 N)` 표시
- 마지막 도구 완료 후에도 "취합 완료!" 억제 (LLM이 최종 응답 생성)

### HEARTBEAT_TOOLS
`create_workbook`, `write_data_to_excel` 추가 (장시간 실행 시 사용자 피드백)

---

## 7. 프론트엔드 (`response.tsx`)

### XLSXDownloadLink 컴포넌트
```tsx
<a href={downloadUrl} download={filename}
   className="text-green-600 dark:text-green-400 hover:underline">
  <FileDown /> {filename} 다운로드
</a>
```
- PDF(파란색), PPT(주황색)와 구분되는 **녹색** 링크

### processXLSXContent 함수
PDF/PPT와 동일 패턴:
- 패턴 1: `**파일명:** xxx.xlsx`
- 패턴 2: `**파일:** xxx.xlsx`
- 패턴 3: `xlsx_output/xxx.xlsx`
- 패턴 4: `C:\...\xlsx_output\xxx.xlsx`

경로/파일명 텍스트를 제거하고 다운로드 링크로 대체.

### 체이닝
```tsx
const { processedContent: pdfProcessed, pdfFiles } = processPDFContent(content);
const { processedContent: pptProcessed, pptFiles } = processPPTContent(pdfProcessed);
const { processedContent: markdownContent, xlsxFiles } = processXLSXContent(pptProcessed);
```

---

## 디버깅 히스토리 & 해결된 이슈

### 이슈 1: MCP 연결 실패
- **증상**: `McpError: Connection closed` 반복
- **원인**: `excel-mcp-server`는 Typer CLI → `args: []`면 help 출력 후 종료
- **해결**: `"args": ["stdio"]` 지정

### 이슈 2: 5분 이상 응답 없음 (멀티시트)
- **증상**: 첫 시트 데이터 작성 후 멈춤
- **원인**: `AGENT_RECURSION_LIMIT = 20` (10회 도구 호출) → 멀티시트에 부족
- **해결**: `BaseWorker.max_agent_steps` property 추가, XlsxWorker에서 50으로 override

### 이슈 3: Excel 파일 손상 ("Bad magic number")
- **증상**: 파일 생성 완료되지만 Excel에서 "repair" 필요, 수리 후 데이터 전부 유실
- **원인**: LangGraph `ToolNode`가 `[write_data, create_worksheet, create_worksheet]`를 **동시 실행** → xlsx(ZIP)에 동시 read/write → 아카이브 손상
- **해결**:
  1. `asyncio.Lock` per filepath (기계적 직렬화)
  2. 시스템 프롬프트 규칙 9 (LLM에 순차 호출 지시)

### 이슈 4: 파일명 중복 덮어쓰기
- **증상**: 같은 이름으로 생성하면 기존 파일 소실
- **해결**: `_deduplicate_filepath()` — `create_workbook` 시 `_1`, `_2` 접미사 자동 추가

### 이슈 5: data 형식 혼동
- **증상**: LLM이 `List[Dict]` 형식으로 전송할 가능성
- **해결**: 시스템 프롬프트에 `List[List]` 명시 + Dict 금지 경고 + 디버그 로깅

### 이슈 6: LLM 할루시네이션 (도구 호출 없이 완료 주장)
- **증상**: `[LLM_END #1] NO tool_calls. Response: 세 개의 시트 모두에 디자인 서식을 적용했습니다!` — 도구를 호출하지 않고 작업 완료를 거짓으로 주장
- **원인**: Haiku 사전 요약이 이전 대화 맥락을 압축하면서, LLM이 이미 작업이 완료된 것으로 오인
- **해결**: 시스템 프롬프트에 규칙 10(할루시네이션 금지) 추가 + 규칙 2 강화
  - 규칙 2: "첫 번째 응답에서 반드시 도구를 호출해야 합니다"
  - 규칙 10: "도구 호출 없이 '적용했습니다' 등 절대 금지, BAD/GOOD 예시 포함"

### 이슈 7: Heartbeat 무한 루프 (비-HEARTBEAT_TOOLS 완료 후)
- **증상**: `format_range` 완료 후에도 "📝 내용을 깔끔하게 정리하고 있습니다..." 스피너가 계속 표시
- **원인**: `a2a_streaming.py`에서 하트비트가 `tool_use_detected` 시 시작되지만, `on_tool_end`에서는 `HEARTBEAT_TOOLS`에 속한 도구만 중지. `format_range`는 HEARTBEAT_TOOLS에 없어서 하트비트가 영영 중지되지 않음
- **해결** (a2a_streaming.py 2곳 수정):
  1. `on_tool_end`: `if tool_name in HEARTBEAT_TOOLS` → `if heartbeat_active` (모든 도구 완료 시 중지)
  2. `on_chat_model_stream content`: 텍스트 스트리밍 시작 시 하트비트 중지 (이중 안전 장치)

### 이슈 8: 인텐트 오분류 ("이 파일 서식 적용해줘" → user_files)
- **증상**: xlsx 파일 업로드 후 "이 파일 디자인 서식 적용해줘" → UserFilesWorker 진입 → "서식 적용은 할 수 없습니다"
- **원인**: "엑셀" 키워드 없이 서식/수정 요청 → quick_classify의 xlsx 패턴 미매칭 → LLM도 파일 타입 정보 없어 user_files로 분류
- **해결** (intent_classifier.py + state.py + a2a_streaming.py):
  1. `RequestContext`에 `has_session_xlsx: bool` 필드 추가
  2. `a2a_streaming.py`에 `_has_session_xlsx()` 헬퍼 — `xlsx_upload/{session_id}/` 디렉토리 스캔
  3. `quick_classify` 패턴 2 추가: `has_session_xlsx=True` + 수정/서식 키워드 → `Intent.XLSX`
     - 키워드: 서식, 포맷, 테두리, 배경색, 글꼴, 볼드, 정렬, 색상, 수식, 합계, 필터, 셀 병합, 행/열 추가/삭제, 피벗 등
  4. `CLASSIFIER_PROMPT`에 `has_session_xlsx` 컨텍스트 + 라우팅 규칙 + 예시 추가

**분류 로직 (READ vs WRITE):**
| 요청 | 세션 xlsx | 결과 |
|------|-----------|------|
| "이 파일 서식 적용해줘" | True | **xlsx** (quick 패턴2) |
| "테두리 넣어줘" | True | **xlsx** (quick 패턴2) |
| "파일 내용 요약해줘" | True | **user_files** (LLM) |
| "엑셀 파일 만들어줘" | False | **xlsx** (quick 패턴1) |

### 이슈 8-보충: Upload → Output 리다이렉트
- **증상**: 업로드된 xlsx 파일 수정 시 원본이 변경되어 다운로드 불가
- **해결**: `_redirect_upload_to_output()` 함수 추가
  - 첫 WRITE 도구 호출 시 upload 파일을 `xlsx_output/`으로 복사
  - 이후 모든 read/write가 output 복사본을 대상으로 함
  - `READ_ONLY_TOOLS` frozenset으로 복사 불필요한 도구 구분
  - `redirected_files` dict로 per-request 캐싱

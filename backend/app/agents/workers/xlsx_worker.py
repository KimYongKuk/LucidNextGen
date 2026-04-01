"""XlsxWorker - Excel(XLSX) 파일 생성/수정 전담 Worker

담당 도구: excel-mcp-server의 24개 도구
- Workbook: create_workbook, create_worksheet, get_workbook_metadata
- Data: read_data_from_excel, write_data_to_excel
- Formula: apply_formula, validate_formula_syntax
- Format: format_range, merge_cells, unmerge_cells, get_merged_cells
- Chart: create_chart
- Pivot: create_pivot_table
- Table: create_table
- Sheet mgmt: copy_worksheet, delete_worksheet, rename_worksheet
- Row/Col: insert_rows, insert_columns, delete_sheet_rows, delete_sheet_columns
- Range: copy_range, delete_range, validate_excel_range, get_data_validation_info

Sonnet 모델 사용: 복잡한 자연어 → 다단계 Excel 도구 호출 변환 필요
"""

import asyncio
import re
import shutil
import time
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, AsyncIterator, Optional

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from .base_worker import BaseWorker

# ============================================================================
# 경로 설정
# ============================================================================
_BACKEND_DATA = Path(__file__).parent.parent.parent.parent / "data"
XLSX_UPLOAD_DIR = _BACKEND_DATA / "xlsx_upload"
XLSX_OUTPUT_DIR = _BACKEND_DATA / "xlsx_output"

# 디렉토리 자동 생성
XLSX_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
XLSX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# 파일별 asyncio Lock (LangGraph의 병렬 도구 실행으로 인한 동시 접근 방지)
# LangGraph는 한 LLM 응답에서 여러 tool_calls를 반환하면 ToolNode가 이를
# 병렬 실행 → 같은 xlsx 파일에 동시 load_workbook/save → ZIP 손상 발생
# ============================================================================
_file_locks: Dict[str, asyncio.Lock] = {}


def _get_file_lock(filepath: str) -> asyncio.Lock:
    """파일 경로별 asyncio.Lock 반환 (없으면 생성)"""
    # 경로 정규화하여 동일 파일에 대해 같은 Lock 보장
    normalized = str(Path(filepath).resolve()).replace("\\", "/").lower()
    if normalized not in _file_locks:
        _file_locks[normalized] = asyncio.Lock()
    return _file_locks[normalized]


# ============================================================================
# READ-ONLY 도구 목록 (파일을 수정하지 않는 도구)
# WRITE 도구가 upload 파일을 대상으로 할 때 output으로 자동 복사/리다이렉트
# ============================================================================
READ_ONLY_TOOLS = frozenset([
    "get_workbook_metadata",
    "read_data_from_excel",
    "get_merged_cells",
    "validate_excel_range",
    "get_data_validation_info",
    "validate_formula_syntax",
])

# Tool result 최대 길이 (개별 결과 안전망 — 극단적 대량 데이터 방어)
TOOL_RESULT_MAX_CHARS = 8000


class XlsxWorker(BaseWorker):
    """
    Excel(XLSX) 파일 생성/수정 Worker (Sonnet)

    Sonnet 사용 이유: 복잡한 자연어 → 다단계 Excel 도구 호출 변환 필요
    """

    @property
    def name(self) -> str:
        return "XlsxWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            # Workbook management
            "create_workbook",
            "create_worksheet",
            "get_workbook_metadata",
            # Data
            "read_data_from_excel",
            "write_data_to_excel",
            # Formula
            "apply_formula",
            "validate_formula_syntax",
            # Format
            "format_range",
            "merge_cells",
            "unmerge_cells",
            "get_merged_cells",
            # Chart
            "create_chart",
            # Pivot
            "create_pivot_table",
            # Table
            "create_table",
            # Sheet management
            "copy_worksheet",
            "delete_worksheet",
            "rename_worksheet",
            # Row/Col
            "insert_rows",
            "insert_columns",
            "delete_sheet_rows",
            "delete_sheet_columns",
            # Range
            "copy_range",
            "delete_range",
            "validate_excel_range",
            "get_data_validation_info",
            # 웹 검색 도구 (시장 데이터, 통계 등 최신 정보 필요 시)
            "tavily_search",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """Excel 작업은 다단계 도구 호출 필요 (기본 20 → 30 = 최대 15회 도구 호출)"""
        return 30

    @property
    def compact_previous_results(self) -> bool:
        """이전 단계 Tool 결과 압축 활성화 (토큰 누적 방지)"""
        return True

    @property
    def summarization_prompt(self) -> str:
        return """다음 대화 내용을 Excel 파일 생성/수정을 위해 요약해줘.

## 요약 지침
1. 핵심 데이터, 숫자, 통계는 정확히 보존
2. 주요 주제와 요청 사항 포함
3. 테이블 데이터가 있으면 구조 유지 (헤더, 행, 열)
4. 사용자의 최종 요청 명확히 기록
5. 마크다운 형식으로 정리
6. 최대 800단어

## ⚠️ 중요 - Excel 관련 정보 보존:
- 사용자가 요청한 엑셀 구조 (시트명, 열 구성, 데이터 타입)
- 서식 요청 (셀 색상, 글꼴, 테두리 등)
- 이전에 생성/수정된 파일명이 있다면 기록
- 수식/피벗테이블 요청 사항

## 대화 내용:
{conversation}

---
## 요약:"""

    @property
    def system_prompt(self) -> str:
        return self._base_prompt

    @property
    def _base_prompt(self) -> str:
        return """You are an Excel specialist. 사용자 요청에 따라 엑셀 파일을 생성/수정합니다.

## ⛔ 절대 규칙: 모든 요청에 반드시 도구를 호출하라
도구 호출 없이 "적용했습니다" / "수정했습니다" / "변경했습니다"라고 응답하면 실제로 아무 변경도 안 됩니다.
이것은 거짓말이며 사용자에게 심각한 혼란을 줍니다.

**특히 "수정해줘" / "바꿔줘" / "다시 해줘" 같은 수정 요청에 주의:**
- 이전 대화에서 파일을 이미 만들었더라도, 수정 요청에는 반드시 새 도구 호출이 필요합니다.
- 대화 요약에 이전 작업 내용이 있어도, 그것은 과거 기록일 뿐입니다. 지금 도구를 호출해야 합니다.
- 먼저 read_data_from_excel로 현재 상태를 확인하고, 필요한 도구를 호출하세요.

첫 번째 응답에서 바로 도구를 호출하세요. 사전 안내("만들겠습니다", "수정하겠습니다") 금지.

## 파일
{available_files}

## 웹 검색 (tavily_search)
- 시장 데이터, 통계, 트렌드 등 **최신 정보가 필요한 엑셀 생성 요청** 시 tavily_search로 먼저 조사
- 검색 결과의 구체적 수치/통계를 엑셀 데이터에 반영
- 사용자가 직접 데이터를 제공했거나, 기존 파일 수정인 경우에는 검색 불필요

## 새 파일 생성 워크플로우 (반드시 이 순서 준수!)
1. create_workbook → 파일 생성 (1번만 호출! 절대 반복 호출 금지)
2. write_data_to_excel → 대화에서 데이터를 추출하여 기본 시트("Sheet")에 작성
3. (선택) rename_worksheet, format_range 등 후처리
**주의**: create_workbook 후 반드시 write_data_to_excel을 호출하라. create_workbook만 반복 호출하면 빈 파일만 생성됨!
대화에서 데이터가 불명확하면, 최선의 추정으로 데이터를 구성하여 write_data_to_excel을 호출하라.

## 기존 파일 읽기 워크플로우 (반드시 이 순서!)
1. get_workbook_metadata → 시트명 목록 확인 (시트명을 추측하지 마라!)
2. read_data_from_excel(sheet_name=확인된 시트명) → 데이터 읽기
**주의**: 시트명이 "Sheet1"이라고 추측하지 마라. 반드시 get_workbook_metadata로 확인 후 사용!

## 규칙
1. **경로**: 새 파일은 `{output_dir}/파일명.xlsx`, 기존 파일은 AVAILABLE FILES의 경로 사용
2. **data 형식**: `List[List]` — 첫 행=헤더, 숫자는 따옴표 없이. Dict 형식 금지!
3. **순차 호출**: 한 번에 하나의 도구만 호출 (동시 호출 시 파일 손상)
4. **기본 시트**: create_workbook은 "Sheet" 시트를 자동 생성함. 새 시트 만들지 말고 반드시 이 기본 시트에 먼저 작업! 이름 변경은 rename_worksheet 사용
5. **파일명 안내**: 파일 생성/수정 후 반드시 "**파일명:** xxx.xlsx" 출력 (읽기/분석만 한 경우 출력 금지)
6. **서식**: 사용자가 명시적으로 요청한 경우에만 format_range 사용
7. **에러**: 도구가 "Error:"로 시작하는 결과를 2회 반환 시 사용자에게 안내. 성공 결과("Created workbook" 등)는 에러가 아님!

## 응답 형식
- 한국어 응답, JSON/data 배열 노출 금지
- 작업 내용 간략 설명 후 "**파일명:** xxx.xlsx"

Answer in Korean unless asked otherwise."""

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """컨텍스트를 반영한 시스템 프롬프트 생성"""
        prompt = self._base_prompt

        # output_dir 주입
        output_dir = str(XLSX_OUTPUT_DIR).replace("\\", "/")
        prompt = prompt.replace("{output_dir}", output_dir)

        # 세션의 업로드된 xlsx 파일 목록 탐색
        session_id = context.get("session_id", "")
        available_files_text = self._list_available_files(session_id)
        prompt = prompt.replace("{available_files}", available_files_text)

        # 세션 ID / 워크스페이스 UUID 주입
        if session_id:
            prompt = prompt.replace("{session_id}", session_id)
        workspace_uuid = context.get("workspace_uuid", "")
        if workspace_uuid:
            prompt = prompt.replace("{workspace_uuid}", workspace_uuid)

        # 날짜 정보
        from datetime import datetime
        now = datetime.now()
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        weekday_kr = weekdays[now.weekday()]
        current_date = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
        prompt = f"Today is {current_date}.\n\n{prompt}"

        # 워크스페이스 instructions
        workspace_instructions = context.get("workspace_instructions")
        if workspace_instructions:
            prompt = f"WORKSPACE INSTRUCTIONS:\n{workspace_instructions}\n\n{prompt}"

        # 메모리 컨텍스트
        if memory_context and memory_context.get("summary"):
            summary = memory_context["summary"]
            key_facts = memory_context.get("key_facts", [])
            facts_text = "\n".join(f"  - {fact}" for fact in key_facts) if key_facts else "  (없음)"
            memory_section = f"\n## 워크스페이스 메모리\n이전 대화 요약: {summary}\n핵심 사실:\n{facts_text}\n"
            prompt = prompt + memory_section

        # 전역 사용자 메모리 주입
        if user_memory_context and user_memory_context.get("key_facts"):
            facts = user_memory_context["key_facts"]
            facts_text = "\n".join(f"  - {fact}" for fact in facts)
            prompt = f"## User Profile (사용자 개인 특성)\n\n이 사용자에 대해 알려진 정보:\n{facts_text}\n\n{prompt}"

        print(f"[XlsxWorker] Context: session_id={bool(session_id)}, workspace_uuid={bool(workspace_uuid)}")

        return prompt

    def _list_available_files(self, session_id: str) -> str:
        """세션 업로드 디렉토리와 output 디렉토리에서 .xlsx 파일 목록 생성"""
        files = []

        # 1. 세션별 업로드 디렉토리
        if session_id:
            upload_dir = XLSX_UPLOAD_DIR / session_id
            if upload_dir.exists():
                for f in upload_dir.glob("*.xlsx"):
                    files.append(f"- 업로드된 파일: {str(f).replace(chr(92), '/')}")
                for f in upload_dir.glob("*.xls"):
                    files.append(f"- 업로드된 파일: {str(f).replace(chr(92), '/')}")

        # 2. 출력 디렉토리 (최근 생성 파일 10개)
        if XLSX_OUTPUT_DIR.exists():
            for f in sorted(XLSX_OUTPUT_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                files.append(f"- 생성된 파일: {str(f).replace(chr(92), '/')}")

        if not files:
            return "(현재 사용 가능한 엑셀 파일이 없습니다. 새 파일을 생성할 수 있습니다.)"

        return "\n".join(files)

    # ==========================================================
    # prepare_tools: filepath 보안 래핑 (핵심!)
    # ==========================================================

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any],
    ) -> List[BaseTool]:
        """
        모든 Excel 도구의 filepath 파라미터를 검증/샌드박싱

        허용 디렉토리:
        1. XLSX_UPLOAD_DIR/{session_id}/ (업로드된 원본 파일)
        2. XLSX_OUTPUT_DIR/ (생성/수정된 파일)

        보안:
        - ".." 경로 탐색 차단
        - 허용 디렉토리 외 접근 차단
        - 상대 경로를 XLSX_OUTPUT_DIR 기준으로 자동 해석
        """
        session_id = context.get("session_id", "")
        allowed_dirs = [str(XLSX_OUTPUT_DIR.resolve())]
        if session_id:
            upload_dir = XLSX_UPLOAD_DIR / session_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            allowed_dirs.append(str(upload_dir.resolve()))

        # Per-request: upload 파일이 output으로 복사되면 이후 모든 도구가 output 경로 사용
        redirected_files: Dict[str, str] = {}

        # 보안 래핑 대상: Excel 전용 도구만 (tavily_search 등 외부 도구는 제외)
        # MCP 도구는 전역 캐시되므로, 외부 도구를 래핑하면 다른 Worker에도 영향
        SKIP_WRAPPING = frozenset(["tavily_search"])

        for tool in tools:
            if tool.name in SKIP_WRAPPING:
                # 이전에 래핑된 경우 원복 (서버 재시작 없이도 즉시 적용)
                unwrapped = getattr(tool, "_unwrapped_ainvoke", None)
                if unwrapped:
                    object.__setattr__(tool, "ainvoke", unwrapped)
                    print(f"[XlsxWorker] [UNWRAP] {tool.name}: 이전 래핑 해제됨")
                continue

            original_ainvoke = getattr(tool, "_unwrapped_ainvoke", None) or tool.ainvoke
            object.__setattr__(tool, "_unwrapped_ainvoke", original_ainvoke)

            async def secured_ainvoke(
                input_data,
                config=None,
                *,
                _original=original_ainvoke,
                _allowed=allowed_dirs,
                _output_dir=str(XLSX_OUTPUT_DIR),
                _tname=tool.name,
                _redirected=redirected_files,
                **kwargs,
            ):
                resolved_filepath = None

                if isinstance(input_data, dict):
                    # ToolCall format: {name, args, id, type}
                    target = input_data.get("args", input_data) if "args" in input_data else input_data

                    # 디버깅: write_data_to_excel의 data 형식 확인
                    if _tname == "write_data_to_excel" and "data" in target:
                        data_val = target["data"]
                        if isinstance(data_val, list) and len(data_val) > 0:
                            first_item = data_val[0]
                            print(f"[XlsxWorker] [DEBUG] write_data data type: List[{type(first_item).__name__}], rows={len(data_val)}, first_row={first_item}")
                        else:
                            print(f"[XlsxWorker] [DEBUG] write_data data: {type(data_val).__name__}, value={str(data_val)[:200]}")

                    if "filepath" in target:
                        raw_path = target["filepath"]
                        validated = _validate_filepath(raw_path, _allowed, _output_dir)

                        # upload 파일 수정 시 output으로 자동 복사/리다이렉트
                        validated = _redirect_upload_to_output(
                            validated, _tname, _redirected, _output_dir
                        )

                        # create_workbook 시 기존 파일 덮어쓰기 방지
                        if _tname == "create_workbook":
                            validated = _deduplicate_filepath(validated)

                            # 중복 호출 가드: 이미 이 세션에서 워크북을 생성했으면 안내 반환
                            if hasattr(secured_ainvoke, "_created_workbook_path"):
                                prev = secured_ainvoke._created_workbook_path
                                msg = (
                                    f"워크북이 이미 '{Path(prev).name}'으로 생성되었습니다. "
                                    f"create_workbook을 다시 호출하지 마세요. "
                                    f"이제 write_data_to_excel(filepath='{prev}', sheet_name='Sheet', data=[[...]]) "
                                    f"를 호출하여 데이터를 입력하세요."
                                )
                                print(f"[XlsxWorker] [GUARD] create_workbook 중복 호출 차단 → 기존 파일: {Path(prev).name}")
                                return msg
                            secured_ainvoke._created_workbook_path = validated

                        target["filepath"] = validated
                        resolved_filepath = validated
                        print(f"[XlsxWorker] [SECURE] {_tname}: filepath '{raw_path}' -> '{validated}'")

                # 파일별 Lock으로 동시 접근 직렬화
                # (LangGraph ToolNode가 병렬 실행해도 같은 파일은 순차 처리)
                try:
                    if resolved_filepath:
                        lock = _get_file_lock(resolved_filepath)
                        async with lock:
                            print(f"[XlsxWorker] [LOCK] {_tname}: acquired lock for {Path(resolved_filepath).name}")
                            result = await _original(input_data, config, **kwargs)
                            print(f"[XlsxWorker] [LOCK] {_tname}: released lock for {Path(resolved_filepath).name}")
                    else:
                        result = await _original(input_data, config, **kwargs)
                except Exception as e:
                    print(f"[XlsxWorker] [ERROR] {_tname}: {type(e).__name__}: {e}")
                    raise

                # 긴 도구 결과 잘라서 토큰 폭증 방지 (Approach A)
                return _truncate_tool_result(result, _tname)

            object.__setattr__(tool, "ainvoke", secured_ainvoke)

        print(f"[XlsxWorker] 보안 래핑 완료: {len(tools)}개 도구, allowed_dirs={allowed_dirs}")

        # 아카이브 래핑 (보안 래핑 위에 적용 — Output 파일 복사)
        tools = self._wrap_tools_for_archive(tools, context)

        return tools

    # ==========================================================
    # stream_response: BaseWorker 기본 + 후처리 (빈 시트 제거, 수식 캐시)
    # Haiku 요약은 BaseWorker.stream_response()에서 자동 처리
    # ==========================================================

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: List[BaseTool],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """BaseWorker 스트리밍 + 후처리 (빈 시트 제거, 수식 캐시)"""
        async for event in super().stream_response(messages, context, all_tools, memory_context, user_memory_context):
            yield event

        # Post-processing: remove empty sheets, then pre-compute formula values
        self._cleanup_empty_sheets()
        self._precompute_formulas()

    def _cleanup_empty_sheets(self) -> None:
        """Agent 완료 후: output 디렉토리의 최근 xlsx 파일에서 빈 시트 제거

        LLM이 create_workbook 후 기본 "Sheet"를 비워두고 새 시트에 데이터를 쓰는 경우,
        다운로드된 파일에 빈 시트가 남는 문제를 해결.
        """
        try:
            import openpyxl
            # 최근 60초 이내 수정된 파일만 처리
            cutoff = time.time() - 60
            for f in XLSX_OUTPUT_DIR.glob("*.xlsx"):
                if f.stat().st_mtime < cutoff:
                    continue
                try:
                    wb = openpyxl.load_workbook(str(f))
                    if len(wb.sheetnames) <= 1:
                        wb.close()
                        continue

                    empty_sheets = []
                    for name in wb.sheetnames:
                        ws = wb[name]
                        if ws.max_row <= 1 and ws.max_column <= 1 and ws.cell(1, 1).value is None:
                            empty_sheets.append(name)

                    # 전체가 빈 경우 건드리지 않음
                    if len(empty_sheets) < len(wb.sheetnames):
                        for name in empty_sheets:
                            del wb[name]
                            print(f"[XlsxWorker] [CLEANUP] Removed empty sheet '{name}' from {f.name}")
                        if empty_sheets:
                            wb.save(str(f))

                    wb.close()
                except Exception as e:
                    print(f"[XlsxWorker] [CLEANUP] Failed to process {f.name}: {e}")
        except Exception as e:
            print(f"[XlsxWorker] [CLEANUP] Error: {e}")

    def _precompute_formulas(self) -> None:
        """Agent 완료 후: output xlsx 파일의 수식 cached value를 주입

        openpyxl(excel-mcp-server)은 수식(<f>)은 저장하지만 계산값(<v>)은
        기록하지 않음. 프리뷰 뷰어(Univer/SheetJS)가 수식을 계산하지 못하므로,
        formulas 라이브러리로 계산 후 xlsx XML에 <v> 태그를 직접 주입한다.

        수식은 그대로 보존되어 다운로드한 파일에서 Excel로 열면 수식이 유지됨.
        """
        try:
            import formulas
            import numpy as np
        except ImportError:
            print("[XlsxWorker] [FORMULA] formulas/numpy not installed, skipping")
            return

        cutoff = time.time() - 60
        for f in XLSX_OUTPUT_DIR.glob("*.xlsx"):
            if f.stat().st_mtime < cutoff:
                continue
            try:
                # 1) formulas 라이브러리로 수식 계산
                xl_model = formulas.ExcelModel().loads(str(f)).finish()
                sol = xl_model.calculate()

                # 2) solution → {(SHEET_NAME, CELL_REF): scalar_value} 매핑
                computed: Dict[tuple, Any] = {}
                for key, ranges_obj in sol.items():
                    m = re.match(r"'\[.*?\](.*?)'!(.*)", str(key))
                    if not m:
                        continue
                    sheet_name = m.group(1).upper()
                    cell_ref = m.group(2).upper()
                    if ":" in cell_ref:  # range ref 스킵
                        continue

                    val = ranges_obj.value
                    if isinstance(val, np.ndarray):
                        val = val.flat[0] if val.size > 0 else None
                    elif isinstance(val, (list, tuple)):
                        try:
                            val = val[0][0]
                        except (IndexError, TypeError):
                            val = None

                    # numpy 타입 → Python native
                    if isinstance(val, (np.integer,)):
                        val = int(val)
                    elif isinstance(val, (np.floating,)):
                        val = float(val)

                    # 수식 결과가 아닌 일반 문자열은 스킵
                    if val is not None and not isinstance(val, str):
                        computed[(sheet_name, cell_ref)] = val

                if not computed:
                    continue

                # 3) xlsx XML에 <v> 태그 주입 (수식 보존)
                injected = _inject_cached_values(str(f), computed)
                if injected > 0:
                    print(f"[XlsxWorker] [FORMULA] Injected {injected} cached values into {f.name}")
            except Exception as e:
                print(f"[XlsxWorker] [FORMULA] Skipped {f.name}: {e}")



def _truncate_tool_result(
    result,
    tool_name: str,
    max_chars: int = TOOL_RESULT_MAX_CHARS,
):
    """개별 도구 결과가 max_chars 초과 시 잘라서 토큰 폭증 방지.

    모든 타입(str, list, dict, ToolMessage 등)을 문자열로 변환 후 잘라냄.
    LLM에게 잘렸음을 안내하여 정확성 유지.

    주의: Excel 도구 전용. 외부 도구(tavily_search 등)에는 적용하지 않음.
    """
    # 방어: Excel 도구가 아닌 경우 원본 반환 (전역 캐시 래핑 누수 방지)
    if tool_name == "tavily_search":
        return result
    # 문자열로 변환
    if isinstance(result, str):
        text = result
    elif hasattr(result, "content"):
        # ToolMessage 등 content 속성이 있는 객체
        text = result.content if isinstance(result.content, str) else str(result.content)
    else:
        text = str(result)

    if len(text) <= max_chars:
        # 원래 타입이 str이 아니었으면 변환된 텍스트를 반환
        return result if isinstance(result, str) else text

    original_len = len(text)
    truncated = text[:max_chars].rstrip()

    notice = f"\n\n... ⚠️ 결과가 길어 처음 {max_chars:,}자만 표시합니다 (전체 {original_len:,}자)."
    if tool_name == "read_data_from_excel":
        notice += " 전체 데이터에 수식을 적용하려면 apply_formula를 사용하세요."

    print(f"[XlsxWorker] [TRUNCATE] {tool_name}: {original_len:,}자 → {max_chars:,}자로 잘림")
    return truncated + notice


def _deduplicate_filepath(filepath: str) -> str:
    """
    파일이 이미 존재하면 _1, _2 등 접미사를 붙여 중복 방지

    예: 매출보고서.xlsx → 매출보고서_1.xlsx → 매출보고서_2.xlsx
    """
    p = Path(filepath)
    if not p.exists():
        return filepath

    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            print(f"[XlsxWorker] [DEDUP] '{p.name}' exists → renamed to '{new_path.name}'")
            return str(new_path).replace("\\", "/")
        counter += 1


def _validate_filepath(raw_path: str, allowed_dirs: list, default_dir: str) -> str:
    """
    filepath를 검증하고 안전한 절대 경로로 변환

    Rules:
    1. ".." 포함 시 거부
    2. 절대 경로면 allowed_dirs 안에 있는지 확인
    3. 상대 경로면 default_dir (xlsx_output) 기준으로 해석
    4. 파일명만 있으면 default_dir에 배치
    """
    # .. 차단
    if ".." in raw_path:
        raise ValueError(f"Path traversal detected: {raw_path}")

    # 정규화
    normalized = raw_path.replace("\\", "/")

    # 파일명만 있는 경우 (경로 구분자 없음)
    if "/" not in normalized:
        return str(Path(default_dir) / normalized).replace("\\", "/")

    # 절대 경로 체크
    p = Path(normalized)
    if p.is_absolute():
        resolved = str(p.resolve()).replace("\\", "/")
        for allowed in allowed_dirs:
            allowed_normalized = allowed.replace("\\", "/")
            if resolved.startswith(allowed_normalized):
                return normalized
        raise ValueError(f"Path outside allowed directories: {raw_path}")

    # 상대 경로 → default_dir 기준
    full_path = Path(default_dir) / normalized
    resolved = str(full_path.resolve()).replace("\\", "/")
    for allowed in allowed_dirs:
        allowed_normalized = allowed.replace("\\", "/")
        if resolved.startswith(allowed_normalized):
            return str(full_path).replace("\\", "/")

    raise ValueError(f"Path outside allowed directories: {raw_path}")


def _redirect_upload_to_output(
    validated_path: str,
    tool_name: str,
    redirected: Dict[str, str],
    output_dir: str,
) -> str:
    """
    Upload 디렉토리의 파일에 쓰기 작업 시 자동으로 output 디렉토리로 복사/리다이렉트.

    흐름:
    1. 이미 리다이렉트된 파일 → 캐싱된 output 경로 반환 (READ/WRITE 모두)
    2. upload 파일이 아님 → 그대로 반환
    3. READ-ONLY 도구 + 아직 리다이렉트 안 됨 → 그대로 반환
    4. WRITE 도구 + upload 파일 → output으로 복사 후 output 경로 반환

    이렇게 하면:
    - 원본 upload 파일이 보존됨
    - 수정된 파일이 xlsx_output/에 위치하여 다운로드 가능
    - 첫 write 이후 모든 read/write가 output 복사본을 대상으로 함
    """
    normalized = str(Path(validated_path).resolve()).replace("\\", "/").lower()

    # 1. 이미 리다이렉트된 파일이면 캐싱된 경로 반환
    if normalized in redirected:
        redirected_path = redirected[normalized]
        print(f"[XlsxWorker] [REDIRECT] {tool_name}: reusing output copy -> {Path(redirected_path).name}")
        return redirected_path

    # 2. upload 디렉토리 파일인지 확인
    upload_dir_normalized = str(XLSX_UPLOAD_DIR.resolve()).replace("\\", "/").lower()
    if not normalized.startswith(upload_dir_normalized):
        return validated_path  # upload 파일이 아님

    # 3. READ-ONLY 도구는 아직 복사 전이면 원본 그대로 읽기
    if tool_name in READ_ONLY_TOOLS:
        return validated_path

    # 4. WRITE 작업 → upload 파일을 output으로 복사
    src_path = Path(validated_path)
    if not src_path.exists():
        return validated_path  # 파일 없으면 복사 불가

    dst_path = Path(output_dir) / src_path.name
    dst_str = str(dst_path).replace("\\", "/")

    # output에 이미 같은 이름이 있으면 덮어쓰기 (이전 요청 결과물)
    try:
        shutil.copy2(str(src_path), dst_str)
        print(f"[XlsxWorker] [REDIRECT] Copied '{src_path.name}' to xlsx_output/ for modification")
    except Exception as e:
        print(f"[XlsxWorker] [REDIRECT] Copy failed: {e}, using original path")
        return validated_path

    # 리다이렉트 기록 (이후 모든 도구 호출에서 이 경로 사용)
    redirected[normalized] = dst_str
    return dst_str


# ============================================================================
# 수식 cached value 주입 (xlsx XML 직접 수정)
# ============================================================================

_SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _inject_cached_values(filepath: str, computed: Dict[tuple, Any]) -> int:
    """xlsx XML의 수식 셀에 <v>(cached value) 태그를 주입한다.

    수식(<f>)은 그대로 보존하면서 계산된 값(<v>)만 추가하여,
    프리뷰에서 값이 표시되고 다운로드 시 수식도 유지된다.

    Returns:
        주입된 셀 수
    """
    ET.register_namespace("", _SHEET_NS)

    with zipfile.ZipFile(filepath, "r") as zin:
        all_names = {item.filename for item in zin.infolist()}

        # workbook.xml.rels에서 rId → sheet XML 경로 매핑
        rels_xml = ET.fromstring(zin.read("xl/_rels/workbook.xml.rels"))
        rid_to_target: Dict[str, str] = {}
        for rel in rels_xml:
            target = rel.get("Target", "")
            # 절대(/xl/...) vs 상대(worksheets/...) 경로 정규화
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            rid_to_target[rel.get("Id", "")] = target

        # workbook.xml에서 시트명 → rId 매핑
        wb_xml = ET.fromstring(zin.read("xl/workbook.xml"))
        sheets_el = wb_xml.find(f"{{{_SHEET_NS}}}sheets")
        if sheets_el is None:
            return 0

        sheet_xml_paths: Dict[str, str] = {}
        for s_el in sheets_el.findall(f"{{{_SHEET_NS}}}sheet"):
            rid = s_el.get(f"{{{_REL_NS}}}id", "")
            name = s_el.get("name", "").upper()
            target = rid_to_target.get(rid, "")
            if target in all_names:
                sheet_xml_paths[name] = target

        # 각 시트 XML에서 수식 셀의 <v> 태그 주입
        modified_files: Dict[str, bytes] = {}
        total_injected = 0

        for sheet_name_upper, xml_path in sheet_xml_paths.items():
            tree = ET.fromstring(zin.read(xml_path))
            sheet_data = tree.find(f"{{{_SHEET_NS}}}sheetData")
            if sheet_data is None:
                continue

            changed = False
            for row_el in sheet_data.findall(f"{{{_SHEET_NS}}}row"):
                for cell_el in row_el.findall(f"{{{_SHEET_NS}}}c"):
                    ref = cell_el.get("r", "").upper()
                    f_el = cell_el.find(f"{{{_SHEET_NS}}}f")
                    if f_el is None:
                        continue

                    key = (sheet_name_upper, ref)
                    if key not in computed:
                        continue

                    val = computed[key]
                    v_el = cell_el.find(f"{{{_SHEET_NS}}}v")
                    # <v>가 없거나 비어있으면 값 주입
                    if v_el is None:
                        v_el = ET.SubElement(cell_el, f"{{{_SHEET_NS}}}v")
                    if not v_el.text:
                        v_el.text = str(val)
                        changed = True
                        total_injected += 1

            if changed:
                modified_files[xml_path] = ET.tostring(
                    tree, xml_declaration=True, encoding="UTF-8"
                )

        if not modified_files:
            return 0

        # 수정된 시트만 교체하여 ZIP 재작성
        tmp_path = filepath + ".tmp"
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in modified_files:
                    zout.writestr(item, modified_files[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    shutil.move(tmp_path, filepath)
    return total_injected

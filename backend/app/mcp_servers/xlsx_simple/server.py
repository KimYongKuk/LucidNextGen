"""
XLSX Simple MCP Server — 엑셀 파일을 단번에 생성하는 합성 도구.

배경: excel-mcp-server의 2-step workflow(create_workbook → write_data)가
Sonnet 4.6의 multi-call 불안정성(경로 변조, 중복 호출, 짧은 응답 환각)과
결합되어 반복 실패. 단일 호출 도구로 실패 지점을 원천 차단.

도구 1개만 제공: `create_xlsx(filepath, headers, rows)`
"""

import json
from pathlib import Path
from typing import List, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from openpyxl import Workbook

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "xlsx_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

server = Server("xlsx-simple")


@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="create_xlsx",
            description=(
                "엑셀(.xlsx) 파일을 단번에 생성합니다. "
                "새 파일 생성은 **반드시 이 도구 하나만** 호출하세요. "
                "create_workbook + write_data_to_excel을 따로 호출하지 마세요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "생성할 파일 경로 (.xlsx). 파일명만 주면 xlsx_output/ 하위에 저장됨.",
                    },
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "첫 행 헤더 배열. 예: ['A', 'B', 'C', 'D']",
                    },
                    "rows": {
                        "type": "array",
                        "items": {"type": "array"},
                        "description": "데이터 행 배열. 예: [[1,2,3,4], [5,6,7,8]]",
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "시트명. 기본값 'Sheet'.",
                        "default": "Sheet",
                    },
                },
                "required": ["filepath", "headers", "rows"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    if name != "create_xlsx":
        return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]

    filepath = arguments.get("filepath", "")
    headers = arguments.get("headers", [])
    rows = arguments.get("rows", [])
    sheet_name = arguments.get("sheet_name", "Sheet")

    if not filepath:
        return [TextContent(type="text", text="Error: filepath가 필요합니다.")]
    if not isinstance(headers, list) or not headers:
        return [TextContent(type="text", text="Error: headers는 비어있지 않은 배열이어야 합니다.")]
    if not isinstance(rows, list):
        return [TextContent(type="text", text="Error: rows는 배열이어야 합니다.")]

    # 파일명만 주어지면 output 디렉토리 하위로 해석
    p = Path(filepath)
    if not p.is_absolute() and "/" not in filepath and "\\" not in filepath:
        p = OUTPUT_DIR / filepath
    if p.suffix.lower() != ".xlsx":
        p = p.with_suffix(".xlsx")

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        ws.append([str(h) for h in headers])
        for row in rows:
            if not isinstance(row, list):
                return [TextContent(type="text", text=f"Error: rows의 각 항목은 배열이어야 합니다. got: {type(row).__name__}")]
            ws.append(row)
        p.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(p))
    except Exception as e:
        return [TextContent(type="text", text=f"Error: 엑셀 생성 실패 - {type(e).__name__}: {e}")]

    msg = (
        f"✅ SUCCESS: 엑셀 파일 생성 완료\n"
        f"- 파일명: {p.name}\n"
        f"- 경로: {str(p).replace(chr(92), '/')}\n"
        f"- 시트: '{sheet_name}'\n"
        f"- 작성 범위: {len(rows) + 1}행 × {len(headers)}열 (헤더 포함)\n"
        f"작업 완료. 사용자에게 `**파일명:** {p.name}` 형태로 안내하세요."
    )
    return [TextContent(type="text", text=msg)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

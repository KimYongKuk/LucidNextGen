"""
SVG Visual Generator MCP Server
LLM이 생성한 SVG 코드를 검증하고 프론트엔드 렌더링용 데이터로 반환

용도:
- 인포그래픽 (통계, KPI, 프로세스 요약)
- 플로우차트/다이어그램
- 타임라인
- 비교 시각화
- 아키텍처/구조도

보안:
- regex 기반 정제 (XML 파서는 <style> CSS를 파괴하므로 사용하지 않음)
- script, foreignObject, on* 이벤트 핸들러, javascript: URL 차단
- 프론트엔드에서 DOMPurify로 이중 보호
"""

import json
import re

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


server = Server("svg-generator")

# SVG 최대 크기 제한 (100KB)
MAX_SVG_SIZE = 100_000


def sanitize_svg(svg_code: str) -> dict:
    """SVG 코드 검증 및 정제 (regex 기반 — XML 파서 미사용)

    XML 파서(ElementTree)는 <style> 태그 안의 CSS를 파괴하므로,
    regex로 위험 요소만 제거하고 SVG 구조는 그대로 보존한다.

    Returns:
        {"valid": True, "svg": cleaned_svg} 또는
        {"valid": False, "error": "..."}
    """
    if not svg_code or not svg_code.strip():
        return {"valid": False, "error": "SVG 코드가 비어있습니다."}

    if len(svg_code) > MAX_SVG_SIZE:
        return {"valid": False, "error": f"SVG 크기 초과 ({len(svg_code):,}자 > {MAX_SVG_SIZE:,}자 제한)"}

    # <svg> 태그 추출 (LLM이 ```svg ... ``` 래핑할 수 있음)
    svg_match = re.search(r'(<svg[\s\S]*?</svg>)', svg_code, re.IGNORECASE)
    if not svg_match:
        return {"valid": False, "error": "유효한 <svg>...</svg> 태그를 찾을 수 없습니다."}

    svg_str = svg_match.group(1)

    # === 보안 정제 (regex) ===

    # 1. <script>...</script> 제거
    svg_str = re.sub(r'<script[\s\S]*?</script>', '', svg_str, flags=re.IGNORECASE)

    # 2. <foreignObject>...</foreignObject> 제거
    svg_str = re.sub(r'<foreignObject[\s\S]*?</foreignObject>', '', svg_str, flags=re.IGNORECASE)

    # 3. on* 이벤트 핸들러 속성 제거 (onload, onclick, onerror 등)
    svg_str = re.sub(r'\s+on\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', '', svg_str, flags=re.IGNORECASE)

    # 4. javascript: URL 제거 (href, xlink:href 등에서)
    svg_str = re.sub(r'(href\s*=\s*["\'])javascript:[^"\']*(["\'])', r'\1#\2', svg_str, flags=re.IGNORECASE)

    # 5. <set>, <animate> 태그 제거 (잠재적 보안 위험)
    svg_str = re.sub(r'<set\b[^>]*/?\s*>', '', svg_str, flags=re.IGNORECASE)
    svg_str = re.sub(r'<animate\b[\s\S]*?(?:/>|</animate>)', '', svg_str, flags=re.IGNORECASE)

    # === xmlns 보장 ===
    if 'xmlns' not in svg_str.split('>')[0]:
        svg_str = svg_str.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"', 1)

    # === viewBox 보장 ===
    svg_open = svg_str[:svg_str.index('>') + 1]
    if 'viewBox' not in svg_open:
        # width/height에서 추출
        w_match = re.search(r'width\s*=\s*["\']?(\d+)', svg_open)
        h_match = re.search(r'height\s*=\s*["\']?(\d+)', svg_open)
        w = w_match.group(1) if w_match else '800'
        h = h_match.group(1) if h_match else '600'
        svg_str = svg_str.replace('<svg', f'<svg viewBox="0 0 {w} {h}"', 1)

    return {"valid": True, "svg": svg_str}


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="create_svg_visual",
            description="""Create an SVG infographic/diagram for inline display in chat.
Use for: infographics, flowcharts, timelines, comparison visuals, architecture diagrams, KPI dashboards, process summaries.
DO NOT use for standard data charts (line/bar/pie) - use chart tools instead.

The SVG should be self-contained with all styles inline.
Use modern, clean design with rounded corners, soft shadows, and professional color palettes.
Include Korean text support (font-family should include 'Malgun Gothic', sans-serif).

IMPORTANT RULES:
1. Use ONLY inline style attributes (style="...") on SVG elements. Do NOT use <style> tags or CSS classes.
2. Use <text> elements for all text — never <foreignObject> or HTML inside SVG.
3. Use emoji sparingly and only in <text> elements (they may not render in all SVG viewers).
4. Prefer simple geometric shapes: <rect>, <circle>, <line>, <path>, <polygon>, <text>.
5. All colors must be hex codes or named colors directly in fill/stroke attributes.
6. For icons, use simple geometric shapes or Unicode symbols in <text> — NOT external images.

DESIGN GUIDELINES:
- ViewBox: use 800x600 for landscape, 600x800 for portrait
- Colors: professional palette — primary #4A90D9, accent #50C878, warm #FF6B6B, bg #F8FAFC, dark #1E293B
- Typography: title 24px bold, subtitle 16px, body 14px, caption 11px
- Font: font-family="Malgun Gothic, sans-serif"
- Shapes: rounded rectangles (rx="12"), circles for icons/numbers
- Background: light gradient or solid #F8FAFC
- Shadows: use filter with feDropShadow for card effects
- Connectors: smooth cubic bezier paths for flowcharts""",
            inputSchema={
                "type": "object",
                "properties": {
                    "svg_code": {
                        "type": "string",
                        "description": "Complete SVG code string (<svg>...</svg>). Use ONLY inline styles, no <style> tags or CSS classes."
                    },
                    "title": {
                        "type": "string",
                        "description": "Visual title (displayed above the SVG in UI)"
                    },
                    "visual_type": {
                        "type": "string",
                        "enum": ["infographic", "flowchart", "timeline", "comparison", "diagram", "dashboard", "process"],
                        "description": "Type of visual for UI hints"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the visual shows (for accessibility)"
                    }
                },
                "required": ["svg_code", "title", "visual_type"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "create_svg_visual":
        svg_code = arguments.get("svg_code", "")
        title = arguments.get("title", "")
        visual_type = arguments.get("visual_type", "infographic")
        description = arguments.get("description", "")

        # SVG 검증 및 정제
        result = sanitize_svg(svg_code)

        if not result["valid"]:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": result["error"]
                }, ensure_ascii=False)
            )]

        # 프론트엔드 렌더링용 데이터 반환
        response = {
            "success": True,
            "type": "svg_visual",
            "title": title,
            "visual_type": visual_type,
            "description": description,
            "svg": result["svg"],
        }

        return [TextContent(
            type="text",
            text=json.dumps(response, ensure_ascii=False)
        )]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

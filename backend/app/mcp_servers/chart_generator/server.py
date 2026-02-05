"""
Chart Generator MCP Server
차트 데이터 생성 + 파일 저장 이중 모드 지원

모드:
- display (기본): 프론트엔드 렌더링용 데이터 반환
- file: matplotlib으로 PNG 파일 저장 (다운로드/PDF 삽입용)
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 차트 생성 (파일 모드용)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

# 현재 디렉토리
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "chart_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# MCP 서버 생성
server = Server("chart-generator")


def setup_korean_font():
    """한글 폰트 설정"""
    windows_fonts = Path("C:/Windows/Fonts")
    malgun = windows_fonts / "malgun.ttf"
    if malgun.exists():
        plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False


setup_korean_font()


def sanitize_filename(filename: str) -> str:
    """파일명 정리"""
    return re.sub(r'[<>:"/\\|?*`\'"\s]', '', filename).strip()


def validate_data(data: List[Dict[str, Any]], required_columns: List[str]) -> Dict[str, Any]:
    """데이터 유효성 검증"""
    if not data:
        return {"valid": False, "error": "데이터가 비어있습니다."}

    first_row = data[0]
    missing = [col for col in required_columns if col not in first_row]

    if missing:
        available = list(first_row.keys())
        return {
            "valid": False,
            "error": f"필수 컬럼 누락: {missing}. 사용 가능한 컬럼: {available}"
        }

    return {"valid": True}


# ============================================================
# Display Mode (프론트엔드 렌더링용)
# ============================================================

def create_display_line_chart(data, x_column, y_columns, title):
    return {
        "success": True,
        "type": "chart_data",
        "chart_type": "line",
        "title": title,
        "data": data,
        "config": {
            "xKey": x_column,
            "yKeys": y_columns,
            "colors": ["#4A90D9", "#50C878", "#FF6B6B", "#FFD93D", "#9B59B6", "#1ABC9C"]
        }
    }


def create_display_bar_chart(data, x_column, y_column, title, horizontal):
    return {
        "success": True,
        "type": "chart_data",
        "chart_type": "bar",
        "title": title,
        "data": data,
        "config": {
            "xKey": x_column,
            "yKey": y_column,
            "horizontal": horizontal,
            "colors": ["#4A90D9"]
        }
    }


def create_display_pie_chart(data, labels_column, values_column, title):
    pie_data = [
        {"name": row[labels_column], "value": row[values_column]}
        for row in data
    ]
    return {
        "success": True,
        "type": "chart_data",
        "chart_type": "pie",
        "title": title,
        "data": pie_data,
        "config": {
            "colors": ["#4A90D9", "#50C878", "#FF6B6B", "#FFD93D", "#9B59B6",
                       "#1ABC9C", "#E74C3C", "#3498DB", "#F39C12", "#2ECC71"]
        }
    }


def create_display_multi_chart(data, chart_type, config, title):
    x_column = config.get("x_column")

    if chart_type == "combo":
        return {
            "success": True,
            "type": "chart_data",
            "chart_type": "combo",
            "title": title,
            "data": data,
            "config": {
                "xKey": x_column,
                "barKeys": config.get("bar_columns", []),
                "lineKeys": config.get("line_columns", []),
                "barColors": ["#4A90D9", "#50C878", "#FFD93D"],
                "lineColors": ["#E74C3C", "#9B59B6", "#1ABC9C"]
            }
        }
    elif chart_type == "stacked_bar":
        return {
            "success": True,
            "type": "chart_data",
            "chart_type": "stacked_bar",
            "title": title,
            "data": data,
            "config": {
                "xKey": x_column,
                "stackKeys": config.get("stack_columns", []),
                "colors": ["#4A90D9", "#50C878", "#FF6B6B", "#FFD93D", "#9B59B6"]
            }
        }
    elif chart_type == "area":
        return {
            "success": True,
            "type": "chart_data",
            "chart_type": "area",
            "title": title,
            "data": data,
            "config": {
                "xKey": x_column,
                "areaKeys": config.get("area_columns", []),
                "colors": ["#4A90D9", "#50C878", "#FF6B6B", "#FFD93D"]
            }
        }
    else:
        return {"success": False, "error": f"지원하지 않는 차트 타입: {chart_type}"}


# ============================================================
# File Mode (PNG 파일 저장용)
# ============================================================

def create_file_line_chart(data, x_column, y_columns, title, filename):
    try:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10, 6))

        colors = ['#4A90D9', '#50C878', '#FF6B6B', '#FFD93D', '#9B59B6', '#1ABC9C']
        for idx, col in enumerate(y_columns):
            if col in df.columns:
                ax.plot(df[x_column], df[col], marker='o', linewidth=2,
                       markersize=6, label=col, color=colors[idx % len(colors)])

        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel(x_column, fontsize=11)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()
        safe_filename = sanitize_filename(filename)
        output_path = OUTPUT_DIR / f"{safe_filename}.png"
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        return {
            "success": True,
            "type": "chart_file",
            "file_path": str(output_path),
            "message": f"라인 차트가 저장되었습니다: {output_path.name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file_bar_chart(data, x_column, y_column, title, filename, horizontal):
    try:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10, 6))

        n_bars = len(df)
        colors = plt.cm.Blues([(i + 3) / (n_bars + 4) for i in range(n_bars)])

        if horizontal:
            bars = ax.barh(df[x_column], df[y_column], color=colors)
            ax.set_xlabel(y_column, fontsize=11)
            for bar, val in zip(bars, df[y_column]):
                ax.text(val + max(df[y_column]) * 0.01, bar.get_y() + bar.get_height()/2,
                       f'{val:,.0f}', va='center', fontsize=9)
        else:
            bars = ax.bar(df[x_column], df[y_column], color=colors)
            ax.set_xlabel(x_column, fontsize=11)
            for bar, val in zip(bars, df[y_column]):
                ax.text(bar.get_x() + bar.get_width()/2, val + max(df[y_column]) * 0.01,
                       f'{val:,.0f}', ha='center', fontsize=9)

        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.grid(True, alpha=0.3, axis='y' if not horizontal else 'x', linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()
        safe_filename = sanitize_filename(filename)
        output_path = OUTPUT_DIR / f"{safe_filename}.png"
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        return {
            "success": True,
            "type": "chart_file",
            "file_path": str(output_path),
            "message": f"막대 차트가 저장되었습니다: {output_path.name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file_pie_chart(data, labels_column, values_column, title, filename):
    try:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10, 8))

        colors = ['#4A90D9', '#50C878', '#FF6B6B', '#FFD93D', '#9B59B6',
                  '#1ABC9C', '#E74C3C', '#3498DB', '#F39C12', '#2ECC71']

        values = df[values_column].tolist()
        max_idx = values.index(max(values))
        explode = [0.05 if i == max_idx else 0 for i in range(len(values))]

        wedges, texts, autotexts = ax.pie(
            df[values_column], labels=df[labels_column], autopct='%1.1f%%',
            colors=colors[:len(df)], explode=explode, shadow=True, startangle=90
        )

        for text in texts:
            text.set_fontsize(11)
        for autotext in autotexts:
            autotext.set_fontsize(10)
            autotext.set_fontweight('bold')

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        safe_filename = sanitize_filename(filename)
        output_path = OUTPUT_DIR / f"{safe_filename}.png"
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        return {
            "success": True,
            "type": "chart_file",
            "file_path": str(output_path),
            "message": f"파이 차트가 저장되었습니다: {output_path.name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file_multi_chart(data, chart_type, config, title, filename):
    try:
        df = pd.DataFrame(data)
        x_column = config.get('x_column', df.columns[0])

        fig, ax1 = plt.subplots(figsize=(12, 6))

        if chart_type == "combo":
            bar_columns = config.get('bar_columns', [])
            line_columns = config.get('line_columns', [])

            x = range(len(df))
            width = 0.35
            colors_bar = ['#4A90D9', '#50C878', '#FFD93D']

            for idx, col in enumerate(bar_columns):
                if col in df.columns:
                    offset = width * (idx - len(bar_columns)/2 + 0.5)
                    ax1.bar([i + offset for i in x], df[col], width,
                           label=col, color=colors_bar[idx % len(colors_bar)])

            ax1.set_xlabel(x_column, fontsize=11)
            ax1.set_xticks(x)
            ax1.set_xticklabels(df[x_column])

            if line_columns:
                ax2 = ax1.twinx()
                colors_line = ['#E74C3C', '#9B59B6', '#1ABC9C']

                for idx, col in enumerate(line_columns):
                    if col in df.columns:
                        ax2.plot(x, df[col], marker='o', linewidth=2,
                                label=col, color=colors_line[idx % len(colors_line)])

                lines1, labels1 = ax1.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
            else:
                ax1.legend(loc='upper left')

        elif chart_type == "stacked_bar":
            stack_columns = config.get('stack_columns', [])
            colors = ['#4A90D9', '#50C878', '#FF6B6B', '#FFD93D', '#9B59B6']

            bottom = None
            for idx, col in enumerate(stack_columns):
                if col in df.columns:
                    ax1.bar(df[x_column], df[col], bottom=bottom,
                           label=col, color=colors[idx % len(colors)])
                    bottom = df[col] if bottom is None else bottom + df[col]

            ax1.legend(loc='upper left')

        elif chart_type == "area":
            area_columns = config.get('area_columns', [])
            colors = ['#4A90D9', '#50C878', '#FF6B6B', '#FFD93D']

            for idx, col in enumerate(area_columns):
                if col in df.columns:
                    ax1.fill_between(df[x_column], df[col], alpha=0.5,
                                    label=col, color=colors[idx % len(colors)])
                    ax1.plot(df[x_column], df[col], linewidth=2, color=colors[idx % len(colors)])

            ax1.legend(loc='upper left')

        ax1.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax1.grid(True, alpha=0.3, linestyle='--')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        plt.tight_layout()
        safe_filename = sanitize_filename(filename)
        output_path = OUTPUT_DIR / f"{safe_filename}.png"
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        return {
            "success": True,
            "type": "chart_file",
            "file_path": str(output_path),
            "message": f"복합 차트가 저장되었습니다: {output_path.name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# MCP Tools
# ============================================================

@server.list_tools()
async def list_tools():
    """사용 가능한 도구 목록"""
    return [
        Tool(
            name="create_line_chart",
            description="""라인/트렌드 차트를 생성합니다.

출력 모드:
- display (기본): 채팅에 인터랙티브 차트로 바로 표시
- file: PNG 파일로 저장 (다운로드/PDF 삽입용)

용도: 시간에 따른 변화 추이, 트렌드 비교
예시: 월별 매출 추이, 연도별 성장률""",
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "차트 데이터. 예: [{\"month\": \"1월\", \"sales\": 100}, ...]"
                    },
                    "x_column": {"type": "string", "description": "X축 컬럼명"},
                    "y_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Y축 컬럼명 목록 (복수 라인 지원)"
                    },
                    "title": {"type": "string", "description": "차트 제목"},
                    "output_mode": {
                        "type": "string",
                        "enum": ["display", "file"],
                        "default": "display",
                        "description": "출력 모드: display(화면표시), file(파일저장)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "파일명 (output_mode=file일 때만 필요)"
                    }
                },
                "required": ["data", "x_column", "y_columns", "title"]
            }
        ),
        Tool(
            name="create_bar_chart",
            description="""막대 차트를 생성합니다.

출력 모드:
- display (기본): 채팅에 인터랙티브 차트로 바로 표시
- file: PNG 파일로 저장

용도: 카테고리별 비교, 순위 시각화
예시: 부서별 인원, 제품별 매출""",
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "차트 데이터. 예: [{\"dept\": \"영업\", \"count\": 50}, ...]"
                    },
                    "x_column": {"type": "string", "description": "X축(카테고리) 컬럼명"},
                    "y_column": {"type": "string", "description": "Y축(값) 컬럼명"},
                    "title": {"type": "string", "description": "차트 제목"},
                    "horizontal": {
                        "type": "boolean",
                        "default": False,
                        "description": "가로 막대 차트 여부"
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["display", "file"],
                        "default": "display"
                    },
                    "filename": {"type": "string", "description": "파일명 (file 모드용)"}
                },
                "required": ["data", "x_column", "y_column", "title"]
            }
        ),
        Tool(
            name="create_pie_chart",
            description="""파이 차트를 생성합니다.

출력 모드:
- display (기본): 채팅에 인터랙티브 차트로 바로 표시
- file: PNG 파일로 저장

용도: 비율/점유율, 구성 비율
예시: 시장 점유율, 비용 구성""",
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "차트 데이터. 예: [{\"category\": \"A\", \"value\": 30}, ...]"
                    },
                    "labels_column": {"type": "string", "description": "레이블 컬럼명"},
                    "values_column": {"type": "string", "description": "값 컬럼명"},
                    "title": {"type": "string", "description": "차트 제목"},
                    "output_mode": {
                        "type": "string",
                        "enum": ["display", "file"],
                        "default": "display"
                    },
                    "filename": {"type": "string", "description": "파일명 (file 모드용)"}
                },
                "required": ["data", "labels_column", "values_column", "title"]
            }
        ),
        Tool(
            name="create_multi_chart",
            description="""복합 차트를 생성합니다.

타입:
- combo: 막대 + 라인 (이중 Y축)
- stacked_bar: 누적 막대
- area: 영역 차트

출력 모드:
- display (기본): 채팅에 인터랙티브 차트로 바로 표시
- file: PNG 파일로 저장""",
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "차트 데이터"
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["combo", "stacked_bar", "area"]
                    },
                    "config": {
                        "type": "object",
                        "description": "차트 설정. combo: {x_column, bar_columns, line_columns}"
                    },
                    "title": {"type": "string", "description": "차트 제목"},
                    "output_mode": {
                        "type": "string",
                        "enum": ["display", "file"],
                        "default": "display"
                    },
                    "filename": {"type": "string", "description": "파일명 (file 모드용)"}
                },
                "required": ["data", "chart_type", "config", "title"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """도구 실행"""
    output_mode = arguments.get("output_mode", "display")
    filename = arguments.get("filename", "chart")

    if name == "create_line_chart":
        data = arguments.get("data", [])
        x_column = arguments.get("x_column", "")
        y_columns = arguments.get("y_columns", [])
        title = arguments.get("title", "라인 차트")

        validation = validate_data(data, [x_column] + y_columns)
        if not validation["valid"]:
            return [TextContent(type="text", text=f"오류: {validation['error']}")]

        if output_mode == "file":
            result = create_file_line_chart(data, x_column, y_columns, title, filename)
        else:
            result = create_display_line_chart(data, x_column, y_columns, title)

    elif name == "create_bar_chart":
        data = arguments.get("data", [])
        x_column = arguments.get("x_column", "")
        y_column = arguments.get("y_column", "")
        title = arguments.get("title", "막대 차트")
        horizontal = arguments.get("horizontal", False)

        validation = validate_data(data, [x_column, y_column])
        if not validation["valid"]:
            return [TextContent(type="text", text=f"오류: {validation['error']}")]

        if output_mode == "file":
            result = create_file_bar_chart(data, x_column, y_column, title, filename, horizontal)
        else:
            result = create_display_bar_chart(data, x_column, y_column, title, horizontal)

    elif name == "create_pie_chart":
        data = arguments.get("data", [])
        labels_column = arguments.get("labels_column", "")
        values_column = arguments.get("values_column", "")
        title = arguments.get("title", "파이 차트")

        validation = validate_data(data, [labels_column, values_column])
        if not validation["valid"]:
            return [TextContent(type="text", text=f"오류: {validation['error']}")]

        if output_mode == "file":
            result = create_file_pie_chart(data, labels_column, values_column, title, filename)
        else:
            result = create_display_pie_chart(data, labels_column, values_column, title)

    elif name == "create_multi_chart":
        data = arguments.get("data", [])
        chart_type = arguments.get("chart_type", "combo")
        config = arguments.get("config", {})
        title = arguments.get("title", "복합 차트")

        x_column = config.get("x_column")
        if not x_column:
            return [TextContent(type="text", text="오류: config에 x_column이 필요합니다.")]

        if output_mode == "file":
            result = create_file_multi_chart(data, chart_type, config, title, filename)
        else:
            result = create_display_multi_chart(data, chart_type, config, title)

    else:
        return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]

    # 결과 반환
    if result.get("success"):
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    else:
        return [TextContent(type="text", text=f"차트 생성 실패: {result.get('error')}")]


async def main():
    """MCP 서버 실행"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
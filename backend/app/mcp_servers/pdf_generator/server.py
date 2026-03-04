"""
PDF Generator MCP Server
fpdf2 기반 마크다운/텍스트 → PDF 변환 서버
Windows 환경에서 추가 의존성 없이 동작
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import tempfile

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# PDF 생성
from fpdf import FPDF
from fpdf.fonts import FontFace
from fpdf.enums import XPos, YPos, TableCellFillMode, Align
import markdown
from markdown.extensions.tables import TableExtension

# 현재 디렉토리
CURRENT_DIR = Path(__file__).parent
TEMPLATES_DIR = CURRENT_DIR / "templates"
FONTS_DIR = CURRENT_DIR / "fonts"
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "pdf_output"

# 출력 디렉토리 생성
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)

# MCP 서버 생성
server = Server("pdf-generator")


class KoreanPDF(FPDF):
    """한글 지원 PDF 클래스"""

    def __init__(self, style: str = "technical"):
        super().__init__()
        self.style = style
        self.setup_fonts()
        self.setup_style()

    def setup_fonts(self):
        """폰트 설정 - Windows 시스템 폰트 사용"""
        # Windows 폰트 경로
        windows_fonts = Path("C:/Windows/Fonts")

        # 맑은 고딕 폰트 추가
        malgun_regular = windows_fonts / "malgun.ttf"
        malgun_bold = windows_fonts / "malgunbd.ttf"

        if malgun_regular.exists():
            self.add_font("MalgunGothic", "", str(malgun_regular))
            if malgun_bold.exists():
                self.add_font("MalgunGothic", "B", str(malgun_bold))
            else:
                self.add_font("MalgunGothic", "B", str(malgun_regular))
            self.default_font = "MalgunGothic"
        else:
            # 폴백: 나눔고딕 또는 기본 폰트
            nanum = windows_fonts / "NanumGothic.ttf"
            if nanum.exists():
                self.add_font("NanumGothic", "", str(nanum))
                self.default_font = "NanumGothic"
            else:
                self.default_font = "Helvetica"

        # 코드용 고정폭 폰트 (나눔고딕코딩 우선, 한글 지원)
        nanum_coding = windows_fonts / "NanumGothicCoding.ttf"
        nanum_coding_bold = windows_fonts / "NanumGothicCoding-Bold.ttf"

        if nanum_coding.exists():
            self.add_font("NanumGothicCoding", "", str(nanum_coding))
            if nanum_coding_bold.exists():
                self.add_font("NanumGothicCoding", "B", str(nanum_coding_bold))
            else:
                self.add_font("NanumGothicCoding", "B", str(nanum_coding))
            self.code_font = "NanumGothicCoding"
        else:
            # 폴백: Consolas (한글 미지원) → 맑은 고딕 (한글 지원, 비고정폭)
            consolas = windows_fonts / "consola.ttf"
            if consolas.exists():
                self.add_font("Consolas", "", str(consolas))
                # 한글이 포함된 코드 블록은 맑은 고딕 사용
                self.code_font = self.default_font
                self._consolas_available = True
            else:
                self.code_font = self.default_font
                self._consolas_available = False

    def setup_style(self):
        """스타일 설정"""
        if self.style == "technical":
            self.colors = {
                "title": (26, 54, 93),      # 진한 파란색
                "h2": (43, 108, 176),       # 파란색
                "h3": (43, 108, 176),       # 파란색
                "text": (51, 51, 51),       # 진한 회색
                "table_header": (74, 85, 104),  # 헤더 배경 (어두운 색)
                "table_header_text": (255, 255, 255),  # 헤더 텍스트 (흰색)
                "table_row_even": (247, 250, 252),  # 짝수 행
                "table_border": (226, 232, 240),    # 테두리
                "code_bg": (26, 32, 44),    # 코드 배경
                "code_text": (226, 232, 240),  # 코드 텍스트
            }
        elif self.style == "report":
            self.colors = {
                "title": (26, 26, 26),
                "h2": (51, 51, 51),
                "h3": (68, 68, 68),
                "text": (34, 34, 34),
                "table_header": (245, 245, 245),  # 헤더 배경 (밝은 색)
                "table_header_text": (34, 34, 34),  # 헤더 텍스트 (어두운 색)
                "table_row_even": (250, 250, 250),
                "table_border": (204, 204, 204),
                "code_bg": (248, 248, 248),
                "code_text": (51, 51, 51),
            }
        else:  # simple
            self.colors = {
                "title": (51, 51, 51),
                "h2": (68, 68, 68),
                "h3": (85, 85, 85),
                "text": (51, 51, 51),
                "table_header": (245, 245, 245),  # 헤더 배경 (밝은 색)
                "table_header_text": (51, 51, 51),  # 헤더 텍스트 (어두운 색)
                "table_row_even": (250, 250, 250),
                "table_border": (221, 221, 221),
                "code_bg": (245, 245, 245),
                "code_text": (51, 51, 51),
            }

    def header(self):
        """페이지 헤더"""
        pass

    def footer(self):
        """페이지 푸터 - 페이지 번호"""
        self.set_y(-15)
        self.set_font(self.default_font, "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"{self.page_no()}", align="C")


def strip_markdown_formatting(text: str) -> str:
    """인라인 마크다운 포맷팅 제거 (**bold**, *italic*, etc.)"""
    # **bold** → bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # *italic* → italic
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # __bold__ → bold
    text = re.sub(r'__(.+?)__', r'\1', text)
    # _italic_ → italic
    text = re.sub(r'_(.+?)_', r'\1', text)
    # `code` → code
    text = re.sub(r'`(.+?)`', r'\1', text)
    # [link](url) → link
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text


def inline_markdown_for_pdf(text: str) -> str:
    """인라인 마크다운을 fpdf2 multi_cell(markdown=True)용으로 변환

    fpdf2 markdown mode 지원:
    - **bold** → 굵게
    - *italic* → 기울임
    - __underlined__ → 밑줄

    지원하지 않는 형식은 텍스트만 유지:
    - `code` → code
    - [link](url) → link
    """
    # `code` → code (backticks 제거)
    text = re.sub(r'`(.+?)`', r'\1', text)
    # [link](url) → link (텍스트만 유지)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text


def _is_list_line(line: str) -> bool:
    """줄이 리스트 항목인지 확인 (bullet 또는 numbered)"""
    stripped = line.strip()
    return bool(re.match(r'^[-*+]\s+', stripped) or re.match(r'^\d+\.\s+', stripped))


def _has_consecutive_numbered(lines: List[str], idx: int) -> bool:
    """idx 위치에서 시작하여 2개 이상 연속된 번호 리스트가 있는지 확인"""
    for j in range(idx + 1, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            continue  # 빈 줄 건너뜀
        return bool(re.match(r'^\d+\.\s+', stripped))
    return False


def _collect_list_items(lines: List[str], start_idx: int) -> tuple:
    """연속된 리스트 항목 수집. (items, next_index) 반환."""
    items = []
    i = start_idx

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            # 빈 줄: 다음에 리스트가 계속되는지 확인
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _is_list_line(lines[j]):
                i = j
                continue
            break

        # 불릿 항목 (-, *, +)
        ul_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if ul_match:
            indent = len(ul_match.group(1))
            depth = indent // 2
            items.append({'text': ul_match.group(2).strip(), 'depth': depth, 'ordered': False})
            i += 1
            continue

        # 번호 항목 (1. 2. etc)
        ol_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        if ol_match:
            indent = len(ol_match.group(1))
            depth = indent // 2
            items.append({'text': ol_match.group(2).strip(), 'depth': depth, 'ordered': True})
            i += 1
            continue

        break  # 리스트가 아닌 줄

    return items, i


def parse_markdown_content(content: str) -> List[Dict[str, Any]]:
    """마크다운 컨텐츠를 구조화된 요소로 파싱

    지원 요소:
    - 제목 (#, ##, ###, ####)
    - 불릿 리스트 (-, *, +) 및 번호 리스트 (1. 2. 3.)
    - 중첩 리스트 (들여쓰기 기반)
    - **굵게**, *기울임* 인라인 서식 (paragraph/list에서)
    - 블록인용 (>)
    - 테이블, 코드블록, 이미지, 구분선
    - 섹션 번호 (1-1. 2-3. 등) → 자동 제목 스타일
    """
    elements = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 빈 줄
        if not stripped:
            i += 1
            continue

        # 이미지 (![alt](path) 또는 ![alt](path "caption"))
        img_match = re.match(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', stripped)
        if img_match:
            alt_text = img_match.group(1)
            img_path = img_match.group(2)
            caption = img_match.group(3) if img_match.group(3) else alt_text
            elements.append({'type': 'image', 'path': img_path, 'alt': alt_text, 'caption': caption})
            i += 1
            continue

        # 제목 (# ## ### ####)
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            text = strip_markdown_formatting(stripped.lstrip('#').strip())
            elements.append({'type': 'heading', 'level': level, 'text': text})
            i += 1
            continue

        # 코드 블록
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            elements.append({'type': 'code', 'lang': lang, 'text': '\n'.join(code_lines)})
            i += 1
            continue

        # 테이블
        if '|' in stripped and i + 1 < len(lines) and '---' in lines[i + 1]:
            table_lines = [stripped]
            i += 1
            while i < len(lines) and '|' in lines[i]:
                table_lines.append(lines[i].strip())
                i += 1
            elements.append({'type': 'table', 'lines': table_lines})
            continue

        # 구분선
        if stripped in ['---', '***', '___']:
            elements.append({'type': 'hr'})
            i += 1
            continue

        # 블록인용 (>)
        if stripped.startswith('>'):
            quote_lines = []
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith('>'):
                    # > 프리픽스 제거
                    text = re.sub(r'^>\s?', '', s)
                    quote_lines.append(text)
                    i += 1
                elif not s:
                    # 빈 줄: 다음 줄이 인용이면 계속
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith('>'):
                        quote_lines.append('')
                        i += 1
                    else:
                        break
                else:
                    break
            combined = '\n'.join(quote_lines)
            elements.append({'type': 'blockquote', 'text': combined})
            continue

        # 불릿 리스트 (-, *, +)
        bullet_match = re.match(r'^(\s*)[-*+]\s+', line)
        if bullet_match:
            items, i = _collect_list_items(lines, i)
            if items:
                elements.append({'type': 'list', 'ordered': False, 'items': items})
            continue

        # 서브 섹션 제목 (1-1. 2-3-1. 등) — 항상 제목으로 처리
        sub_section_match = re.match(r'^(\d+-\d+(?:-\d+)*)\.\s+(.+)$', stripped)
        if sub_section_match:
            section_num = sub_section_match.group(1)
            text = strip_markdown_formatting(stripped)
            if section_num.count('-') == 1:
                level = 3
            else:
                level = 4
            elements.append({'type': 'heading', 'level': level, 'text': text})
            i += 1
            continue

        # 번호 패턴 (1. 2. 등) — 연속이면 리스트, 단독이면 섹션 제목
        num_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_match:
            if _has_consecutive_numbered(lines, i):
                # 연속 번호 → 번호 리스트
                items, i = _collect_list_items(lines, i)
                if items:
                    elements.append({'type': 'list', 'ordered': True, 'items': items})
                continue
            else:
                # 단독 번호 → 섹션 제목 (기존 동작 유지)
                text = strip_markdown_formatting(stripped)
                elements.append({'type': 'heading', 'level': 2, 'text': text})
                i += 1
                continue

        # 일반 텍스트 (여러 줄 수집, 인라인 서식 보존)
        text_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if (not next_line or
                next_line.startswith('#') or
                next_line.startswith('```') or
                next_line.startswith('>') or
                next_line in ['---', '***', '___'] or
                re.match(r'^[-*+]\s+', next_line) or
                re.match(r'^\d+(?:-\d+)*\.\s+', next_line) or
                re.match(r'^!\[', next_line) or
                ('|' in next_line and i + 1 < len(lines) and '---' in lines[i + 1])):
                break
            text_lines.append(next_line)
            i += 1
        # 인라인 서식 보존 (bold, italic은 유지, backtick/link만 변환)
        combined_text = inline_markdown_for_pdf(' '.join(text_lines))
        elements.append({'type': 'paragraph', 'text': combined_text})

    return elements


def parse_table(table_lines: List[str]) -> Dict[str, Any]:
    """테이블 파싱"""
    rows = []
    for line in table_lines:
        # 구분선 스킵
        if '---' in line and '|' in line:
            continue
        cells = [strip_markdown_formatting(cell.strip()) for cell in line.split('|')]
        # 앞뒤 빈 셀 제거
        if cells and not cells[0]:
            cells = cells[1:]
        if cells and not cells[-1]:
            cells = cells[:-1]
        if cells:
            rows.append(cells)

    if len(rows) >= 1:
        return {'headers': rows[0], 'data': rows[1:] if len(rows) > 1 else []}
    return {'headers': [], 'data': []}


def render_pdf(elements: List[Dict[str, Any]], title: str, style: str = "technical", section_per_page: bool = True) -> KoreanPDF:
    """구조화된 요소를 PDF로 렌더링

    Args:
        elements: 파싱된 마크다운 요소 목록
        title: 문서 제목
        style: PDF 스타일 (technical, report, simple)
        section_per_page: True면 주요 섹션(h2)마다 새 페이지에서 시작
    """
    pdf = KoreanPDF(style=style)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    # 섹션 페이지 나누기를 위한 상태 추적
    h1_rendered = False  # h1(제목)이 렌더링되었는지
    first_h2_after_h1 = True  # h1 직후 첫 번째 h2인지

    for elem in elements:
        elem_type = elem['type']

        if elem_type == 'heading':
            level = elem['level']
            text = elem['text']

            if level == 1:
                pdf.set_font(pdf.default_font, "B", 20)
                pdf.set_text_color(*pdf.colors['title'])
                pdf.ln(5)
                pdf.multi_cell(0, 10, text, align="C")
                pdf.ln(3)
                # 밑줄
                pdf.set_draw_color(*pdf.colors['h2'])
                pdf.set_line_width(0.8)
                pdf.line(15, pdf.get_y(), 195, pdf.get_y())
                pdf.ln(8)
                h1_rendered = True

            elif level == 2:
                # 섹션별 페이지 나누기: h1 직후 첫 번째 h2는 같은 페이지, 이후 h2는 새 페이지
                if section_per_page and h1_rendered:
                    if first_h2_after_h1:
                        first_h2_after_h1 = False
                        pdf.ln(6)  # 첫 번째 h2는 같은 페이지이므로 상단 여백 유지
                    else:
                        pdf.add_page()
                        # 새 페이지에서는 약간의 상단 여백만 추가
                        pdf.ln(3)
                else:
                    pdf.ln(6)  # section_per_page=False일 때 기존 여백 유지

                pdf.set_font(pdf.default_font, "B", 14)
                pdf.set_text_color(*pdf.colors['h2'])
                pdf.multi_cell(0, 8, text)
                # 밑줄
                pdf.set_draw_color(*pdf.colors['h2'])
                pdf.set_line_width(0.5)
                pdf.line(15, pdf.get_y() + 1, 195, pdf.get_y() + 1)
                pdf.ln(5)

            elif level == 3:
                pdf.ln(4)
                pdf.set_font(pdf.default_font, "B", 12)
                pdf.set_text_color(*pdf.colors['h3'])
                pdf.multi_cell(0, 7, text)
                pdf.ln(3)

            else:
                pdf.ln(3)
                pdf.set_font(pdf.default_font, "B", 11)
                pdf.set_text_color(*pdf.colors['text'])
                pdf.multi_cell(0, 6, text)
                pdf.ln(2)

        elif elem_type == 'paragraph':
            pdf.set_font(pdf.default_font, "", 10)
            pdf.set_text_color(*pdf.colors['text'])
            pdf.multi_cell(0, 6, elem['text'], markdown=True)
            pdf.ln(3)

        elif elem_type == 'list':
            render_list(pdf, elem['items'], elem['ordered'])

        elif elem_type == 'blockquote':
            render_blockquote(pdf, elem['text'])

        elif elem_type == 'table':
            table = parse_table(elem['lines'])
            if table['headers']:
                render_table(pdf, table)
            pdf.ln(3)

        elif elem_type == 'code':
            render_code_block(pdf, elem['text'], elem.get('lang', ''))
            pdf.ln(3)

        elif elem_type == 'hr':
            pdf.ln(3)
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.3)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(5)

        elif elem_type == 'image':
            render_image(pdf, elem['path'], elem.get('caption', ''))
            pdf.ln(3)

    return pdf


def calculate_col_widths(headers: List[str], data: List[List[str]], max_total: float = 180) -> List[float]:
    """컬럼 너비를 내용 기반으로 계산"""
    num_cols = len(headers)
    if num_cols == 0:
        return []

    # 각 열의 최대 문자 길이 계산
    max_lengths = []
    for col_idx in range(num_cols):
        # 헤더 길이
        max_len = len(headers[col_idx]) if col_idx < len(headers) else 0
        # 데이터 최대 길이
        for row in data:
            if col_idx < len(row):
                max_len = max(max_len, len(str(row[col_idx])))
        max_lengths.append(max_len)

    # 총 문자 길이
    total_chars = sum(max_lengths) or 1

    # 비율 기반 너비 계산 (최소 20mm, 최대 80mm)
    col_widths = []
    for length in max_lengths:
        width = (length / total_chars) * max_total
        width = max(20, min(80, width))  # 최소 20, 최대 80
        col_widths.append(width)

    # 전체 너비 조정
    total_width = sum(col_widths)
    if total_width > max_total:
        ratio = max_total / total_width
        col_widths = [w * ratio for w in col_widths]

    return col_widths


def render_table(pdf: KoreanPDF, table: Dict[str, Any]):
    """테이블 렌더링"""
    headers = table['headers']
    data = table['data']

    if not headers:
        return

    num_cols = len(headers)

    # 동적 열 너비 계산
    col_widths = calculate_col_widths(headers, data)

    # 페이지 체크
    if pdf.get_y() > 250:
        pdf.add_page()

    # 헤더 행
    pdf.set_font(pdf.default_font, "B", 9)
    pdf.set_fill_color(*pdf.colors['table_header'])
    pdf.set_text_color(*pdf.colors['table_header_text'])
    pdf.set_draw_color(*pdf.colors['table_border'])

    for col_idx, header in enumerate(headers):
        col_width = col_widths[col_idx] if col_idx < len(col_widths) else 30
        # 너비에 맞게 텍스트 잘라내기 (글자당 약 2.5mm)
        max_chars = int(col_width / 2.5)
        display_text = header[:max_chars] if len(header) > max_chars else header
        pdf.cell(col_width, 8, display_text, border=1, fill=True, align="C")
    pdf.ln()

    # 데이터 행
    pdf.set_font(pdf.default_font, "", 9)
    pdf.set_text_color(*pdf.colors['text'])

    for row_idx, row in enumerate(data):
        # 짝수 행 배경색
        if row_idx % 2 == 0:
            pdf.set_fill_color(*pdf.colors['table_row_even'])
            fill = True
        else:
            fill = False

        # 페이지 넘침 체크
        if pdf.get_y() > 270:
            pdf.add_page()
            # 헤더 다시 그리기
            pdf.set_font(pdf.default_font, "B", 9)
            pdf.set_fill_color(*pdf.colors['table_header'])
            pdf.set_text_color(*pdf.colors['table_header_text'])
            for col_idx, header in enumerate(headers):
                col_width = col_widths[col_idx] if col_idx < len(col_widths) else 30
                max_chars = int(col_width / 2.5)
                display_text = header[:max_chars] if len(header) > max_chars else header
                pdf.cell(col_width, 8, display_text, border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font(pdf.default_font, "", 9)
            pdf.set_text_color(*pdf.colors['text'])

        for col_idx, cell in enumerate(row):
            if col_idx < num_cols:
                col_width = col_widths[col_idx] if col_idx < len(col_widths) else 30
                # 첫 번째 열은 가운데 정렬
                align = "C" if col_idx == 0 else "L"
                # 너비에 맞게 텍스트 잘라내기
                max_chars = int(col_width / 2.5)
                cell_text = str(cell)
                display_text = cell_text[:max_chars] if len(cell_text) > max_chars else cell_text
                pdf.cell(col_width, 7, display_text, border=1, fill=fill, align=align)

        # 부족한 셀 채우기
        for missing_idx in range(num_cols - len(row)):
            col_idx = len(row) + missing_idx
            col_width = col_widths[col_idx] if col_idx < len(col_widths) else 30
            pdf.cell(col_width, 7, "", border=1, fill=fill)
        pdf.ln()

    # 테이블 종료 후 텍스트 색상 리셋 (흰색 방지)
    pdf.set_text_color(*pdf.colors['text'])
    pdf.set_font(pdf.default_font, "", 10)


def render_code_block(pdf: KoreanPDF, code: str, lang: str = ""):
    """코드 블록 렌더링"""
    # 페이지 체크
    if pdf.get_y() > 240:
        pdf.add_page()

    # 배경
    start_y = pdf.get_y()
    pdf.set_fill_color(*pdf.colors['code_bg'])
    pdf.set_text_color(*pdf.colors['code_text'])
    pdf.set_font(pdf.code_font, "", 8)

    # 코드 라인
    lines = code.split('\n')
    line_height = 4.5

    # 배경 박스 그리기
    total_height = len(lines) * line_height + 8
    pdf.rect(15, start_y, 180, total_height, style='F')

    pdf.set_xy(18, start_y + 3)

    for line in lines:
        pdf.set_x(18)
        # 긴 라인 자르기
        if len(line) > 95:
            line = line[:92] + "..."
        pdf.cell(0, line_height, line)
        pdf.ln(line_height)

    pdf.ln(3)

    # 코드 블록 종료 후 텍스트 색상/폰트 리셋 (흰색 방지)
    pdf.set_text_color(*pdf.colors['text'])
    pdf.set_font(pdf.default_font, "", 10)


def render_list(pdf: KoreanPDF, items: List[Dict[str, Any]], ordered: bool):
    """리스트 렌더링 (불릿/번호, 중첩 지원)"""
    if pdf.get_y() > 260:
        pdf.add_page()

    pdf.set_font(pdf.default_font, "", 10)
    pdf.set_text_color(*pdf.colors['text'])

    # depth별 순번 카운터 (번호 리스트용)
    counters: Dict[int, int] = {}

    for item in items:
        depth = item.get('depth', 0)
        is_ordered = item.get('ordered', ordered)
        text = inline_markdown_for_pdf(item['text'])

        # 들여쓰기 계산
        base_indent = 20
        indent = base_indent + depth * 7

        # 프리픽스 생성
        if is_ordered:
            counters.setdefault(depth, 0)
            counters[depth] += 1
            # 하위 depth 카운터 리셋
            for d in list(counters.keys()):
                if d > depth:
                    del counters[d]
            prefix = f"{counters[depth]}.  "
        else:
            bullets = ['\u2022', '-', '\u00B7']  # •, -, ·
            bullet_char = bullets[min(depth, len(bullets) - 1)]
            prefix = f"{bullet_char}  "

        # 프리픽스 렌더
        pdf.set_font(pdf.default_font, "", 10)
        pdf.set_x(indent)
        prefix_width = pdf.get_string_width(prefix) + 1
        pdf.cell(prefix_width, 6, prefix)

        # 텍스트 렌더 (markdown=True로 **bold**, *italic* 지원)
        text_x = indent + prefix_width
        old_margin = pdf.l_margin
        pdf.set_left_margin(text_x)
        pdf.multi_cell(0, 6, text, markdown=True)
        pdf.set_left_margin(old_margin)

        # 페이지 넘침 체크
        if pdf.get_y() > 270:
            pdf.add_page()
            pdf.set_font(pdf.default_font, "", 10)
            pdf.set_text_color(*pdf.colors['text'])

    pdf.ln(2)
    # 폰트 상태 리셋
    pdf.set_font(pdf.default_font, "", 10)


def render_blockquote(pdf: KoreanPDF, text: str):
    """블록인용 렌더링 (왼쪽 세로선 + 배경)"""
    if pdf.get_y() > 250:
        pdf.add_page()

    start_y = pdf.get_y()

    # 배경색 + 들여쓰기
    quote_indent = 22
    pdf.set_fill_color(245, 247, 250)
    pdf.set_font(pdf.default_font, "", 10)
    pdf.set_text_color(85, 85, 85)

    old_margin = pdf.l_margin
    pdf.set_left_margin(quote_indent)
    pdf.set_x(quote_indent)

    processed_text = inline_markdown_for_pdf(text)
    pdf.multi_cell(170, 6, processed_text, markdown=True, fill=True)

    pdf.set_left_margin(old_margin)

    end_y = pdf.get_y()

    # 왼쪽 세로선
    pdf.set_draw_color(*pdf.colors['h2'])
    pdf.set_line_width(1.0)
    pdf.line(19, start_y, 19, end_y)

    # 리셋
    pdf.set_text_color(*pdf.colors['text'])
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.ln(3)


def find_chart_image(img_path: str) -> Optional[Path]:
    """차트 이미지 파일 찾기 - 여러 경로 시도"""
    img_file = Path(img_path)
    filename = Path(img_path).name

    # 1. 절대 경로인 경우 그대로 사용
    if img_file.is_absolute() and img_file.exists():
        return img_file

    # 2. 가능한 chart_output 경로들 (절대 경로 우선)
    possible_bases = [
        # 절대 경로 (가장 확실)
        Path(r"C:\Users\Administrator\Documents\LFChatbot_NextJS_FastAPI\backend\data\chart_output"),
        # __file__ 기준 (mcp_servers/pdf_generator/server.py)
        Path(__file__).parent.parent.parent.parent / "data" / "chart_output",
        # 현재 작업 디렉토리 기준
        Path.cwd() / "data" / "chart_output",
        Path.cwd() / "backend" / "data" / "chart_output",
    ]

    # 각 경로에서 파일 찾기
    for base_dir in possible_bases:
        # 전체 경로로 시도
        full_path = base_dir / img_path
        if full_path.exists():
            print(f"[PDF] Found image at: {full_path}")
            return full_path

        # 파일명만으로 시도
        name_path = base_dir / filename
        if name_path.exists():
            print(f"[PDF] Found image at: {name_path}")
            return name_path

    # 디버그: 시도한 경로들 출력
    print(f"[PDF] Image not found: {img_path}")
    print(f"[PDF] Tried paths:")
    for base_dir in possible_bases:
        print(f"  - {base_dir / filename} (exists: {(base_dir / filename).exists()})")

    return None


def render_image(pdf: KoreanPDF, img_path: str, caption: str = ""):
    """이미지 렌더링 (차트 등)"""
    # 이미지 파일 찾기
    img_file = find_chart_image(img_path)

    if img_file is None:
        # 이미지를 찾을 수 없으면 텍스트로 표시
        pdf.set_font(pdf.default_font, "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, f"[이미지를 찾을 수 없음: {img_path}]", align="C")
        pdf.ln(5)
        pdf.set_text_color(*pdf.colors['text'])
        return

    # 페이지 체크 - 이미지를 위한 충분한 공간 확보
    if pdf.get_y() > 180:
        pdf.add_page()

    try:
        # 이미지 크기 계산 (최대 너비 160mm, 최대 높이 100mm)
        max_width = 160
        max_height = 100

        # 이미지를 중앙 정렬로 삽입
        x_pos = (210 - max_width) / 2  # A4 너비 210mm 기준 중앙

        pdf.image(str(img_file), x=x_pos, w=max_width)

        # 캡션 추가
        if caption:
            pdf.ln(2)
            pdf.set_font(pdf.default_font, "", 9)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, caption, align="C")
            pdf.set_text_color(*pdf.colors['text'])

        pdf.ln(5)

    except Exception as e:
        # 이미지 삽입 실패 시 오류 표시
        pdf.set_font(pdf.default_font, "", 9)
        pdf.set_text_color(200, 100, 100)
        pdf.cell(0, 8, f"[이미지 삽입 실패: {str(e)}]", align="C")
        pdf.ln(5)
        pdf.set_text_color(*pdf.colors['text'])


@server.list_tools()
async def list_tools():
    """사용 가능한 도구 목록"""
    return [
        Tool(
            name="create_document_pdf",
            description="""마크다운/텍스트 문서를 PDF로 변환합니다.

기능:
- 마크다운 문법 지원 (제목 #, 표, 코드블록 ```, 구분선 ---)
- **굵게**, *기울임* 인라인 서식 지원
- 불릿 리스트 (-, *, +) 및 번호 리스트 (1. 2. 3.) 지원 (중첩 가능)
- 블록인용 (>) 지원
- 섹션 번호 자동 인식 (1-1. 2-3. 형태 → 자동 제목 스타일)
- 한글 완벽 지원 (맑은 고딕)
- 테이블 자동 스타일링 (헤더 색상, 줄무늬)
- 코드블록 구문 하이라이팅 스타일

스타일 옵션:
- technical: 기술 문서용 (파란색 헤더, 깔끔한 표) - 기본값
- report: 보고서용 (공식적인 회색톤)
- simple: 심플한 스타일""",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "변환할 마크다운/텍스트 내용"
                    },
                    "title": {
                        "type": "string",
                        "description": "문서 제목"
                    },
                    "filename": {
                        "type": "string",
                        "description": "출력 파일명 (확장자 제외)"
                    },
                    "style": {
                        "type": "string",
                        "enum": ["technical", "report", "simple"],
                        "default": "technical",
                        "description": "PDF 스타일 템플릿"
                    },
                    "section_per_page": {
                        "type": "boolean",
                        "default": False,
                        "description": "True면 주요 섹션(##)마다 새 페이지에서 시작 (섹션 헤더가 페이지 상단에 배치됨). 기본값 False (연속 배치)"
                    }
                },
                "required": ["content", "title", "filename"]
            }
        ),
        Tool(
            name="create_table_spec_pdf",
            description="""데이터베이스 테이블 정의서 전용 PDF 생성.

자동으로 다음을 감지하고 포맷팅:
- 테이블 정의 (컬럼명, 타입, 제약조건)
- DDL SQL 코드
- 인덱스/제약조건 정보
- ER 다이어그램 (텍스트)

technical 스타일이 자동 적용됩니다.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "테이블 정의서 내용"
                    },
                    "title": {
                        "type": "string",
                        "description": "문서 제목 (예: 베어 라인 테이블 정의서)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "출력 파일명 (확장자 제외)"
                    },
                    "version": {
                        "type": "string",
                        "default": "1.0",
                        "description": "문서 버전"
                    },
                    "section_per_page": {
                        "type": "boolean",
                        "default": False,
                        "description": "True면 주요 섹션(##)마다 새 페이지에서 시작 (섹션 헤더가 페이지 상단에 배치됨). 기본값 False (연속 배치)"
                    }
                },
                "required": ["content", "title", "filename"]
            }
        ),
        Tool(
            name="list_generated_pdfs",
            description="생성된 PDF 파일 목록을 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """도구 실행"""

    if name == "create_document_pdf":
        content = arguments.get("content", "")
        title = arguments.get("title", "문서")
        filename = arguments.get("filename", "output")
        style = arguments.get("style", "technical")
        section_per_page = arguments.get("section_per_page", False)

        try:
            # 파일명 정리
            safe_filename = re.sub(r'[<>:"/\\|?*`\'"\s]', '', filename).strip()
            output_path = OUTPUT_DIR / f"{safe_filename}.pdf"

            # 제목 추가 (content가 이미 # 제목으로 시작하면 추가하지 않음)
            content_stripped = content.strip()
            if content_stripped.startswith('# '):
                full_content = content
            else:
                full_content = f"# {title}\n\n{content}"

            # 파싱 및 렌더링
            elements = parse_markdown_content(full_content)
            pdf = render_pdf(elements, title, style, section_per_page)

            # 저장
            pdf.output(str(output_path))

            file_size = output_path.stat().st_size / 1024

            # 섹션 페이지 나누기 안내 추가
            section_hint = ""
            if not section_per_page:
                section_hint = "\n\n[참고] 섹션별로 페이지를 나눠서 다시 생성하려면 section_per_page=true 옵션을 사용하세요."

            return [TextContent(
                type="text",
                text=f"PDF 생성 완료\n\n파일: {output_path}\n스타일: {style}\n제목: {title}\n크기: {file_size:.1f} KB{section_hint}"
            )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"PDF 생성 실패: {str(e)}"
            )]

    elif name == "create_table_spec_pdf":
        content = arguments.get("content", "")
        title = arguments.get("title", "테이블 정의서")
        filename = arguments.get("filename", "table_spec")
        version = arguments.get("version", "1.0")
        section_per_page = arguments.get("section_per_page", False)

        try:
            # 버전 정보 (마크다운 포맷 제거)
            version_header = f"버전: {version} | 작성일: {datetime.now().strftime('%Y-%m-%d')}\n\n---\n\n"

            # 제목 추가 (content가 이미 # 제목으로 시작하면 추가하지 않음)
            content_stripped = content.strip()
            if content_stripped.startswith('# '):
                full_content = f"{version_header}{content}"
            else:
                full_content = f"# {title}\n\n{version_header}{content}"

            # 파일명 정리
            safe_filename = re.sub(r'[<>:"/\\|?*`\'"\s]', '', filename).strip()
            output_path = OUTPUT_DIR / f"{safe_filename}.pdf"

            # 파싱 및 렌더링 (technical 스타일)
            elements = parse_markdown_content(full_content)
            pdf = render_pdf(elements, title, "technical", section_per_page)

            # 저장
            pdf.output(str(output_path))

            file_size = output_path.stat().st_size / 1024

            # 섹션 페이지 나누기 안내 추가
            section_hint = ""
            if not section_per_page:
                section_hint = "\n\n[참고] 섹션별로 페이지를 나눠서 다시 생성하려면 section_per_page=true 옵션을 사용하세요."

            return [TextContent(
                type="text",
                text=f"테이블 정의서 PDF 생성 완료\n\n파일: {output_path}\n버전: {version}\n제목: {title}\n크기: {file_size:.1f} KB{section_hint}"
            )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"PDF 생성 실패: {str(e)}"
            )]

    elif name == "list_generated_pdfs":
        try:
            pdf_files = list(OUTPUT_DIR.glob("*.pdf"))

            if not pdf_files:
                return [TextContent(
                    type="text",
                    text="생성된 PDF 파일이 없습니다."
                )]

            file_list = []
            for pdf in sorted(pdf_files, key=lambda x: x.stat().st_mtime, reverse=True):
                stat = pdf.stat()
                size_kb = stat.st_size / 1024
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                file_list.append(f"- {pdf.name} ({size_kb:.1f} KB) - {mtime}")

            return [TextContent(
                type="text",
                text=f"생성된 PDF 목록 ({len(pdf_files)}개)\n\n" + "\n".join(file_list)
            )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"목록 조회 실패: {str(e)}"
            )]

    return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


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

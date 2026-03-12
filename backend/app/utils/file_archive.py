"""
파일 아카이브 유틸리티
- MCP 도구가 생성한 Output 파일을 날짜/사용자별 아카이브 디렉토리에 복사
- 원본 파일은 그대로 유지 (LLM 참조 + 다운로드 엔드포인트 변경 없음)
- 아카이브: data/file_archive/{YYYY-MM-DD}/{user_id}/{파일타입}/{파일명}
"""

import shutil
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 아카이브 기준 디렉토리
BASE_DIR = Path(__file__).parent.parent.parent
ARCHIVE_DIR = BASE_DIR / "data" / "file_archive"

# Output 디렉토리 → 파일 타입 매핑
OUTPUT_DIR_MAP = {
    "pdf_output": "pdf",
    "ppt_output": "ppt",
    "chart_output": "chart",
    "xlsx_output": "xlsx",
}


def archive_file(
    file_path: str,
    user_id: str,
    file_type: Optional[str] = None,
) -> Optional[str]:
    """
    생성된 파일을 아카이브 디렉토리에 복사

    Args:
        file_path: 원본 파일 경로 (MCP가 생성한 파일)
        user_id: 사용자 ID (사번)
        file_type: 파일 타입 (pdf, ppt, chart, xlsx). None이면 경로에서 자동 감지

    Returns:
        아카이브 경로 (성공 시) 또는 None (실패 시)
    """
    try:
        src = Path(file_path)
        if not src.exists():
            return None

        # 파일 타입 자동 감지 (output 디렉토리명 기반)
        if not file_type:
            for dir_name, ftype in OUTPUT_DIR_MAP.items():
                if dir_name in str(src):
                    file_type = ftype
                    break
            if not file_type:
                file_type = src.suffix.lstrip(".") or "etc"

        today = datetime.now().strftime("%Y-%m-%d")
        safe_user_id = re.sub(r'[/\\. ]', '_', user_id) if user_id else "unknown"

        dest_dir = ARCHIVE_DIR / today / safe_user_id / file_type
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / src.name
        shutil.copy2(str(src), str(dest))

        logger.info(f"[Archive] {src.name} -> {dest_dir.relative_to(BASE_DIR)}/{src.name} (user={user_id})")
        return str(dest)

    except Exception as e:
        logger.warning(f"[Archive] Failed to archive {file_path}: {e}")
        return None


def extract_output_filepath(tool_result_text: str) -> Optional[str]:
    """
    MCP 도구 결과 텍스트에서 output 파일 경로를 추출

    MCP 도구 결과 형식 예:
    - "PDF 생성 완료\\n\\n파일: C:\\...\\pdf_output\\report.pdf"
    - "PPT 생성 완료 ... 파일 경로: C:\\...\\ppt_output\\slides.pptx"
    - "파일 경로: /path/to/xlsx_output/data.xlsx"
    """
    # 패턴: output 디렉토리 포함 경로 추출
    patterns = [
        r'[A-Za-z]:\\[^\n]*?(?:pdf_output|ppt_output|chart_output|xlsx_output)[/\\][^\n\s]+',
        r'/[^\n]*?(?:pdf_output|ppt_output|chart_output|xlsx_output)/[^\n\s]+',
    ]
    for pattern in patterns:
        match = re.search(pattern, tool_result_text)
        if match:
            return match.group(0).rstrip('.')
    return None
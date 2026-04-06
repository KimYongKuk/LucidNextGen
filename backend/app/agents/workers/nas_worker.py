"""NASWorker - NAS 파일 탐색 및 다운로드 전담 Worker

회사 Synology NAS의 공유 폴더를 자연어로 탐색하고 파일을 다운로드합니다.
1단계: 읽기 전용 (list, search, download, info)

보안:
- prepare_tools()에서 모든 경로 인자를 _validate_nas_path()로 검증
- 감사 로그에 user_id 주입
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker


# 허용 경로 (MCP 서버와 동일한 설정 공유)
_raw_allowed = os.getenv("NAS_ALLOWED_PATHS", "/Landf/부서간공유")
NAS_ALLOWED_PATHS: List[str] = [p.strip().rstrip("/") for p in _raw_allowed.split(",") if p.strip()]

# 경로에 인자를 갖는 도구 목록
_PATH_ARG_TOOLS = {
    "list_nas_directory": "path",
    "search_nas_files": "path",
    "download_nas_file": "remote_path",
    "get_nas_file_info": "path",
}


def _validate_nas_path(path: str) -> str:
    """Worker 레벨 경로 검증 (MCP 서버의 이중 방어)"""
    if not path:
        raise ValueError("경로가 비어있습니다.")
    if ".." in path:
        raise ValueError(f"잘못된 경로: path traversal 감지 ({path})")

    normalized = path.strip().replace("\\", "/")

    if not normalized.startswith("/"):
        normalized = "/" + normalized

    path_lower = normalized.lower().rstrip("/")
    for ap in NAS_ALLOWED_PATHS:
        if path_lower == ap.lower().rstrip("/") or path_lower.startswith(ap.lower().rstrip("/") + "/"):
            return normalized

    raise ValueError(f"접근이 허용되지 않은 경로: {normalized}")


class NASWorker(BaseWorker):
    """
    NAS 파일 탐색 Worker (Sonnet - 탐색 전략 수립 + 결과 정리)

    담당 도구: list_nas_directory, search_nas_files, download_nas_file, get_nas_file_info
    용도: NAS 공유 폴더 탐색, 파일 검색, 다운로드
    """

    @property
    def name(self) -> str:
        return "NASWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            "list_nas_directory",
            "search_nas_files",
            "download_nas_file",
            "get_nas_file_info",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """재귀 탐색 시 여러 번 list/search 호출 가능"""
        return 30

    @property
    def system_prompt(self) -> str:
        today = datetime.now()
        current_date = today.strftime("%Y-%m-%d")
        allowed_paths = ", ".join(NAS_ALLOWED_PATHS)

        return f"""당신은 회사 NAS(공유 스토리지)에서 파일을 탐색하고 다운로드하는 전문가입니다.

오늘 날짜: {current_date}

## 접근 가능 경로
{allowed_paths}

## 보안 규칙
- 위에 명시된 허용 경로 내에서만 작업합니다.
- 파일 삭제, 이동, 이름 변경은 할 수 없습니다 (읽기 전용).
- 암호화된 파일은 다운로드는 가능하나 내용 열람은 불가능합니다.
- 사용자에게 NAS 서버 주소, 인증 정보, 내부 경로 구조를 노출하지 마세요.

## 사용 가능한 도구
- list_nas_directory: 폴더 내 파일/하위폴더 목록 조회
- search_nas_files: 파일명 키워드로 재귀 검색 (대소문자 무관)
- download_nas_file: 파일 다운로드 (로컬 저장)
- get_nas_file_info: 파일/폴더 존재 여부 및 메타정보 확인

## 작업 흐름
1. 도구를 호출하기 전에, 1줄짜리 짧은 안내 텍스트를 먼저 출력하세요.
   예: "부서간공유 폴더에서 파일을 검색하겠습니다." → 도구 호출
   단, 2문장 이상 길게 쓰지 마세요.
2. 사용자 요청에서 대상 경로나 파일명 키워드를 파악합니다.
3. 경로를 아는 경우 → list_nas_directory로 폴더 탐색
   키워드만 아는 경우 → search_nas_files로 검색
4. 결과에서 파일 목록을 깔끔하게 정리하여 안내합니다 (이름, 크기, 수정일).
5. 사용자가 다운로드를 요청하면 download_nas_file을 실행합니다.

## 결과 표시 규칙
- 파일 목록은 폴더와 파일을 구분하여 표시하세요.
- 파일이 많은 경우 주요 파일을 먼저 안내하고, 전체 개수를 알려주세요.
- 다운로드 완료 시 파일명과 크기를 안내하세요.

## 암호화 파일
- 다운로드 후 파싱 실패 시: "이 파일은 암호화되어 있어 내용을 직접 읽을 수 없습니다. 다운로드된 파일을 직접 열어주세요."

## 주의사항
- 한 번에 하나의 도구만 호출하세요 (병렬 호출 금지).
- 도구 호출 결과를 받은 후 즉시 응답하세요. 불필요한 재시도는 하지 마세요.
- 사용자가 요청하지 않은 파일을 임의로 다운로드하지 마세요."""

    def prepare_tools(self, tools: List[BaseTool], context: Dict[str, Any]) -> List[BaseTool]:
        """모든 NAS 도구의 경로 인자를 검증하고 감사 로그에 user_id 주입"""
        user_id = context.get("user_id", "anonymous")

        for tool in tools:
            if tool.name not in _PATH_ARG_TOOLS:
                continue

            path_arg_name = _PATH_ARG_TOOLS[tool.name]

            # 이미 래핑된 경우 스킵
            if hasattr(tool, "_nas_wrapped"):
                continue

            original_ainvoke = getattr(tool, "_unwrapped_ainvoke", tool.ainvoke)

            async def secured_ainvoke(
                input_data,
                config=None,
                *,
                _original=original_ainvoke,
                _path_arg=path_arg_name,
                _tool_name=tool.name,
                _user_id=user_id,
                **kwargs,
            ):
                # ToolCall 형식: {name, args, id, type}
                args = input_data.get("args", input_data) if isinstance(input_data, dict) else input_data

                # 경로 인자 검증
                if isinstance(args, dict) and _path_arg in args:
                    raw_path = args[_path_arg]
                    try:
                        validated = _validate_nas_path(raw_path)
                        args[_path_arg] = validated
                    except ValueError as e:
                        print(f"[NAS] BLOCKED: user={_user_id} tool={_tool_name} path={raw_path} reason={e}", file=sys.stderr)
                        return f"접근 차단: {e}"

                # 감사 로그
                path_val = args.get(_path_arg, "?") if isinstance(args, dict) else "?"
                print(f"[NAS] user={_user_id} tool={_tool_name} path={path_val}", file=sys.stderr)

                return await _original(input_data, config, **kwargs)

            object.__setattr__(tool, "_unwrapped_ainvoke", original_ainvoke)
            object.__setattr__(tool, "ainvoke", secured_ainvoke)
            object.__setattr__(tool, "_nas_wrapped", True)

        return tools

"""MCP Adapter - MCP 서버들과 통신하는 클라이언트 어댑터

이 모듈은 langchain-mcp-adapters의 MultiServerMCPClient를 기반으로 구축되었습니다.

주요 기능:
- mcp_config.json 파일을 로드하고 ${ENV_VAR} 형식의 환경변수를 치환
- 여러 MCP 서버를 동시에 연결/관리하는 비동기 컨텍스트 매니저 제공
- MCP 도구들을 LangChain Tool 객체로 변환하여 제공 (캐싱 지원)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

# LangChain의 MCP 어댑터 - 여러 MCP 서버를 동시에 관리
from langchain_mcp_adapters.client import MultiServerMCPClient


@dataclass
class MCPServerDefinition:
    """MCP 서버 정의를 담는 데이터 클래스

    mcp_config.json의 각 서버 설정을 파싱하여 저장합니다.

    Attributes:
        name: 서버 이름 (예: "rag", "tavily", "github")
        transport: 통신 방식 ("stdio", "sse", "http" 등)
        description: 서버 설명 (선택)
        enabled: 서버 활성화 여부 (기본값: True)
        url: 원격 MCP 서버 URL (HTTP/SSE 통신 시 사용)
        command: 로컬 프로세스 실행 명령 (stdio 통신 시 사용, 예: "python")
        args: command 실행 시 인자 (예: ["backend/app/mcp_servers/rag_server.py"])
        env: 환경변수 딕셔너리 (프로세스 실행 시 전달)
    """
    name: str
    transport: str
    description: str = ""
    enabled: bool = True
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None


def _substitute_env(value: str) -> str:
    """환경변수 플레이스홀더를 실제 값으로 치환

    mcp_config.json에서 ${GITHUB_TOKEN}, ${API_KEY} 같은 형식을
    실제 환경변수 값으로 대체합니다.

    Args:
        value: 치환할 문자열 (예: "https://api.com?key=${API_KEY}")

    Returns:
        환경변수가 치환된 문자열 (예: "https://api.com?key=sk-1234...")

    Example:
        >>> os.environ["API_KEY"] = "secret123"
        >>> _substitute_env("Bearer ${API_KEY}")
        'Bearer secret123'
    """
    result = value
    # 현재 환경변수를 순회하며 ${VAR} 형태를 찾아 치환
    for key, val in os.environ.items():
        placeholder = f"${{{key}}}"  # ${API_KEY} 형태로 만듦
        if placeholder in result:
            result = result.replace(placeholder, val)
    return result


def _load_mcp_config(config_path: str) -> Dict[str, MCPServerDefinition]:
    """mcp_config.json 파일을 로드하고 파싱

    JSON 파일에서 MCP 서버 설정을 읽어와 MCPServerDefinition 객체로 변환합니다.
    이 과정에서 환경변수 치환도 수행합니다.

    Args:
        config_path: mcp_config.json 파일 경로

    Returns:
        서버 이름을 키로 하는 MCPServerDefinition 딕셔너리

    Example:
        >>> servers = _load_mcp_config("backend/mcp_config.json")
        >>> servers["rag"].command
        'python'
        >>> servers["rag"].args
        ['backend/app/mcp_servers/rag_server.py']
    """
    # JSON 파일 읽기
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    servers: Dict[str, MCPServerDefinition] = {}

    # "mcpServers" 섹션의 각 서버 설정을 순회
    for name, cfg in raw.get("mcpServers", {}).items():
        url = cfg.get("url")          # 원격 서버 URL (있는 경우)
        command = cfg.get("command")  # 로컬 실행 명령 (있는 경우)
        args = cfg.get("args")        # 명령 인자 (있는 경우)
        env = cfg.get("env")          # 환경변수 (있는 경우)

        # URL과 args에 환경변수가 있으면 치환
        if url:
            url = _substitute_env(url)
        if args:
            args = [_substitute_env(arg) for arg in args]
        # env 값에도 환경변수 치환 적용
        if env:
            env = {k: _substitute_env(v) for k, v in env.items()}

        # MCPServerDefinition 객체 생성
        servers[name] = MCPServerDefinition(
            name=name,
            transport=cfg.get("transport", "stdio"),  # 기본값: stdio
            description=cfg.get("description", ""),
            enabled=cfg.get("enabled", True),         # 기본값: True
            url=url,
            command=command,
            args=args,
            env=env,
        )
    return servers


class MCPAdapter:
    """MCP 서버 클라이언트 어댑터 - 여러 MCP 서버를 통합 관리

    MultiServerMCPClient를 래핑하여 설정 파일 로드와 환경변수 치환 기능을 추가합니다.
    비동기 컨텍스트 매니저로 사용할 수 있으며, 도구 목록을 캐싱하여 성능을 최적화합니다.

    사용 예시:
        >>> adapter = MCPAdapter("backend/mcp_config.json")
        >>> await adapter.open()
        >>> tools = await adapter.get_tools()  # LangChain Tool 리스트 반환
        >>> # ... tools 사용 ...
        >>> await adapter.close()

        또는 컨텍스트 매니저:
        >>> async with MCPAdapter("backend/mcp_config.json") as adapter:
        >>>     tools = await adapter.get_tools()
        >>>     # ... tools 사용 ...

    Attributes:
        config_path: mcp_config.json 파일 경로
        servers: 로드된 MCP 서버 정의 딕셔너리
        _client: MultiServerMCPClient 인스턴스 (open 후 생성)
        _tools_cache: 캐싱된 LangChain Tools 리스트
    """

    # 클래스 레벨 글로벌 캐시 (TTL 기반)
    _global_tools_cache: Optional[List] = None
    _cache_timestamp: Optional[float] = None
    CACHE_TTL: int = 3600  # 1시간

    def __init__(self, config_path: str):
        """MCPAdapter 초기화

        Args:
            config_path: mcp_config.json 파일 경로
        """
        self.config_path = config_path
        # 설정 파일에서 서버 정의 로드
        self.servers = _load_mcp_config(config_path)
        # 아직 연결 전이므로 None
        self._client: Optional[MultiServerMCPClient] = None
        self._tools_cache: Optional[List] = None

    async def open(self):
        """MCP 서버 클라이언트 초기화 및 연결

        enabled=True인 서버들만 필터링하여 MultiServerMCPClient를 생성합니다.
        각 서버는 transport 타입에 따라 다르게 연결됩니다:
        - stdio: command + args로 로컬 프로세스 실행
        - sse/http: url로 원격 서버 연결

        Returns:
            self (컨텍스트 매니저 패턴 지원)

        Note:
            MultiServerMCPClient는 async context manager가 아니므로
            수동으로 open/close를 관리합니다.
        """
        if self._client is None:
            # enabled된 서버만 필터링하여 클라이언트 설정 생성
            self._client = MultiServerMCPClient(
                {
                    name: {
                        "transport": s.transport,
                        # url이 있으면 포함 (원격 서버)
                        **({"url": s.url} if s.url else {}),
                        # command가 있으면 포함 (로컬 프로세스)
                        **({"command": s.command, "args": s.args or []} if s.command else {}),
                        # env가 있으면 포함 (환경변수)
                        **({"env": s.env} if s.env else {}),
                    }
                    for name, s in self.servers.items()
                    if s.enabled  # enabled=True인 서버만
                }
            )
        return self

    async def close(self):
        """MCP 서버 클라이언트 종료 및 정리

        클라이언트와 캐시를 정리합니다.

        Note:
            MultiServerMCPClient는 별도의 close 메서드가 없으므로
            참조만 해제하여 가비지 컬렉션되도록 합니다.
        """
        self._client = None
        self._tools_cache = None

    async def get_tools(self, force_refresh: bool = False):
        """MCP 서버들로부터 도구(Tool) 목록을 가져옴 (TTL 기반 글로벌 캐시)

        연결된 모든 MCP 서버의 도구들을 LangChain Tool 형식으로 반환합니다.
        결과는 글로벌 캐싱되며 (TTL 5분), force_refresh=True로 캐시를 무시할 수 있습니다.

        Args:
            force_refresh: True면 캐시 무시하고 서버에서 다시 가져옴 (기본값: False)

        Returns:
            LangChain Tool 객체 리스트

        Raises:
            RuntimeError: open()을 먼저 호출하지 않은 경우
        """
        if self._client is None:
            raise RuntimeError("MCPAdapter must be opened first (await open())")

        now = time.time()

        # TTL 기반 글로벌 캐시 체크
        if (
            MCPAdapter._global_tools_cache is not None
            and not force_refresh
            and MCPAdapter._cache_timestamp is not None
            and (now - MCPAdapter._cache_timestamp) < MCPAdapter.CACHE_TTL
        ):
            cache_age = int(now - MCPAdapter._cache_timestamp)
            print(f"[MCP] Using cached tools (age: {cache_age}s, TTL: {MCPAdapter.CACHE_TTL}s)")
            return MCPAdapter._global_tools_cache

        # 캐시 미스 - 서버에서 가져오기
        print("[MCP] Fetching tools from MCP servers...")
        tools = await self._client.get_tools()

        # 직접 호출 RAG 도구 추가 (MCP 프로세스 오버헤드 제거)
        from app.agents.tools.rag_direct_tools import get_direct_rag_tools
        direct_rag_tools = get_direct_rag_tools()
        tools = list(tools)  # 리스트로 변환 (불변 객체일 수 있음)
        tools.extend(direct_rag_tools)
        print(f"[MCP] Added {len(direct_rag_tools)} direct RAG tools")

        # 글로벌 캐시 업데이트
        MCPAdapter._global_tools_cache = tools
        MCPAdapter._cache_timestamp = now
        print(f"[MCP] Tools cached: {len(tools)} tools")

        return tools

    async def refresh_tools(self):
        """도구 목록을 강제로 새로고침

        캐시를 무시하고 MCP 서버들로부터 도구 목록을 다시 가져옵니다.

        Returns:
            LangChain Tool 객체 리스트

        Note:
            get_tools(force_refresh=True)와 동일한 동작
        """
        return await self.get_tools(force_refresh=True)

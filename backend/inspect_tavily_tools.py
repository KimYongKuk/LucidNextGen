"""Tavily MCP Tool 스펙 확인"""
import asyncio
import json
from app.services.mcp_client_manager import get_mcp_manager


async def inspect_tavily_tools():
    """Tavily Tool의 파라미터 확인"""
    print("\n" + "="*80)
    print("Tavily MCP Tool 스펙 조사")
    print("="*80 + "\n")

    # MCP Manager 가져오기
    manager = await get_mcp_manager()

    # 모든 Tool 가져오기
    tools = await manager.get_all_tools()

    # Tavily 관련 Tool만 필터링
    tavily_tools = [
        tool for tool in tools
        if 'tavily' in tool['toolSpec']['name'].lower()
    ]

    if not tavily_tools:
        print("[WARNING] Tavily Tool을 찾을 수 없습니다.")
        return

    print(f"[OK] {len(tavily_tools)}개의 Tavily Tool 발견\n")

    for tool in tavily_tools:
        spec = tool['toolSpec']
        print("-" * 80)
        print(f"[TOOL] Name: {spec['name']}")
        print(f"[DESC] {spec['description']}")
        print(f"\n[INPUT SCHEMA]:")
        print(json.dumps(spec['inputSchema']['json'], indent=2, ensure_ascii=False))
        print("-" * 80)
        print()


if __name__ == "__main__":
    asyncio.run(inspect_tavily_tools())

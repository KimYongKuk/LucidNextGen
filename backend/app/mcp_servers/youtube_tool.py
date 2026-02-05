"""YouTube MCP Server - 유튜브 비디오 요약"""
import sys
import os
import asyncio
import json

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP
from app.services.youtube_summary_service import get_youtube_summary_service

# MCP 서버 초기화
mcp = FastMCP("YouTube Summary Server")

# YouTube Summary Service 초기화
youtube_service = get_youtube_summary_service()


@mcp.tool()
async def youtube_summarize(
    youtube_url: str,
    user_id: str = "anonymous"
) -> str:
    """유튜브 비디오 요약. URL이 youtube.com 또는 youtu.be면 즉시 호출."""
    try:
        # YouTube Summary Service 호출
        result = await youtube_service.summarize_video(youtube_url, user_id)

        # JSON 문자열로 변환하여 반환
        # (Agent가 파싱하기 쉽도록)
        return json.dumps(result, ensure_ascii=False, indent=2)

    except ValueError as e:
        # URL 파싱 실패
        return json.dumps({
            "error": "invalid_url",
            "message": str(e)
        }, ensure_ascii=False)

    except Exception as e:
        # 기타 오류 - 자세한 로그 출력
        import traceback
        error_trace = traceback.format_exc()
        print(f"[YOUTUBE_TOOL] ERROR: {str(e)}")
        print(f"[YOUTUBE_TOOL] Traceback:\n{error_trace}")

        return json.dumps({
            "error": "service_error",
            "message": str(e)  # 중복 메시지 제거
        }, ensure_ascii=False)


if __name__ == "__main__":
    # MCP 서버 실행
    mcp.run()

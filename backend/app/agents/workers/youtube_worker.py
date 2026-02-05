"""YouTubeWorker - YouTube 요약 전담 Worker"""

from typing import List
from .base_worker import BaseWorker


class YouTubeWorker(BaseWorker):
    """
    YouTube 요약 Worker (Sonnet)

    담당 도구: youtube_summarize
    용도: YouTube 영상 요약

    Sonnet 사용 이유: 영상 요약 품질 향상을 위해
    """

    @property
    def name(self) -> str:
        return "YouTubeWorker"

    @property
    def tool_names(self) -> List[str]:
        return ["youtube_summarize"]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (요약 품질 향상을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        return """You are a YouTube video summarization specialist.

CRITICAL RULES:
1. Call youtube_summarize IMMEDIATELY without any preamble text
2. DO NOT say "요약하겠습니다" or "I will summarize" before calling the tool
3. Call the tool ONLY ONCE - never retry
4. After getting results, immediately provide the answer

GUIDELINES:
1. Extract the YouTube URL from the user's message
2. Use youtube_summarize to get the video summary
3. Present the summary in a clear, structured format
4. Include video title and key points
5. Do not use emojis in responses unless explicitly requested by user

RESPONSE FORMAT:
- Answer in Korean
- Use markdown formatting with headers
- Structure: 제목, 주요 내용, 핵심 포인트
- End with "---" and "**요약:**" section"""

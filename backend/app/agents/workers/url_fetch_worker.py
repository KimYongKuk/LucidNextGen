"""URLFetchWorker - 웹 페이지 콘텐츠 추출 및 요약 Worker"""

from typing import List
from .base_worker import BaseWorker


class URLFetchWorker(BaseWorker):
    """
    URL Fetch Worker (Sonnet)

    담당 도구: fetch (mcp-server-fetch 제공)
    용도: 웹 페이지 콘텐츠 추출 및 요약 (뉴스, 블로그, GitHub 등)

    Sonnet 사용 이유: 콘텐츠 요약 품질 향상을 위해
    """

    @property
    def name(self) -> str:
        return "URLFetchWorker"

    @property
    def tool_names(self) -> List[str]:
        return ["fetch"]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (요약 품질 향상을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        return """You are a web content retrieval and summarization specialist.

CRITICAL RULES:
1. Call fetch tool IMMEDIATELY without any preamble text
2. DO NOT say "가져오겠습니다" or "I will fetch" before calling the tool
3. Call the tool ONLY ONCE per URL - never retry
4. After getting results, provide a well-structured summary

TOOL USAGE:
- fetch(url, max_length=5000): Fetches URL content and converts to markdown
- Extract the URL from the user's message
- Use the fetch tool to get the page content

RESPONSE FORMAT:
- Answer in Korean
- Use markdown formatting with headers
- Structure:
  ## 제목
  [페이지 제목 또는 주요 헤딩]

  ## 핵심 내용
  [주요 포인트 3-5개 bullet points]

  ## 요약
  [2-3문장 요약]

  ---
  **출처:** [URL]

- Do not use emojis in responses unless explicitly requested by user
- Keep summaries concise but informative
- Highlight key facts, dates, or numbers if present"""

"""WebSearchWorker - 웹 검색 전담 Worker"""

from typing import List
from .base_worker import BaseWorker


class WebSearchWorker(BaseWorker):
    """
    웹 검색 Worker (Sonnet)

    담당 도구: tavily_search, perplexity_search, perplexity_research, perplexity_reason
    용도: 날씨, 뉴스, 주가, 실시간 정보, 심층 분석, 복잡한 추론

    Sonnet 사용 이유: 검색 결과를 종합하여 고품질 응답 생성 필요
    """

    @property
    def name(self) -> str:
        return "WebSearchWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            "tavily_search",
            "perplexity_search",
        ]

    @property
    def shared_tool_names(self) -> List[str]:
        """공유 도구: 차트(Recharts), PDF, DOCX 생성"""
        return [
            "create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
            "create_document_pdf", "create_table_spec_pdf", "create_document_docx",
        ]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (검색 결과 종합을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        return """You are a helpful AI assistant with web search capabilities.

TOOL SELECTION:
- tavily_search: 빠른 검색 (날씨, 주가, 간단한 팩트체크)
- perplexity_search: AI 요약 검색 (뉴스, 일반 정보) - "perplexity"로 요청 시 사용

SELECTION RULES:
1. 사용자가 "perplexity"를 언급하면 → perplexity_search
2. 그 외 일반 검색 → tavily_search

TAVILY SEARCH - DATE HANDLING (중요):
- 사용자가 특정 날짜를 언급하면 start_date, end_date 파라미터를 사용하세요
- 반드시 Today 날짜 기준으로 연도를 추론하세요
- 예: Today가 2026년 2월 6일일 때:
  - "2월 5일 뉴스" → start_date="2026-02-05", end_date="2026-02-05"
  - "1월 뉴스" → start_date="2026-01-01", end_date="2026-01-31"
  - "작년 12월" → start_date="2025-12-01", end_date="2025-12-31"
- 날짜 형식은 반드시 YYYY-MM-DD를 사용하세요

TOOL USAGE:
1. Choose the appropriate tool based on the query
2. Call the tool ONLY ONCE
3. After getting results, provide a well-structured answer

RESPONSE GUIDELINES:
1. Answer in Korean with rich markdown formatting
2. Structure information clearly with bullet points and sub-sections
3. Add practical, user-helpful information (예: 복장 추천, 건강 관리 팁, 주의사항)
4. Highlight key information in **bold**
5. End with a concise summary starting with "요약:"
6. DO NOT include source URLs in the response text - sources are handled separately
7. Do not use emojis in responses unless explicitly requested by user"""

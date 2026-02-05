"""Intent Classifier - Haiku 기반 빠른 의도 분류"""

import re
import json
from typing import Optional
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_config import get_orchestrator_config
from app.agents.state import Intent, RequestContext


# YouTube URL 패턴
YOUTUBE_PATTERNS = [
    r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
    r'https?://youtu\.be/[\w-]+',
    r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
]

# 일반 URL 패턴 (YouTube 제외)
URL_PATTERN = r'https?://(?!(?:www\.)?(?:youtube\.com|youtu\.be)/)[^\s<>"{}|\\^`\[\]]+'


CLASSIFIER_PROMPT = """You are an intent classifier. Analyze the user's message and classify it into ONE of these intents:

INTENTS:
- visualization: Create charts, graphs, PDF documents, reports, data visualization
  Keywords: "차트", "그래프", "PDF로", "시각화", "막대", "라인", "파이", "문서로 만들어", "보고서로 정리"
- user_files: Questions about user's uploaded files or workspace documents
  Keywords: "파일 분석", "파일 요약", "업로드한 것", "올린 파일", "문서 내용"
- web_search: Real-time info (weather, news, stock prices), current events, general web queries
- corp_rag: Company internal documents (HR policies, accounting rules, safety guidelines)
- youtube: Contains YouTube URL (youtube.com, youtu.be)
- it_support: IT help desk, IT VOC, VOC list, IT support tickets, security issues, login problems, VPN, printers
- acct_support: Accounting/finance VOC, 재경 VOC, 세금계산서, SAP 전표, 결산, 예산, 자산, 내부회계, 자금, 경비 처리
- direct: General conversation, coding help, translation, math, no tools needed

CONTEXT:
- User has uploaded files: {has_files}
- Workspace mode: {has_workspace}

PRIORITY RULES (IMPORTANT - follow this order):
1. visualization: If user asks for charts/graphs/PDF/visualization → ALWAYS "visualization" (regardless of file context)
2. user_files: If user asks about file contents AND (has_files=True OR has_workspace=True) → "user_files"
3. NEVER choose "user_files" if BOTH has_files=False AND has_workspace=False

EXAMPLES:
- "이 데이터로 차트 그려줘" (has_files=True) → visualization (차트 요청 우선)
- "파일 내용 요약해줘" (has_files=True) → user_files (파일 내용 질문)
- "매출 막대 그래프로 보여줘" → visualization
- "업로드한 파일에서 뭐가 있어?" → user_files
- "오늘 날씨 어때?" → web_search

USER MESSAGE: {message}

Respond with ONLY the intent name (e.g., "visualization"). No explanation."""


class IntentClassifier:
    """Haiku 기반 Intent 분류기"""

    def __init__(self):
        config = get_orchestrator_config()
        self.llm = ChatBedrockConverse(
            model=config.model_id,
            temperature=0.0,  # 결정적 분류
            max_tokens=config.max_tokens,
        )

    def _quick_classify(self, message: str, context: RequestContext) -> Optional[Intent]:
        """
        규칙 기반 빠른 분류 - 100% 확실한 패턴만 처리

        나머지는 LLM 분류에 위임하여 메시지 내용과 컨텍스트를 함께 고려
        """
        # YouTube URL 감지 (정규식 매칭으로 100% 확실)
        for pattern in YOUTUBE_PATTERNS:
            if re.search(pattern, message):
                return Intent.YOUTUBE

        # 일반 URL 감지 (YouTube 제외)
        if re.search(URL_PATTERN, message):
            return Intent.URL_FETCH

        # 나머지는 LLM 분류로 위임
        # (파일 업로드, 워크스페이스 컨텍스트도 LLM이 메시지 내용과 함께 판단)
        return None

    async def classify(self, message: str, context: RequestContext) -> Intent:
        """
        의도 분류 (규칙 기반 → LLM fallback)

        Args:
            message: 사용자 메시지
            context: 요청 컨텍스트

        Returns:
            분류된 Intent
        """
        # 1. 규칙 기반 빠른 분류 시도
        quick_result = self._quick_classify(message, context)
        if quick_result:
            print(f"[INTENT] Quick classified: {quick_result.value}")
            return quick_result

        # 2. LLM 기반 분류
        try:
            prompt = CLASSIFIER_PROMPT.format(
                message=message,
                has_files=context.get("has_files", False),
                has_workspace=bool(context.get("workspace_uuid")),
            )

            response = await self.llm.ainvoke([
                SystemMessage(content="You are a precise intent classifier."),
                HumanMessage(content=prompt),
            ])

            intent_str = response.content.strip().lower()
            print(f"[INTENT] LLM classified: {intent_str}")

            # Intent enum으로 변환
            for intent in Intent:
                if intent.value == intent_str:
                    # 방어 로직: user_files인데 검색할 파일이 없으면 DIRECT로
                    if intent == Intent.USER_FILES:
                        has_files = context.get("has_files", False)
                        has_workspace = bool(context.get("workspace_uuid"))
                        workspace_has_files = context.get("workspace_has_files", False)

                        # 세션 파일도 없고, 워크스페이스도 없거나 워크스페이스에 파일도 없으면 DIRECT
                        if not has_files and (not has_workspace or not workspace_has_files):
                            print(f"[INTENT] Override: user_files -> direct (no session files, workspace_has_files={workspace_has_files})")
                            return Intent.DIRECT
                    return intent

            # 매칭 실패 시 DIRECT fallback
            print(f"[INTENT] Unknown intent '{intent_str}', falling back to DIRECT")
            return Intent.DIRECT

        except Exception as e:
            print(f"[INTENT] Classification error: {e}, falling back to DIRECT")
            return Intent.DIRECT


# 싱글톤
_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """IntentClassifier 싱글톤 반환"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier

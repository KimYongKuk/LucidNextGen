"""Intent Classifier - Haiku 기반 빠른 의도 분류"""

import os
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
- ppt_generation: Create PowerPoint presentations, slides, PPT files
  Keywords: "PPT", "파워포인트", "프레젠테이션", "발표자료", "슬라이드로", "PT자료", "PPT로", "발표 자료"
- visualization: Create charts, graphs, PDF documents, reports, data visualization
  Keywords: "차트", "그래프", "PDF로", "시각화", "막대", "라인", "파이", "문서로 만들어", "보고서로 정리"
- user_files: Questions about user's uploaded files or workspace documents
  Keywords: "파일 분석", "파일 요약", "업로드한 것", "올린 파일", "문서 내용"
- web_search: Queries that require up-to-date or factual information from the internet
  Keywords: "동향", "트렌드", "뉴스", "소식", "현황", "전망", "시황", "시세", "주가", "환율", "날씨", "이슈", "실적"
  Time indicators: "이번달", "이번주", "올해", "최근", "최신", "오늘", "어제", "지난달", "현재", specific years
  Topics: weather, news, stock/financial info, market trends, industry analysis, company info lookup, tax rates, regulations, product prices, sports scores, event schedules
  IMPORTANT: If user asks about specific companies, industries, market trends, or ANY information that changes over time → ALWAYS "web_search"
  IMPORTANT: "정리해줘" or "알려줘" combined with real-world topics = web_search (NOT direct)
- corp_rag: Company internal documents (HR policies, safety guidelines), organization chart, finding staff/person in charge for GENERAL departments
  Keywords: "부서", "조직도", "근무지", "인원", "직원", "책임자", "담당자"
  NOTE: If "담당자" is combined with IT/security keywords → use "it_support" instead. If combined with accounting/finance keywords → use "acct_support" instead.
- youtube: Contains YouTube URL (youtube.com, youtu.be)
- it_support: IT help desk, IT VOC, VOC list, IT support tickets, security issues, login problems, VPN, printers. Also handles IT-domain person-in-charge questions.
  Keywords: "IT 담당자", "VPN 담당자", "보안 담당자", "프린터 담당자", "네트워크 담당자", "시스템 담당자"
  Internal IT systems/solutions: 쉐도우큐브, ShadowCube, DRM, DLP, LFON, SAP GUI, Citrix, AD, Active Directory, 방화벽, 백신, 매체제어, 출력보안, 특별라이센스
- acct_support: Accounting/finance VOC, 재경 VOC, 세금계산서, SAP 전표, 결산, 예산, 자산, 내부회계, 자금, 경비 처리. Also handles finance-domain person-in-charge questions.
  Keywords: "회계 담당자", "재경 담당자", "세금계산서 담당자", "결산 담당자", "예산 담당자", "자금 담당자", "SAP 담당자"
  Accounting systems: SAP ERP, SAP FI, SAP CO, 전자세금계산서, 법인카드, iCUBE
- mail: Check/search user's email inbox, sent mail, unread mail, mail folders
  Keywords: "메일", "이메일", "email", "받은편지함", "보낸편지함", "편지함", "안읽은 메일", "새 메일", "메일 검색", "수신함", "발신함", "inbox", "mailbox"
- approval: Electronic approval document queries - check pending approvals, drafted documents, approval status, bottleneck analysis, department documents
  Keywords: "결재", "기안", "상신", "전자결재", "결재 대기", "결재 완료", "결재함", "기안함", "참조함", "반려", "재기안", "결재선", "합의", "승인 문서", "결재 건"
  NOTE: "결산" (settlement/closing) is accounting → use "acct_support", NOT "approval"
- direct: General conversation, coding help, translation, math, creative writing, no tools needed
  ONLY use "direct" for tasks that do NOT require any external information (e.g., pure conversation, coding, translation, math)

CONTEXT:
- User has uploaded files: {has_files}
- Workspace mode: {has_workspace}
- Workspace name: {workspace_name}
- Workspace description: {workspace_description}
- Workspace uploaded files: {workspace_file_names}

PRIORITY RULES (IMPORTANT - follow this order):
1. ppt_generation: If user asks for PPT/PowerPoint/presentation/slides → ALWAYS "ppt_generation"
2. visualization: If user asks for charts/graphs/PDF/visualization → ALWAYS "visualization" (regardless of file context)
3. WORKSPACE-AWARE ROUTING (when has_workspace=True AND workspace has files):
   - Compare the user's query topic with the workspace name, description, and uploaded file names
   - If the query topic MATCHES the workspace domain → "user_files" (search workspace documents first)
   - If the query topic is UNRELATED to the workspace → use the specialized intent (mail, web_search, etc.)
   - Examples:
     - Workspace "메일 관리" with files ["2월_수신메일목록.xlsx"] + query "메일 현황 정리해줘" → "user_files" (workspace covers mail topic)
     - Workspace "분기 실적" with files ["매출보고서.pdf"] + query "안 읽은 메일 확인해줘" → "mail" (workspace is about finance, not mail)
     - Workspace "AI 리서치" with files ["AI동향보고서.pdf"] + query "최근 AI 트렌드" → "user_files" (workspace covers AI trends)
     - Workspace "AI 리서치" with files ["AI동향보고서.pdf"] + query "오늘 날씨" → "web_search" (unrelated to workspace)
4. mail: If user asks about their email/inbox/sent mail/unread mail → "mail"
5. approval: If user asks about electronic approval documents, pending approvals, drafted documents, approval status, bottleneck → "approval"
6. web_search: If user asks about real-world topics, industries, companies, trends, current events, or anything requiring up-to-date info → "web_search"
7. user_files: If user asks about file contents AND (has_files=True OR has_workspace=True) → "user_files"
8. NEVER choose "user_files" if BOTH has_files=False AND has_workspace=False
9. NEVER choose "direct" if the query is about real-world facts, companies, industries, or current information

WORKSPACE RULES (when has_workspace=True AND workspace has files):
- The user is working inside a workspace session, so workspace documents are the primary knowledge source
- Follow-up questions, corrections, complaints about accuracy/hallucination → "user_files"
- Questions referencing specific data, names, numbers from previous context → "user_files"
- Only route to specialized intents (mail, web_search, etc.) when the topic is CLEARLY outside the workspace domain
- Only use "direct" for tasks CLEARLY unrelated to documents: pure coding, translation, math, creative writing

EXAMPLES:
- "분기 실적 PPT 만들어줘" → ppt_generation (PPT 생성 요청)
- "발표자료 슬라이드로 정리해줘" → ppt_generation
- "이 데이터로 차트 그려줘" (has_files=True) → visualization (차트 요청 우선)
- "파일 내용 요약해줘" (has_files=True) → user_files (파일 내용 질문)
- "매출 막대 그래프로 보여줘" → visualization
- "업로드한 파일에서 뭐가 있어?" → user_files
- "오늘 날씨 어때?" → web_search
- "이번달 2차전지 산업 주요 동향 정리" → web_search (산업 동향 = 실시간 정보)
- "엘앤에프 증권거래세" → web_search (주식/세금 정보 = 실시간 정보)
- "최신 AI 기술 트렌드" → web_search (최신 정보 필요)
- "삼성전자 주가" → web_search (주가 조회)
- "반도체 산업 전망 정리해줘" → web_search (산업 분석 = 실시간 정보)
- "테슬라 실적 분석" → web_search (기업 실적 = 실시간 정보)
- "비트코인 시세" → web_search (시세 조회)
- "마케팅 담당자 누구야?" → corp_rag (일반 부서 담당자)
- "대전 근무자 리스트" → corp_rag (조직도)
- "VPN 담당자 누구야?" → it_support (IT 도메인 담당자)
- "보안 담당자 찾아줘" → it_support (IT/보안 도메인)
- "쉐도우큐브 담당자 누구야?" → it_support (사내 IT 시스템)
- "DRM 해제 담당자?" → it_support (사내 보안 시스템)
- "세금계산서 담당자?" → acct_support (재경 도메인 담당자)
- "결산 담당자 누구야?" → acct_support (회계 도메인)
- "최근 메일 보여줘" → mail (메일 조회)
- "안 읽은 메일 있어?" → mail (안읽은 메일)
- "김영수한테 온 메일 찾아줘" → mail (메일 검색)
- "메일함 목록 보여줘" → mail (메일함 조회)
- "보낸 메일 확인해줘" → mail (보낸편지함)
- "결재 대기 건 있어?" → approval (결재 대기 조회)
- "내 기안 문서 보여줘" → approval (기안함 조회)
- "결재선에서 누가 안 해?" → approval (병목 분석)
- "이번 달 결재 처리 건수" → approval (결재 완료 통계)
- "반려된 문서 찾아줘" → approval (반려 문서 조회)
- "부서 수신 문서 있어?" → approval (부서 수신함)
- "안 읽은 참조 문서" → approval (참조함 미열람)
- "긴급 결재 건 확인해줘" → approval (긴급 결재 대기)
- "코드 리뷰해줘" → direct (코딩 도움)
- "이 문장 영어로 번역해줘" → direct (번역)

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

        # 워크스페이스에 파일이 있으면 전문 인텐트(MAIL, WEB_SEARCH) quick 판단을 보류
        # → LLM 분류기가 워크스페이스 컨텍스트(이름/설명/파일명)를 보고 최종 판단
        workspace_has_files = context.get("workspace_has_files", False)

        # 메일 관련 키워드 감지 (MAIL_WORKER_ENABLED 환경변수로 on/off)
        mail_enabled = os.environ.get("MAIL_WORKER_ENABLED", "true").lower() == "true"
        if mail_enabled:
            mail_keywords = r'(메일|이메일|e-?mail|받은\s?편지|보낸\s?편지|편지함|안\s?읽은\s?메일|새\s?메일|수신함|발신함|inbox|sent\s?mail|mailbox|unread)'
            if re.search(mail_keywords, message, re.IGNORECASE):
                if workspace_has_files:
                    # 워크스페이스에 파일이 있으면 LLM에게 위임 (워크스페이스 주제와 관련 있을 수 있음)
                    print(f"[INTENT] Quick: mail keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.MAIL

        # 전자결재 관련 키워드 감지 (APPROVAL_WORKER_ENABLED 환경변수로 on/off)
        approval_enabled = os.environ.get("APPROVAL_WORKER_ENABLED", "true").lower() == "true"
        if approval_enabled:
            approval_keywords = r'(결재|기안|상신|전자결재|결재\s?대기|결재\s?완료|결재함|기안함|반려|재기안|결재선|합의|승인\s?문서|결재\s?건)'
            if re.search(approval_keywords, message, re.IGNORECASE):
                if workspace_has_files:
                    print(f"[INTENT] Quick: approval keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.APPROVAL

        if not workspace_has_files:
            # 시간 기반 정보 요청 감지 → 웹 검색 필요 (실시간 정보)
            time_keywords = r'(이번\s?달|이번\s?주|올해|최근|최신|금일|오늘|어제|지난\s?달|지난\s?주|2026년|2025년|현재)'
            info_keywords = r'(동향|트렌드|뉴스|소식|현황|상황|이슈|전망|시황|시세|주가|환율|날씨|실적|실시간)'
            if re.search(time_keywords, message) and re.search(info_keywords, message):
                return Intent.WEB_SEARCH

            # 주식/금융/산업 관련 키워드 → 실시간 정보 필요
            finance_keywords = r'(주가|주식|시세|환율|증권|거래세|코스피|코스닥|나스닥|S&P|배당|공모주|IPO|시가총액|PER|PBR|EPS)'
            if re.search(finance_keywords, message):
                return Intent.WEB_SEARCH

            # 산업/시장 동향 키워드 (시간 키워드 없이도 웹 검색 필요)
            industry_keywords = r'(동향|트렌드|전망|시황|산업\s?.+\s?정리|시장\s?.+\s?분석|업계\s?.+\s?현황)'
            if re.search(industry_keywords, message):
                return Intent.WEB_SEARCH

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
            # 워크스페이스 메타데이터 준비 (인텐트 분류용)
            workspace_name = "N/A"
            workspace_description = "N/A"
            workspace_file_names = "None"
            has_workspace = bool(context.get("workspace_uuid") or context.get("workspace_id"))
            if has_workspace:
                workspace_name = context.get("workspace_name") or "N/A"
                workspace_description = context.get("workspace_description") or "N/A"
                file_names_list = context.get("workspace_file_names", [])
                workspace_file_names = ", ".join(file_names_list) if file_names_list else "None"

            prompt = CLASSIFIER_PROMPT.format(
                message=message,
                has_files=context.get("has_files", False),
                has_workspace=has_workspace,
                workspace_name=workspace_name,
                workspace_description=workspace_description,
                workspace_file_names=workspace_file_names,
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
                        has_workspace = bool(context.get("workspace_uuid") or context.get("workspace_id"))
                        workspace_has_files = context.get("workspace_has_files", False)

                        # 세션 파일도 없고, 워크스페이스도 없거나 워크스페이스에 파일도 없으면 DIRECT
                        if not has_files and (not has_workspace or not workspace_has_files):
                            print(f"[INTENT] Override: user_files -> direct (no session files, workspace_has_files={workspace_has_files})")
                            return Intent.DIRECT

                    # 워크스페이스에 파일이 있고, 정보 검색 의도면 → 워크스페이스 문서 우선 검색
                    workspace_has_files = context.get("workspace_has_files", False)
                    if workspace_has_files and intent in (Intent.CORP_RAG, Intent.IT_SUPPORT, Intent.ACCT_SUPPORT):
                        print(f"[INTENT] Override: {intent.value} -> user_files (workspace has files, search workspace docs first)")
                        return Intent.USER_FILES

                    # 워크스페이스에 파일이 있는데 direct로 분류되면 → user_files로 오버라이드
                    # (UserFilesWorker가 내부적으로 도구 호출 필요 여부를 판단함)
                    if workspace_has_files and intent == Intent.DIRECT:
                        print(f"[INTENT] Override: direct -> user_files (workspace has files, ensure document-grounded response)")
                        return Intent.USER_FILES

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

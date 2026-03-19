"""Intent Classifier - Haiku 기반 빠른 의도 분류"""

import os
import re
import asyncio
from typing import Optional, List, Dict, Tuple
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_config import get_orchestrator_config
from app.core.region_fallback import get_region_fallback_manager
from app.agents.state import Intent, RequestContext


# YouTube URL 패턴
YOUTUBE_PATTERNS = [
    r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
    r'https?://youtu\.be/[\w-]+',
    r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
]

# 일반 URL 패턴 (YouTube 제외)
URL_PATTERN = r'https?://(?!(?:www\.)?(?:youtube\.com|youtu\.be)/)[^\s<>"{}|\\^`\[\]]+'


CLASSIFIER_PROMPT = """You are an intent classifier. Classify the user's message into ONE intent.

INTENTS:
- ppt_generation: Create PowerPoint presentations, slides, PPT files
  Keywords: "PPT", "파워포인트", "프레젠테이션", "발표자료", "슬라이드로", "PT자료"
- visualization: Create charts, graphs, PDF documents, Word/DOCX documents, reports, data visualization
  Keywords: "차트", "그래프", "PDF로", "워드로", "Word로", "DOCX", "시각화", "막대", "라인", "파이", "보고서로 정리"
- xlsx: Create, modify, or manipulate Excel (XLSX) files
  NOTE: Analyzing uploaded xlsx content → "user_files". Creating/modifying xlsx → "xlsx"
- user_files: Questions about user's uploaded files or workspace documents
- web_search: Queries requiring up-to-date or factual information from the internet
  Topics: weather, news, stocks, market trends, industry analysis, company info, regulations
  IMPORTANT: Real-world topics, companies, industries, anything that changes over time → "web_search"
  IMPORTANT: "정리해줘" or "알려줘" combined with real-world topics = "web_search" (NOT "direct")
- corp_rag: Company internal documents (HR policies, safety guidelines), organization chart, general department staff lookup
  NOTE: "담당자" + IT/security keywords → "it_support". + accounting/finance → "acct_support"
- youtube: Contains YouTube URL
- it_support: IT help desk, IT VOC, security issues, VPN, printers, IT-domain staff lookup
  Systems: 쉐도우큐브, DRM, DLP, LFON, SAP GUI, Citrix, AD, 방화벽, 백신, 매체제어
- acct_support: Accounting/finance VOC, 세금계산서, SAP 전표, 결산, 예산, 자산, 경비 처리
  NOTE: "결산" (settlement) → "acct_support", NOT "approval"
  NOTE: "WA전표품의" is an approval FORM name → "approval", NOT "acct_support"
  Systems: SAP ERP, SAP FI/CO, 전자세금계산서, 법인카드, iCUBE
- mail: Check/search email inbox, sent mail, unread mail, view mail body, summarize, draft reply
- approval: Electronic approval queries - pending approvals, drafted documents, status, bottleneck
  Approval form names (양식명): WA전표품의, 품의서, 보고, 사전지출승인서, 예외처리 신청서, 인장 및 법인서류 요청서
- board: Search company bulletin boards, notices, announcements, posts
  NOTE: Board posts/notices → "board". Company policies/regulations (not posts) → "corp_rag"
- outline: Search or browse Outline Wiki documents, collections, recent wiki updates
  Keywords: "위키", "wiki", "outline", "아웃라인", "위키 문서", "위키에서"
  NOTE: "위키" explicitly mentioned → "outline". General company docs without "위키" → "corp_rag"
- clarify: The query asks to FIND a specific item/document/record, but NONE of the above intents match
  ONLY use as last resort when: no domain keywords, not a knowledge question, not how-to — purely "find this thing" with no clue where
- direct: General conversation, coding, translation, math, creative writing — no external info needed

CONTEXT:
- User has uploaded files: {has_files}
- Session has xlsx files: {has_session_xlsx}
- Workspace mode: {has_workspace}
- Workspace name: {workspace_name}
- Workspace description: {workspace_description}
- Workspace uploaded files: {workspace_file_names}
- Previous turn intent: {previous_intent}

CONVERSATION HISTORY (last few messages for context):
{conversation_context}

RULES:
1. PPT/PowerPoint/presentation → ALWAYS "ppt_generation"
2. Charts/graphs/PDF/visualization → ALWAYS "visualization"
3. xlsx: CREATE/MODIFY/FORMAT Excel → "xlsx". Analyzing content → "user_files"
   If has_session_xlsx=True AND modification request (수정, 편집, 서식, 추가, 삭제, 정리, 값 입력 등) → "xlsx"
   But: "파일 내용 요약/분석" + has_session_xlsx=True → "user_files" (READ request)
4. DISAMBIGUATION: When multiple intent keywords co-occur, the ACTION verb/target determines intent:
   - "전자결재 관련 게시글 찾아줘" → "board" (action=게시글 검색, 전자결재는 검색 주제)
   - "'전자결재 수정 확인 요청' 메일 확인해줘" → "mail" (action=메일 확인, 전자결재는 메일 제목)
   - "전자결재 결재 대기 건 확인해줘" → "approval" (action=결재 대기 확인)
   - "게시판에서 결재 관련 공지 찾아줘" → "board" (action=게시판 검색)
5. WORKSPACE-AWARE ROUTING (when has_workspace=True AND workspace has files):
   - Query topic MATCHES workspace domain → "user_files" (search workspace docs first)
   - Query topic UNRELATED to workspace → specialized intent (mail, web_search, etc.)
6. web_search: Real-world facts, companies, industries, current events → "web_search"
7. user_files: File content queries — only if has_files=True OR has_workspace=True
8. NEVER "user_files" if BOTH has_files=False AND has_workspace=False
9. NEVER "direct" for real-world facts, companies, or current information
10. FOLLOW-UP: If previous_intent is set and the current message is a follow-up to that conversation (e.g., referencing items from previous results, asking details, changing keyword), MAINTAIN the previous intent. Example: previous_intent=approval + "WA전표품의 3건 상세 확인" → "approval". previous_intent=mail + "근무지는?" → "mail"
11. CLARIFY: Last resort only — when the user wants to find a specific item/record but NO intent above fits. Never use for how-to, knowledge, or conversation questions.

WORKSPACE RULES (when has_workspace=True AND workspace has files):
- Workspace documents are the primary knowledge source
- Follow-up questions, corrections, accuracy complaints → "user_files"
- Only route to specialized intents when topic is CLEARLY outside workspace domain
- Only "direct" for tasks CLEARLY unrelated to documents (coding, translation, math)

EXAMPLES:
- "분기 실적 PPT 만들어줘" → ppt_generation
- "발표자료 슬라이드로 정리해줘" → ppt_generation
- "매출 막대 그래프로 보여줘" → visualization
- "이 데이터로 차트 그려줘" → visualization
- "이거 워드로 만들어줘" → visualization
- "Word 문서로 정리해줘" → visualization
- "이번달 2차전지 산업 동향 정리" → web_search
- "반도체 산업 전망 정리해줘" → web_search
- "마케팅 담당자 누구야?" → corp_rag
- "VPN 담당자 누구야?" → it_support
- "쉐도우큐브 담당자?" → it_support
- "세금계산서 담당자?" → acct_support
- "결산 담당자 누구야?" → acct_support
- "전자결재 관련 게시글 찾아줘" → board (게시글 검색, 전자결재는 주제)
- "게시판에서 전자결재 관련 내용 찾아줘" → board (게시판 검색)
- "'결재 반려 통보' 메일 찾아줘" → mail (메일 검색, 결재는 제목)
- "이 파일 서식 적용해줘" (has_session_xlsx=True) → xlsx
- "파일에 합계 행 추가해줘" (has_session_xlsx=True) → xlsx
- "파일 내용 분석해줘" (has_session_xlsx=True) → user_files
- "파일 내용 요약해줘" (has_files=True) → user_files
- "코드 리뷰해줘" → direct
- "이 문장 영어로 번역해줘" → direct
- "위키에서 VPN 문서 찾아줘" → outline
- "아웃라인 최근 문서 보여줘" → outline
- "OO 건 조회해줘" (no domain keyword at all) → clarify

USER MESSAGE: {message}

RESPONSE FORMAT:
- Respond with the PRIMARY intent, optionally followed by a FALLBACK intent separated by comma.
- Fallback = the next most likely search scope if the primary finds nothing.
- Only include fallback for search-type intents (approval, board, corp_rag, it_support, acct_support, web_search).
- Do NOT include fallback for: direct, ppt_generation, visualization, xlsx, youtube, mail, user_files, clarify, url_fetch.
- Examples: "approval,board" / "acct_support,web_search" / "direct" / "web_search,corp_rag"
No explanation."""


class IntentClassifier:
    """Haiku 기반 Intent 분류기"""

    def __init__(self):
        self._region_mgr = get_region_fallback_manager()
        self._was_fallback = self._region_mgr.is_fallback_active
        self.llm = self._create_llm()

    def _create_llm(self) -> ChatBedrockConverse:
        """현재 리전 상태에 맞는 LLM 인스턴스 생성"""
        config = get_orchestrator_config()
        effective_model_id = self._region_mgr.get_model_id(config.model_id)
        llm_kwargs = dict(
            model=effective_model_id,
            temperature=0.0,
            max_tokens=config.max_tokens,
        )
        if self._region_mgr.is_fallback_active:
            llm_kwargs["region_name"] = self._region_mgr.fallback_region
        return ChatBedrockConverse(**llm_kwargs)

    def _ensure_correct_region(self):
        """리전 상태가 바뀌었으면 LLM 재생성"""
        current_fallback = self._region_mgr.is_fallback_active
        if current_fallback != self._was_fallback:
            self._was_fallback = current_fallback
            self.llm = self._create_llm()
            print(f"[IntentClassifier] LLM recreated for region change (fallback={current_fallback})")

    def _quick_classify(self, message: str, context: RequestContext) -> Optional[Intent]:
        """
        규칙 기반 빠른 분류

        Step 1: 100% 확실한 패턴 (URL, 명시적 메일 액션)
        Step 2: 생성/산출물 인텐트 (차트, PPT — 자체 web search 보유)
        Step 3: 도메인 인텐트 키워드 스캔 (mail, approval, board, xlsx)
        Step 4: 판정 (2개 이상 → LLM, 1개 + workspace → LLM, 1개 → 즉시 반환)
        Step 5: Web search fallback (도메인에 안 걸렸을 때만)
        """
        # ========= Step 1: 100% 확실한 패턴 =========

        # YouTube URL (정규식 매칭으로 100% 확실)
        for pattern in YOUTUBE_PATTERNS:
            if re.search(pattern, message):
                return Intent.YOUTUBE

        # 일반 URL (YouTube 제외)
        if re.search(URL_PATTERN, message):
            return Intent.URL_FETCH

        # 명시적 메일 액션 ("메일 확인해줘", "메일 요약해줘" 등)
        # 단, 게시글/게시판 키워드가 함께 있으면 Step 3에서 multi-intent로 처리
        mail_enabled = os.environ.get("MAIL_WORKER_ENABLED", "true").lower() == "true"
        if mail_enabled:
            mail_action_pattern = r'메일\s*(내용|내역|본문)?\s*(확인|보여|검색|찾아|조회|알려|읽어|요약|답장|답신|회신|응답)'
            board_guard = r'(게시판|게시글|게시물|공지사항|사내\s?공지)'
            if re.search(mail_action_pattern, message, re.IGNORECASE) and not re.search(board_guard, message, re.IGNORECASE):
                print(f"[INTENT] Quick: explicit mail action → MAIL")
                return Intent.MAIL

        # ========= Step 2: 생성/산출물 인텐트 (차트, PPT 등) =========
        # 이 워커들은 tavily_search 도구를 자체 보유하므로,
        # "OO 데이터를 차트로 만들어줘" 같은 복합 요청도 단일 워커 내에서 처리 가능
        viz_pattern = r'(차트|그래프|시각화|막대.*그|라인.*그|파이.*그|꺾은선).{0,15}(만들|생성|그려|보여|작성|그리|표시)'
        viz_pattern2 = r'(만들|생성|그려|보여|작성|그리|표시).{0,15}(차트|그래프|시각화)'
        viz_pattern3 = r'(PDF로|pdf로|PDF\s?문서|보고서로\s?정리|워드로|Word로|word로|DOCX로|docx로|워드\s?문서|Word\s?문서)'
        if re.search(viz_pattern, message, re.IGNORECASE) or re.search(viz_pattern2, message, re.IGNORECASE) or re.search(viz_pattern3, message, re.IGNORECASE):
            print(f"[INTENT] Quick: visualization keyword → VISUALIZATION")
            return Intent.VISUALIZATION

        ppt_pattern = r'(PPT|ppt|파워포인트|프레젠테이션|발표\s?자료|슬라이드로|PT\s?자료)'
        if re.search(ppt_pattern, message, re.IGNORECASE):
            print(f"[INTENT] Quick: PPT keyword → PPT_GENERATION")
            return Intent.PPT_GENERATION

        # ========= Step 3: 도메인 인텐트 키워드 스캔 =========
        workspace_has_files = context.get("workspace_has_files", False)
        matched_intents: List[Intent] = []

        # Mail keywords
        if mail_enabled:
            mail_keywords = r'(메일|이메일|e-?mail|받은\s?편지|보낸\s?편지|편지함|안\s?읽은\s?메일|새\s?메일|수신함|발신함|inbox|sent\s?mail|mailbox|unread|메일\s?요약|메일\s?답장|메일\s?회신)'
            if re.search(mail_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.MAIL)

        # Approval keywords (결재 양식명 포함: 전표품의, 품의서, 승인서 등)
        approval_enabled = os.environ.get("APPROVAL_WORKER_ENABLED", "true").lower() == "true"
        if approval_enabled:
            approval_keywords = r'(결재|기안|상신|전자결재|결재\s?대기|결재\s?완료|결재함|기안함|반려|재기안|결재선|합의|승인\s?문서|결재\s?건|전표품의|품의서|사전지출\s?승인|예외처리\s?신청)'
            if re.search(approval_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.APPROVAL)

        # Board keywords
        board_enabled = os.environ.get("BOARD_WORKER_ENABLED", "true").lower() == "true"
        if board_enabled:
            board_keywords = r'(게시판|공지사항|게시글|게시물|사내\s?공지|전사\s?공지|전사\s?게시)'
            if re.search(board_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.BOARD)

        # Outline Wiki keywords
        outline_enabled = os.environ.get("OUTLINE_WORKER_ENABLED", "true").lower() == "true"
        if outline_enabled:
            outline_keywords = r'(위키|wiki|outline|아웃라인|위키\s?문서|위키에서)'
            if re.search(outline_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.OUTLINE)

        # XLSX keywords (두 가지 패턴)
        xlsx_enabled = os.environ.get("XLSX_WORKER_ENABLED", "true").lower() == "true"
        if xlsx_enabled:
            # 패턴 1: "엑셀" 키워드 + 액션 동사
            xlsx_pattern = r'(엑셀|excel|xlsx|xls|스프레드시트).{0,20}(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내)'
            xlsx_pattern2 = r'(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내).{0,20}(엑셀|excel|xlsx|xls|스프레드시트)'
            if re.search(xlsx_pattern, message, re.IGNORECASE) or re.search(xlsx_pattern2, message, re.IGNORECASE):
                matched_intents.append(Intent.XLSX)
            # 패턴 2: 세션에 xlsx 파일 존재 + 수정/서식 키워드 (엑셀 키워드 없이)
            elif context.get("has_session_xlsx", False):
                xlsx_modify_keywords = r'(수정|편집|변경|고치|바꿔|바꾸|업데이트|update|서식|포맷|테두리|배경색|글꼴|볼드|bold|정렬|색상|수식|formula|합계|sum|필터|filter|셀\s?병합|merge|행\s?추가|열\s?추가|행\s?삭제|열\s?삭제|데이터\s?추가|데이터\s?입력|값\s?입력|값\s?넣|값\s?변경|값\s?수정|내용\s?변경|내용\s?수정|시트\s?추가|시트\s?삭제|피벗|pivot|채우|넣어|입력|작성|정리|다듬)'
                if re.search(xlsx_modify_keywords, message, re.IGNORECASE):
                    matched_intents.append(Intent.XLSX)

        # ========= Step 4: 판정 =========
        if len(matched_intents) >= 2:
            print(f"[INTENT] Quick: multiple intents matched {[m.value for m in matched_intents]}, deferring to LLM")
            return None
        elif len(matched_intents) == 1:
            if workspace_has_files:
                print(f"[INTENT] Quick: {matched_intents[0].value} matched but workspace has files, deferring to LLM")
                return None
            return matched_intents[0]

        # ========= Step 5: Web search fallback =========
        # 도메인 인텐트에 걸리지 않았을 때만 체크 (도메인 키워드와 false overlap 방지)
        if not workspace_has_files:
            # 시간 + 정보 키워드 조합
            time_keywords = r'(이번\s?달|이번\s?주|올해|최근|최신|금일|오늘|어제|지난\s?달|지난\s?주|2026년|2025년|현재)'
            info_keywords = r'(동향|트렌드|뉴스|소식|현황|상황|이슈|전망|시황|시세|주가|환율|날씨|실적|실시간)'
            if re.search(time_keywords, message) and re.search(info_keywords, message):
                return Intent.WEB_SEARCH

            # 주식/금융 키워드
            finance_keywords = r'(주가|주식|시세|환율|증권|거래세|코스피|코스닥|나스닥|S&P|배당|공모주|IPO|시가총액|PER|PBR|EPS)'
            if re.search(finance_keywords, message):
                return Intent.WEB_SEARCH

            # 산업/시장 동향 키워드
            industry_keywords = r'(동향|트렌드|전망|시황|산업\s?.+\s?정리|시장\s?.+\s?분석|업계\s?.+\s?현황)'
            if re.search(industry_keywords, message):
                return Intent.WEB_SEARCH

        # ========= Step 6: LLM 위임 =========
        return None

    def _parse_intent(self, intent_str: str) -> Optional[Intent]:
        """문자열을 Intent enum으로 변환"""
        for intent in Intent:
            if intent.value == intent_str.strip():
                return intent
        return None

    def _apply_overrides(self, intent: Intent, context: RequestContext) -> Intent:
        """워크스페이스 등 컨텍스트 기반 인텐트 오버라이드"""
        # 방어 로직: user_files인데 검색할 파일이 없으면 DIRECT로
        if intent == Intent.USER_FILES:
            has_files = context.get("has_files", False)
            has_workspace = bool(context.get("workspace_uuid") or context.get("workspace_id"))
            workspace_has_files = context.get("workspace_has_files", False)
            if not has_files and (not has_workspace or not workspace_has_files):
                print(f"[INTENT] Override: user_files -> direct (no session files, workspace_has_files={workspace_has_files})")
                return Intent.DIRECT

        # 워크스페이스에 파일이 있고, 정보 검색 의도면 → 워크스페이스 문서 우선 검색
        workspace_has_files = context.get("workspace_has_files", False)
        if workspace_has_files and intent in (Intent.CORP_RAG, Intent.IT_SUPPORT, Intent.ACCT_SUPPORT):
            print(f"[INTENT] Override: {intent.value} -> user_files (workspace has files, search workspace docs first)")
            return Intent.USER_FILES

        # 워크스페이스에 파일이 있는데 direct로 분류되면 → user_files로 오버라이드
        if workspace_has_files and intent == Intent.DIRECT:
            print(f"[INTENT] Override: direct -> user_files (workspace has files, ensure document-grounded response)")
            return Intent.USER_FILES

        return intent

    async def classify(self, message: str, context: RequestContext, message_history: Optional[List[Dict]] = None, previous_intent: Optional[str] = None) -> Tuple[Intent, Optional[Intent]]:
        """
        의도 분류 (규칙 기반 → LLM fallback)

        Args:
            message: 사용자 메시지
            context: 요청 컨텍스트
            message_history: 이전 대화 히스토리 (LLM 분류 시 맥락 참고)
            previous_intent: 이전 턴의 분류된 인텐트 (follow-up 판단용)

        Returns:
            (primary_intent, fallback_intent) 튜플
            - quick_classify 결과는 fallback=None (이미 확실한 패턴)
            - LLM 분류 시 fallback 포함 가능 (예: "approval,board")
        """
        # 1. 규칙 기반 빠른 분류 시도
        quick_result = self._quick_classify(message, context)
        if quick_result:
            print(f"[INTENT] Quick classified: {quick_result.value}")
            return (quick_result, None)

        # 2. LLM 기반 분류
        try:
            # 대화 히스토리에서 최근 맥락 구성 (최대 4개 메시지)
            conversation_context = "No previous messages."
            if message_history:
                recent = message_history[-4:]
                lines = []
                for msg in recent:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if content:
                        lines.append(f"  {role}: {content[:150]}")
                if lines:
                    conversation_context = "\n".join(lines)

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
                has_session_xlsx=context.get("has_session_xlsx", False),
                has_workspace=has_workspace,
                workspace_name=workspace_name,
                workspace_description=workspace_description,
                workspace_file_names=workspace_file_names,
                conversation_context=conversation_context,
                previous_intent=previous_intent or "N/A (first message)",
            )

            # 리전 상태 변경 시 LLM 재생성
            self._ensure_correct_region()

            response = await self.llm.ainvoke([
                SystemMessage(content="You are a precise intent classifier."),
                HumanMessage(content=prompt),
            ])

            # 토큰 사용량 로깅
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                try:
                    from app.services.token_usage_service import get_token_usage_service
                    um = response.usage_metadata
                    asyncio.create_task(get_token_usage_service().log(
                        caller="intent_classifier",
                        model_id=self.llm.model_id if hasattr(self.llm, "model_id") else "haiku",
                        input_tokens=um.get("input_tokens", 0),
                        output_tokens=um.get("output_tokens", 0),
                        session_id=context.get("session_id") if context else None,
                        user_id=context.get("user_id") if context else None,
                    ))
                except Exception:
                    pass

            raw = response.content.strip().lower()
            print(f"[INTENT] LLM classified: {raw}")

            # "approval,board" 또는 "direct" 형식 파싱
            parts = [p.strip() for p in raw.split(",")]
            primary = self._parse_intent(parts[0])
            secondary = self._parse_intent(parts[1]) if len(parts) > 1 else None

            if not primary:
                print(f"[INTENT] Unknown primary intent '{parts[0]}', falling back to DIRECT")
                return (Intent.DIRECT, None)

            # 오버라이드 적용 (primary만 — secondary는 원본 유지)
            primary = self._apply_overrides(primary, context)

            # secondary가 primary와 같으면 무의미
            if secondary == primary:
                secondary = None

            print(f"[INTENT] Final: primary={primary.value}, fallback={secondary.value if secondary else 'None'}")
            return (primary, secondary)

        except Exception as e:
            print(f"[INTENT] Classification error: {e}, falling back to DIRECT")
            return (Intent.DIRECT, None)


# 싱글톤
_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """IntentClassifier 싱글톤 반환"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
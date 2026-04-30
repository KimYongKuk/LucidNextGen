"""Intent Classifier - Haiku 기반 빠른 의도 분류"""

import os
import re
import asyncio
from typing import Optional, List, Dict, Tuple
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_config import get_orchestrator_config
from app.core.region_fallback import get_region_fallback_manager
from app.agents.routing_guide import DOMAIN_ROUTING_GUIDE
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
- xlsx: Create, modify, or manipulate Excel (XLSX) files
  NOTE: Analyzing uploaded xlsx content → "user_files". Creating/modifying xlsx → "xlsx"
- user_files: Questions about user's uploaded files or workspace documents
- web_search: Queries requiring up-to-date or factual information from the internet
  Topics: weather, news, stocks, market trends, industry analysis, company info, regulations
  IMPORTANT: Real-world topics, companies, industries, anything that changes over time → "web_search"
  IMPORTANT: "정리해줘" or "알려줘" combined with real-world topics = "web_search" (NOT "direct")
- corp_rag: HR (인사) and Safety/Environment (안전환경) regulations/policies ONLY, organization chart, general department staff lookup
  See the **DOMAIN ROUTING** section below for domain-to-worker mapping and exclusivity rules.
  NOTE: "담당자" + IT/security keywords → "it_support". + accounting/finance → "acct_support"
- youtube: Contains YouTube URL
- it_support: IT help desk, IT VOC, security issues, VPN, printers, IT-domain staff lookup
  Systems: 쉐도우큐브, DRM, DLP, LFON, SAP GUI, Citrix, AD, 방화벽, 백신, 매체제어
  ALSO HANDLES (destructive account actions, 2-step confirm/execute):
    - OTP 초기화/재등록/재설정 (휴대폰 교체 등)
    - 그룹웨어(LFON) 비밀번호 초기화/리셋
    - SAP 비밀번호 초기화 (reset_sap_password)
    - 메일함 용량 증설/확장
  IMPORTANT: "비밀번호 초기화"는 모호하면 → it_support (Worker가 SAP/LFON 재질문)
  IMPORTANT: "OTP", "메일 용량", "메일함 증설" 등 명시 키워드 → 즉시 it_support
- acct_support: Accounting/finance VOC, 세금계산서, SAP 전표, 결산, 예산, 자산, 경비 처리
  NOTE: "결산" (settlement) → "acct_support", NOT "approval"
  NOTE: "WA전표품의" is an approval FORM name → "approval", NOT "acct_support"
  Systems: SAP ERP, SAP FI/CO, 전자세금계산서, 법인카드, iCUBE
- mail: Check/search email inbox, sent mail, unread mail, view mail body, summarize, draft reply
- approval: Electronic approval queries - pending approvals, drafted documents, status, bottleneck
  Approval form names (양식명): WA전표품의, 품의서, 보고, 사전지출승인서, 예외처리 신청서, 인장 및 법인서류 요청서
- board: Search company bulletin boards, notices, announcements, posts
  NOTE: Board posts/notices → "board". Company policies/regulations (not posts) → "corp_rag"
- outline: Search or browse L&F Wiki documents, collections, recent wiki updates, OR publish uploaded files to wiki
  Keywords: "위키", "wiki", "outline", "아웃라인", "위키 문서", "위키에서"
  Examples: "위키에서 보안 정책 찾아줘", "이 파일 위키에 올려줘", "PDF를 위키 문서로 만들어줘"
  NOTE: "위키" explicitly mentioned → "outline". General company docs without "위키" → "corp_rag"
- reservation: Meeting room/asset reservation - search, book, cancel reservations
  Keywords: "예약", "회의실", "빈 회의실", "예약 현황", "예약 등록", "예약 취소", "회의룸", "C/R"
  Examples: "내 예약 보여줘", "내일 본사 빈 회의실 있어?", "오후 2시에 회의실 잡아줘", "예약 취소해줘"
  NOTE: "구독 예약", "식당 예약" 등 외부 예약은 해당 없음 → "direct" or "web_search"
- calendar: Calendar schedule management - view, create, delete events on groupware calendar
  Keywords: "일정", "캘린더", "스케줄", "빈 시간", "내 일정", "오늘 일정", "이번 주 일정"
  Examples: "오늘 일정 보여줘", "내일 오후에 미팅 잡아줘", "이번 주 일정 확인", "캘린더에 등록해줘", "일정 삭제해줘"
  NOTE: "일정/캘린더/스케줄" → calendar. "회의실 예약"만 단독 → reservation.
  IMPORTANT: 일정 + 회의실 예약이 함께 언급되면 → calendar (CalendarWorker가 회의실 예약도 처리 가능)
- nas: Browse, search, download files from company NAS (shared storage)
  Keywords: "NAS", "공유폴더", "부서간공유", "데이터서버", "파일서버", "공유드라이브"
  Examples: "NAS에서 AI교육 자료 찾아줘", "부서간공유에 있는 파일 보여줘", "공유폴더에서 PDF 다운받아줘"
  NOTE: "파일 업로드/분석" (user's uploaded files) → "user_files". NAS shared storage → "nas"
- clarify: The query asks to FIND a specific item/document/record, but NONE of the above intents match
  ONLY use as last resort when: no domain keywords, not a knowledge question, not how-to — purely "find this thing" with no clue where
- direct: General conversation, coding, translation, math, creative writing — no external info needed

{domain_routing_guide}

CONTEXT:
- User has uploaded files: {has_files}
- Session has xlsx files: {has_session_xlsx}
- Workspace mode: {has_workspace}
- Workspace name: {workspace_name}
- Workspace description: {workspace_description}
- Workspace uploaded files: {workspace_file_names}
- Workspace instructions (purpose): {workspace_instructions}
- Previous turn intent: {previous_intent}

CONVERSATION HISTORY (last few messages for context):
{conversation_context}

RULES:
1. PPT/PowerPoint/presentation: ONLY "ppt_generation" when user explicitly requests CREATING/MAKING a PPT.
   "PPT 만들어줘", "발표자료 작성해줘" → "ppt_generation"
   "PPT에 대해 알려줘", "PPT 내용 분석해줘", "발표 준비 어떻게 해?" → "direct" (NOT ppt_generation)
   KEY: The user must express intent to CREATE a file. Mentioning PPT alone is NOT enough.
2. Charts/graphs/PDF/DOCX/Word requests → "direct" (shared tools handle visualization)
   IMPORTANT: "워드로 만들어줘", "PDF로 정리해줘" → "direct" (DirectWorker has shared doc tools)
   Do NOT route to specialized workers for PDF/DOCX/chart creation.
3. xlsx: ONLY "xlsx" when user explicitly requests CREATING or MODIFYING an Excel file.
   "엑셀로 만들어줘", "엑셀 파일 생성해줘" → "xlsx"
   If has_session_xlsx=True AND modification request (수정, 편집, 서식, 추가, 삭제, 값 입력 등) → "xlsx"
   But: "파일 내용 요약/분석" + has_session_xlsx=True → "user_files" (READ request)
   "엑셀로 정리해줘" without has_session_xlsx → "direct" (just text formatting, not file creation)
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

WORKSPACE RULES (when has_workspace=True):
- When workspace has files: documents are the primary knowledge source
- Follow-up questions, corrections, accuracy complaints → "user_files"
- Only route to specialized intents when topic is CLEARLY outside workspace domain
- Only "direct" for tasks CLEARLY unrelated to documents (coding, translation, math)
- WORKSPACE INSTRUCTIONS ROUTING (when workspace_instructions is provided):
  - Instructions describe the workspace's PRIMARY purpose and domain
  - If user message ALIGNS with workspace purpose → route to the matching specialized intent
  - If user message is CLEARLY UNRELATED to workspace purpose → ignore instructions, classify by message alone
  - Examples:
    - Instructions: "전자결재 시스템에서 문서 검색" + Message: "주간보고 정리해줘" → approval (aligned)
    - Instructions: "전자결재 시스템에서 문서 검색" + Message: "오늘 날씨?" → web_search (unrelated)
    - Instructions: "메일함 자동 탐지" + Message: "실행" → mail (aligned)
    - Instructions: "번역 전문가" + Message: "이 문장 번역해줘" → direct (no external tool needed)

EXAMPLES:
- "분기 실적 PPT 만들어줘" → ppt_generation (explicit creation request)
- "발표자료 슬라이드로 정리해줘" → ppt_generation (explicit creation request)
- "PPT 잘 만드는 법 알려줘" → direct (knowledge question, NOT creation)
- "발표 준비 어떻게 해?" → direct (advice, NOT creation)
- "PPT 내용 검토해줘" → user_files (if has_files=True, analyzing uploaded PPT)
- "매출 막대 그래프로 보여줘" → direct
- "이 데이터로 차트 그려줘" → direct
- "이거 워드로 만들어줘" → direct
- "엑셀로 정리해줘" → direct (text formatting, NOT file creation)
- "엑셀 파일 하나 만들어줘" → xlsx (explicit creation)
- "프로세스 플로우차트로 보여줘" → direct
- "이번달 2차전지 산업 동향 정리" → web_search
- "반도체 산업 전망 정리해줘" → web_search
- "마케팅 담당자 누구야?" → corp_rag
- "VPN 담당자 누구야?" → it_support
- "쉐도우큐브 담당자?" → it_support
- "내 OTP 초기화해줘" → it_support
- "OTP 재등록 해야돼" → it_support
- "그룹웨어 비밀번호 초기화" → it_support
- "LFON 로그인 비번 리셋해줘" → it_support
- "SAP 비밀번호 초기화" → it_support
- "메일 용량 늘려줘" → it_support
- "메일함 증설해줘" → it_support
- "받은편지함이 꽉 찼어" → it_support
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
- "내 예약 보여줘" → reservation
- "내일 본사 빈 회의실 있어?" → reservation
- "오후 2시에 회의실 잡아줘" → reservation
- "예약 취소해줘" → reservation
- "오늘 일정 보여줘" → calendar
- "이번 주 일정 확인해줘" → calendar
- "내일 오후에 미팅 잡아줘" → calendar
- "캘린더에서 일정 삭제해줘" → calendar
- "NAS에서 교육 자료 찾아줘" → nas
- "부서간공유에 있는 파일 보여줘" → nas
- "공유폴더에서 PDF 다운받아줘" → nas
- "OO 건 조회해줘" (no domain keyword at all) → clarify

USER MESSAGE: {message}

RESPONSE FORMAT:
- Respond with the PRIMARY intent, optionally followed by a FALLBACK intent separated by comma.
- Fallback = the next most likely search scope if the primary finds nothing.
- Only include fallback for search-type intents (approval, board, corp_rag, it_support, acct_support, web_search).
- Do NOT include fallback for: direct, ppt_generation, xlsx, youtube, mail, user_files, clarify, url_fetch.
- Examples: "approval,board" / "acct_support,web_search" / "direct" / "web_search,corp_rag"
No explanation."""


class IntentClassifier:
    """Haiku 기반 Intent 분류기"""

    def __init__(self):
        self._region_mgr = get_region_fallback_manager()
        self._was_fallback = self._region_mgr.is_fallback_active
        self.llm = self._create_llm()

    def _create_llm(self) -> ChatBedrockConverse:
        """현재 프로필 상태에 맞는 LLM 인스턴스 생성"""
        config = get_orchestrator_config()
        effective_model_id = self._region_mgr.get_model_id(config.model_id)
        return ChatBedrockConverse(
            model=effective_model_id,
            temperature=0.0,
            max_tokens=config.max_tokens,
        )

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
        # URL이 데이터의 일부(테이블, 예시)가 아니라 분석/조회 대상인 경우에만 URL_FETCH
        # - URL이 3개 이상 → 데이터 목록일 가능성 높음 → LLM에 위임
        # - 문서 생성 동사(만들어줘, 생성, 변환 등)가 있으면 → URL 분석이 아님
        url_matches = re.findall(URL_PATTERN, message)
        if url_matches:
            doc_action = r'(만들|생성|작성|변환|정리해|워드|word|docx|pdf|PDF|엑셀|excel|ppt|PPT)'
            if len(url_matches) <= 2 and not re.search(doc_action, message, re.IGNORECASE):
                return Intent.URL_FETCH

        # 업로드 파일 명시 참조 + 파일 존재 → USER_FILES (다른 도메인 키워드보다 우선)
        # 단, 위키 키워드가 함께 있으면 OUTLINE으로 넘김 (파일→위키 게시 시나리오)
        has_files = context.get("has_files", False)
        if has_files:
            upload_file_ref = r'(업로드\s?한?\s?파일|올린\s?파일|첨부\s?파일|위\s?파일|해당\s?파일|이\s?파일|그\s?파일|방금\s?파일)'
            wiki_guard = r'(위키|wiki|outline|아웃라인)'
            if re.search(upload_file_ref, message, re.IGNORECASE):
                if re.search(wiki_guard, message, re.IGNORECASE):
                    print(f"[INTENT] Quick: file reference + wiki keyword → OUTLINE")
                    return Intent.OUTLINE
                print(f"[INTENT] Quick: explicit file reference + has_files → USER_FILES")
                return Intent.USER_FILES

            # 파일 명시 없이 분석/요약 등 파일 작업 키워드만 있는 경우
            # "분석해줘", "요약해줘", "정리해줘", "알려줘" 등 단독 요청 → 업로드 파일 우선
            file_action_keywords = r'(분석|요약|정리|설명|내용|읽어|확인|살펴|검토|리뷰|비교|통계|데이터)'
            if re.search(file_action_keywords, message, re.IGNORECASE):
                print(f"[INTENT] Quick: has_files + file action keyword → USER_FILES")
                return Intent.USER_FILES

        # 명시적 메일 액션 ("메일 확인해줘", "메일 요약해줘" 등)
        # 단, 게시글/게시판 키워드가 함께 있으면 Step 3에서 multi-intent로 처리
        mail_enabled = os.environ.get("MAIL_WORKER_ENABLED", "true").lower() == "true"
        if mail_enabled:
            mail_action_pattern = r'메일\s*(내용|내역|본문)?\s*(확인|보여|검색|찾아|조회|알려|읽어|요약|답장|답신|회신|응답)'
            board_guard = r'(게시판|게시글|게시물|공지사항|사내\s?공지)'
            if re.search(mail_action_pattern, message, re.IGNORECASE) and not re.search(board_guard, message, re.IGNORECASE):
                print(f"[INTENT] Quick: explicit mail action → MAIL")
                return Intent.MAIL

        # ========= Step 2: 생성/산출물 인텐트 (PPT 등) =========
        # visualization 인텐트 제거: 차트/PDF/DOCX는 공유 도구로 어떤 에이전트든 직접 생성 가능
        # SVG 인포그래픽/다이어그램은 모든 에이전트가 인라인 SVG로 생성 가능
        # PPT: 키워드 + 생성 동사가 함께 있어야만 PPT_GENERATION
        # "PPT 내용 정리해줘" → direct, "PPT 만들어줘" → ppt_generation
        ppt_keyword = r'(PPT|ppt|파워포인트|프레젠테이션|발표\s?자료|슬라이드로|PT\s?자료)'
        ppt_create_verb = r'(만들|생성|작성|제작|구성|정리해\s?줘|뽑아|변환)'
        if re.search(ppt_keyword, message, re.IGNORECASE):
            if re.search(ppt_create_verb, message, re.IGNORECASE):
                print(f"[INTENT] Quick: PPT keyword + create verb → PPT_GENERATION")
                return Intent.PPT_GENERATION
            else:
                print(f"[INTENT] Quick: PPT keyword without create verb → defer to LLM")
                # 생성 동사 없이 PPT 언급만 → LLM에 위임 (분석/질문일 수 있음)

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

        # L&F Wiki keywords
        outline_enabled = os.environ.get("OUTLINE_WORKER_ENABLED", "true").lower() == "true"
        if outline_enabled:
            outline_keywords = r'(위키|wiki|outline|아웃라인|위키\s?문서|위키에서)'
            if re.search(outline_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.OUTLINE)

        # Reservation keywords
        reservation_enabled = os.environ.get("RESERVATION_WORKER_ENABLED", "true").lower() == "true"
        if reservation_enabled:
            reservation_keywords = r'(회의실|회의\s?룸|C/?R\d|예약\s?(현황|등록|취소|조회|목록|내역)|빈\s?회의실|내\s?예약|예약\s?잡아|예약\s?해줘)'
            if re.search(reservation_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.RESERVATION)

        # Calendar keywords
        calendar_enabled = os.environ.get("CALENDAR_WORKER_ENABLED", "true").lower() == "true"
        if calendar_enabled:
            calendar_keywords = r'(캘린더|일정\s?(조회|등록|삭제|추가|확인)|내\s?일정|오늘\s?일정|이번\s?주\s?일정|다음\s?주\s?일정|빈\s?시간|스케줄|일정\s?잡아|일정\s?만들|일정\s?넣어|일정\s?잡아줘)'
            if re.search(calendar_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.CALENDAR)

        # IT Support - 계정 관리 destructive 액션 키워드 (즉시 분류, 매우 명확)
        # OTP 초기화, 비밀번호 리셋, 메일 용량 증설 등은 반드시 ITSupportWorker로 라우팅
        # (ITSupportWorker에서 2-step confirm/execute 패턴으로 안전 처리)
        it_account_pattern = r'(OTP.{0,10}(초기화|재등록|재설정|리셋)|' \
                             r'(그룹웨어|LFON|SAP|로그인)?\s*비밀번호.{0,5}(초기화|리셋|재설정)|' \
                             r'(메일|받은\s?편지함|메일함).{0,5}(용량|증설|확장|늘려)|' \
                             r'메일.{0,5}용량.{0,5}(늘려|증설|확장|부족))'
        if re.search(it_account_pattern, message, re.IGNORECASE):
            print(f"[INTENT] Quick: IT account management keyword → IT_SUPPORT")
            return Intent.IT_SUPPORT

        # NAS keywords
        nas_enabled = os.environ.get("NAS_WORKER_ENABLED", "true").lower() == "true"
        if nas_enabled:
            nas_keywords = r'(NAS|nas|공유\s?폴더|부서간\s?공유|데이터\s?서버|파일\s?서버|시놀로지|synology|공유\s?드라이브|NAS에서|NAS\s?파일)'
            if re.search(nas_keywords, message, re.IGNORECASE):
                matched_intents.append(Intent.NAS)

        # XLSX keywords (두 가지 패턴)
        xlsx_enabled = os.environ.get("XLSX_WORKER_ENABLED", "true").lower() == "true"
        if xlsx_enabled:
            # 패턴 1: "엑셀" 키워드 + 액션 동사
            xlsx_pattern = r'(엑셀|excel|xlsx|xls|스프레드시트).{0,20}(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내)'
            xlsx_pattern2 = r'(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내).{0,20}(엑셀|excel|xlsx|xls|스프레드시트)'
            if re.search(xlsx_pattern, message, re.IGNORECASE) or re.search(xlsx_pattern2, message, re.IGNORECASE):
                matched_intents.append(Intent.XLSX)
            # 패턴 2 제거: "엑셀" 키워드 없이 세션 xlsx + 수정 키워드만으로 판단하는 것은
            # 오분류 위험이 높아 LLM 분류에 위임 (예: 이미지 첨부 + "채워줘" → xlsx로 오분류)

        # ========= Step 4: 판정 =========
        # calendar + reservation 동시 매칭 → calendar 우선
        # (CalendarWorker가 회의실 예약 도구도 보유하므로 통합 처리 가능)
        if set(matched_intents) == {Intent.CALENDAR, Intent.RESERVATION}:
            print(f"[INTENT] Quick: calendar+reservation both matched → calendar (can handle both)")
            return Intent.CALENDAR

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

        # 워크스페이스 컨텍스트(파일, instructions)는 BaseWorker.build_system_prompt에서
        # 모든 워커에 자동 주입됨. 인텐트를 강제 변경할 필요 없음.
        # (이전: workspace_has_files and direct → user_files 강제 오버라이드 — 시각화 등 비검색 요청 깨짐)

        # NOTE: corp_rag/it_support/acct_support 등 전문 인텐트는 더 이상 user_files로
        # 강제 오버라이드하지 않음. orchestrator에서 workspace 모드일 때
        # user_files를 1순위로 실행 후 NO_RESULTS 시 원래 인텐트 워커로 폴백.

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

        # 1.5. Follow-up 규칙: quick_classify 미매칭 + previous_intent → 이전 인텐트 유지
        # quick_classify가 새 도메인 키워드를 잡지 못했다면, 명확한 주제 전환이 아님
        # → 이전 대화의 follow-up으로 간주하고 이전 인텐트 유지 (LLM 분류 생략)
        if previous_intent and previous_intent != "direct":
            prev = self._parse_intent(previous_intent)
            if prev:
                print(f"[INTENT] Follow-up: no new domain keyword + previous={previous_intent} → {prev.value}")
                return (prev, None)

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
            workspace_instructions = "N/A"
            has_workspace = bool(context.get("workspace_uuid") or context.get("workspace_id"))
            if has_workspace:
                workspace_name = context.get("workspace_name") or "N/A"
                workspace_description = context.get("workspace_description") or "N/A"
                file_names_list = context.get("workspace_file_names", [])
                workspace_file_names = ", ".join(file_names_list) if file_names_list else "None"
                # 인스트럭션 앞 500자만 분류기에 전달 (목적 파악용)
                raw_instructions = context.get("workspace_instructions") or ""
                if raw_instructions:
                    workspace_instructions = raw_instructions[:500]

            prompt = CLASSIFIER_PROMPT.format(
                domain_routing_guide=DOMAIN_ROUTING_GUIDE,
                message=message,
                has_files=context.get("has_files", False),
                has_session_xlsx=context.get("has_session_xlsx", False),
                has_workspace=has_workspace,
                workspace_name=workspace_name,
                workspace_description=workspace_description,
                workspace_file_names=workspace_file_names,
                workspace_instructions=workspace_instructions,
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
            # throttling 시 inference profile prefix 전환 후 재시도
            from app.utils.bedrock_exceptions import is_throttling_error
            if is_throttling_error(e):
                from app.core.region_fallback import swap_inference_prefix
                print(f"[INTENT] Throttled, swapping inference profile prefix and retrying...")
                self._region_mgr.activate_fallback()
                # 사용자 알림용 throttling 시각 기록 (프론트 배너 트리거)
                self._region_mgr.record_throttling()
                self.llm = self._create_llm()
                try:
                    response = await self.llm.ainvoke([
                        SystemMessage(content="You are a precise intent classifier."),
                        HumanMessage(content=prompt),
                    ])
                    raw = response.content.strip().lower()
                    print(f"[INTENT] LLM classified (fallback profile): {raw}")
                    parts = [p.strip() for p in raw.split(",")]
                    primary = self._parse_intent(parts[0])
                    secondary = self._parse_intent(parts[1]) if len(parts) > 1 else None
                    if not primary:
                        return (Intent.DIRECT, None)
                    primary = self._apply_overrides(primary, context)
                    if secondary == primary:
                        secondary = None
                    return (primary, secondary)
                except Exception as e2:
                    print(f"[INTENT] Fallback profile also failed: {e2}")
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
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
- xlsx: Create, modify, or manipulate Excel (XLSX) files. Editing cells, formatting, formulas, charts in Excel, pivot tables, creating new spreadsheets
  Keywords: "엑셀", "excel", "xlsx", "스프레드시트", "워크시트", "셀", "행 추가", "열 삭제", "서식", "피벗 테이블", "수식"
  NOTE: If user asks about analyzing uploaded xlsx file content → "user_files". If user wants to CREATE or MODIFY an xlsx file → "xlsx"
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
- mail: Check/search user's email inbox, sent mail, unread mail, mail folders, view full mail body, summarize mail content, draft reply
  Keywords: "메일", "이메일", "email", "받은편지함", "보낸편지함", "편지함", "안읽은 메일", "새 메일", "메일 검색", "수신함", "발신함", "inbox", "mailbox", "메일 본문", "메일 요약", "메일 답장", "답장 초안", "회신"
- approval: Electronic approval document queries - check pending approvals, drafted documents, approval status, bottleneck analysis, department documents
  Keywords: "결재", "기안", "상신", "전자결재", "결재 대기", "결재 완료", "결재함", "기안함", "참조함", "반려", "재기안", "결재선", "합의", "승인 문서", "결재 건"
  NOTE: "결산" (settlement/closing) is accounting → use "acct_support", NOT "approval"
- board: Search company bulletin boards (다우오피스), notices, announcements, posts
  Keywords: "게시판", "공지", "공지사항", "게시글", "게시물", "사내 공지", "전사 공지", "사내 게시판", "전사 게시판", "게시판 검색"
  Topics: company notices, board posts, announcements, bulletin board search, finding specific posts
  NOTE: If user wants to search internal bulletin board posts or company notices → "board". If user asks about company policies/regulations (not board posts) → "corp_rag"
- direct: General conversation, coding help, translation, math, creative writing, no tools needed
  ONLY use "direct" for tasks that do NOT require any external information (e.g., pure conversation, coding, translation, math)

CONTEXT:
- User has uploaded files: {has_files}
- Session has xlsx files: {has_session_xlsx}
- Workspace mode: {has_workspace}
- Workspace name: {workspace_name}
- Workspace description: {workspace_description}
- Workspace uploaded files: {workspace_file_names}

PRIORITY RULES (IMPORTANT - follow this order):
1. ppt_generation: If user asks for PPT/PowerPoint/presentation/slides → ALWAYS "ppt_generation"
2. visualization: If user asks for charts/graphs/PDF/visualization → ALWAYS "visualization" (regardless of file context)
2.5. xlsx: If user asks to CREATE, MODIFY, FORMAT, or MANIPULATE Excel/XLSX files → ALWAYS "xlsx"
     NOTE: "엑셀 파일 분석해줘" (analyzing content) → "user_files". "엑셀 만들어줘" (creating/modifying) → "xlsx"
     IMPORTANT: If has_session_xlsx=True AND user asks to FORMAT, MODIFY, EDIT, UPDATE, or CHANGE the uploaded file → "xlsx" (even without explicit "엑셀" keyword)
     ANY modification request (수정, 편집, 변경, 고치, 바꿔, 업데이트, 추가, 삭제, 정리, 다듬, 값 입력/넣기) + has_session_xlsx=True → "xlsx"
     Examples: "이 파일 서식 적용해줘" + has_session_xlsx=True → "xlsx". "파일에 합계 추가해줘" + has_session_xlsx=True → "xlsx". "파일 수정해줘" + has_session_xlsx=True → "xlsx". "데이터 좀 바꿔줘" + has_session_xlsx=True → "xlsx"
     But: "이 파일 내용 요약해줘" + has_session_xlsx=True → "user_files" (READ/분석 요청은 user_files)
3. DISAMBIGUATION - mail vs approval (IMPORTANT):
   - If the user's ACTION is about checking/searching EMAIL (메일 확인, 메일 내용, 메일 검색), classify as "mail" even if the mail subject contains approval keywords like "전자결재", "결재", "기안"
   - The mail subject/title is NOT the user's intent — the ACTION verb determines the intent
   - "'전자결재 수정 확인 요청' 메일 내용 확인해줘" → "mail" (action=메일 확인, subject happens to mention 전자결재)
   - "전자결재 결재 대기 건 확인해줘" → "approval" (action=결재 대기 확인)
4. WORKSPACE-AWARE ROUTING (when has_workspace=True AND workspace has files):
   - Compare the user's query topic with the workspace name, description, and uploaded file names
   - If the query topic MATCHES the workspace domain → "user_files" (search workspace documents first)
   - If the query topic is UNRELATED to the workspace → use the specialized intent (mail, web_search, etc.)
   - Examples:
     - Workspace "메일 관리" with files ["2월_수신메일목록.xlsx"] + query "메일 현황 정리해줘" → "user_files" (workspace covers mail topic)
     - Workspace "분기 실적" with files ["매출보고서.pdf"] + query "안 읽은 메일 확인해줘" → "mail" (workspace is about finance, not mail)
     - Workspace "AI 리서치" with files ["AI동향보고서.pdf"] + query "최근 AI 트렌드" → "user_files" (workspace covers AI trends)
     - Workspace "AI 리서치" with files ["AI동향보고서.pdf"] + query "오늘 날씨" → "web_search" (unrelated to workspace)
5. mail: If user asks about their email/inbox/sent mail/unread mail → "mail"
6. approval: If user asks about electronic approval documents, pending approvals, drafted documents, approval status, bottleneck → "approval"
6.5. board: If user asks about company bulletin board posts, notices, announcements, or searching 게시판 → "board"
7. web_search: If user asks about real-world topics, industries, companies, trends, current events, or anything requiring up-to-date info → "web_search"
8. user_files: If user asks about file contents AND (has_files=True OR has_workspace=True) → "user_files"
9. NEVER choose "user_files" if BOTH has_files=False AND has_workspace=False
10. NEVER choose "direct" if the query is about real-world facts, companies, industries, or current information

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
- "'JHC 전자결재 수정 확인 요청' 메일 내용 확인해줘" → mail (메일 내용 확인 액션, 제목에 전자결재 포함은 무관)
- "'결재 반려 통보' 메일 찾아줘" → mail (메일 검색 액션)
- "전자결재 수정 관련 메일 확인해줘" → mail (메일 확인 액션)
- "안전교육 관련 공지 찾아줘" → board (게시판 검색)
- "전사 공지 최신글 보여줘" → board (전사 게시판 조회)
- "IT 게시판에 올라온 글 뭐 있어?" → board (특정 게시판 조회)
- "게시판에서 발령 검색해줘" → board (게시판 키워드 검색)
- "이번 달 올라온 공지 보여줘" → board (기간 범위 게시판 검색)
- "김명진 님이 올린 게시글 있어?" → board (작성자 기반 검색)
- "JHC 쪽 공지사항 좀 보여줘" → board (카테고리 게시판 검색)
- "엑셀 파일 만들어줘" → xlsx (엑셀 생성)
- "매출 데이터를 엑셀로 정리해줘" → xlsx (엑셀 생성)
- "이 엑셀에 합계 행 추가해줘" → xlsx (엑셀 수정)
- "피벗테이블 만들어줘" → xlsx (엑셀 피벗)
- "엑셀 파일 내용 요약해줘" → user_files (파일 분석, NOT xlsx)
- "이 파일 서식 적용해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 서식 수정)
- "이 파일 디자인 서식 적용해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 서식 수정)
- "파일에 합계 행 추가해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 수정)
- "파일 수정해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 수정)
- "데이터 좀 바꿔줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 수정)
- "값 변경해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 수정)
- "이 파일 정리해줘" (has_session_xlsx=True) → xlsx (세션 xlsx 파일 편집)
- "파일 내용 분석해줘" (has_session_xlsx=True) → user_files (내용 분석/읽기는 user_files)
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

        # ================================================================
        # 메일 액션 우선 감지: "메일 내용 확인해줘", "메일 확인해줘" 등
        # 메일 제목에 "전자결재"가 포함되어 있어도 사용자의 실제 액션이
        # 메일 조회인 경우를 정확히 라우팅 (워크스페이스/다른 키워드 무관)
        # ================================================================
        mail_enabled = os.environ.get("MAIL_WORKER_ENABLED", "true").lower() == "true"
        if mail_enabled:
            mail_action_pattern = r'메일\s*(내용|내역|본문)?\s*(확인|보여|검색|찾아|조회|알려|읽어|요약|답장|답신|회신|응답)'
            if re.search(mail_action_pattern, message, re.IGNORECASE):
                print(f"[INTENT] Quick: explicit mail action pattern detected → MAIL")
                return Intent.MAIL

        # 메일 관련 키워드 감지 (MAIL_WORKER_ENABLED 환경변수로 on/off)
        if mail_enabled:
            mail_keywords = r'(메일|이메일|e-?mail|받은\s?편지|보낸\s?편지|편지함|안\s?읽은\s?메일|새\s?메일|수신함|발신함|inbox|sent\s?mail|mailbox|unread|메일\s?요약|메일\s?답장|메일\s?회신)'
            if re.search(mail_keywords, message, re.IGNORECASE):
                if workspace_has_files:
                    # 워크스페이스에 파일이 있으면 LLM에게 위임 (워크스페이스 주제와 관련 있을 수 있음)
                    print(f"[INTENT] Quick: mail keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.MAIL

        # 전자결재 관련 키워드 감지 (APPROVAL_WORKER_ENABLED 환경변수로 on/off)
        approval_enabled = os.environ.get("APPROVAL_WORKER_ENABLED", "true").lower() == "true"
        if approval_enabled:
            # "메일" 키워드가 함께 있고 메일 기능이 활성화되어 있으면 approval로 단정하지 않음
            # (메일 제목에 "전자결재"가 포함된 경우 오분류 방지)
            # mail_enabled=false이면 메일 라우팅이 불가능하므로 approval로 바로 분류
            has_mail_keyword = mail_enabled and bool(re.search(r'(메일|이메일|e-?mail)', message, re.IGNORECASE))
            approval_keywords = r'(결재|기안|상신|전자결재|결재\s?대기|결재\s?완료|결재함|기안함|반려|재기안|결재선|합의|승인\s?문서|결재\s?건)'
            if re.search(approval_keywords, message, re.IGNORECASE):
                if has_mail_keyword:
                    print(f"[INTENT] Quick: approval keyword detected but also has mail keyword, deferring to LLM for disambiguation")
                    return None
                if workspace_has_files:
                    print(f"[INTENT] Quick: approval keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.APPROVAL

        # 게시판 관련 키워드 감지 (BOARD_WORKER_ENABLED 환경변수로 on/off)
        board_enabled = os.environ.get("BOARD_WORKER_ENABLED", "true").lower() == "true"
        if board_enabled:
            board_keywords = r'(게시판|공지사항|게시글|게시물|사내\s?공지|전사\s?공지|전사\s?게시)'
            if re.search(board_keywords, message, re.IGNORECASE):
                if workspace_has_files:
                    print(f"[INTENT] Quick: board keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.BOARD

        # Excel/XLSX 관련 키워드 감지 (XLSX_WORKER_ENABLED 환경변수로 on/off)
        xlsx_enabled = os.environ.get("XLSX_WORKER_ENABLED", "true").lower() == "true"
        if xlsx_enabled:
            # 패턴 1: "엑셀" 키워드 + 액션 동사 (기존)
            xlsx_pattern = r'(엑셀|excel|xlsx|xls|스프레드시트).{0,20}(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내)'
            xlsx_pattern2 = r'(만들|생성|수정|편집|추가|삭제|서식|포맷|정리|작성|변환|내보내).{0,20}(엑셀|excel|xlsx|xls|스프레드시트)'
            if re.search(xlsx_pattern, message, re.IGNORECASE) or re.search(xlsx_pattern2, message, re.IGNORECASE):
                if workspace_has_files:
                    print(f"[INTENT] Quick: xlsx keyword detected but workspace has files, deferring to LLM")
                    return None
                return Intent.XLSX

            # 패턴 2: 세션에 xlsx 파일 존재 + Excel 수정/서식 관련 키워드 (엑셀 키워드 없이도)
            # "이 파일 서식 적용해줘", "테두리 넣어줘", "합계 추가해줘", "파일 수정해줘" 등
            has_session_xlsx = context.get("has_session_xlsx", False)
            if has_session_xlsx:
                xlsx_modify_keywords = r'(수정|편집|변경|고치|바꿔|바꾸|업데이트|update|서식|포맷|테두리|배경색|글꼴|볼드|bold|정렬|색상|수식|formula|합계|sum|필터|filter|셀\s?병합|merge|행\s?추가|열\s?추가|행\s?삭제|열\s?삭제|데이터\s?추가|데이터\s?입력|값\s?입력|값\s?넣|값\s?변경|값\s?수정|내용\s?변경|내용\s?수정|시트\s?추가|시트\s?삭제|피벗|pivot|채우|넣어|입력|작성|정리|다듬)'
                if re.search(xlsx_modify_keywords, message, re.IGNORECASE):
                    if workspace_has_files:
                        print(f"[INTENT] Quick: xlsx modify keyword + session xlsx, but workspace has files, deferring to LLM")
                        return None
                    print(f"[INTENT] Quick: xlsx modify keyword detected with session xlsx files")
                    return Intent.XLSX

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
                has_session_xlsx=context.get("has_session_xlsx", False),
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

"""A2A 에이전트 공유 상태 정의"""

from enum import Enum
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator


class Intent(str, Enum):
    """사용자 의도 분류"""
    WEB_SEARCH = "web_search"       # 날씨, 뉴스, 실시간 정보
    CORP_RAG = "corp_rag"           # 사내 문서 검색
    USER_FILES = "user_files"       # 업로드 파일 + 워크스페이스 문서
    YOUTUBE = "youtube"             # YouTube URL 포함
    URL_FETCH = "url_fetch"         # 일반 URL 콘텐츠 가져오기 (뉴스, 블로그, GitHub 등)
    IT_SUPPORT = "it_support"       # IT/보안 VOC
    ACCT_SUPPORT = "acct_support"   # 회계/재경 VOC
    PPT_GENERATION = "ppt_generation" # PPT 프레젠테이션 생성
    MAIL = "mail"                   # 메일 조회, 메일 검색
    APPROVAL = "approval"           # 전자결재 조회, 기안/결재/참조/부서문서
    XLSX = "xlsx"                   # Excel 파일 생성, 수정, 조작
    BOARD = "board"                 # 사내 게시판 검색, 공지사항 조회
    OUTLINE = "outline"             # L&F Wiki 문서 검색/조회
    RESERVATION = "reservation"     # 회의실/자산 예약 조회, 등록, 취소
    CALENDAR = "calendar"           # 캘린더 일정 조회, 등록, 삭제
    NAS = "nas"                     # NAS 공유 폴더 파일 탐색, 검색, 다운로드
    CLARIFY = "clarify"             # 어디서 조회해야 할지 모호한 요청 → 사용자에게 확인
    DIRECT = "direct"               # 일반 대화, 코딩, 번역 등


# Intent → Worker 매핑
INTENT_TO_WORKER = {
    Intent.WEB_SEARCH: "WebSearchWorker",
    Intent.CORP_RAG: "CorpRAGWorker",
    Intent.USER_FILES: "UserFilesWorker",
    Intent.YOUTUBE: "YouTubeWorker",
    Intent.URL_FETCH: "URLFetchWorker",
    Intent.IT_SUPPORT: "ITSupportWorker",
    Intent.ACCT_SUPPORT: "AcctSupportWorker",
    Intent.PPT_GENERATION: "PPTWorker",
    Intent.MAIL: "MailWorker",
    Intent.APPROVAL: "ApprovalWorker",
    Intent.XLSX: "XlsxWorker",
    Intent.BOARD: "BoardWorker",
    Intent.OUTLINE: "OutlineWorker",
    Intent.RESERVATION: "ReservationWorker",
    Intent.CALENDAR: "CalendarWorker",
    Intent.NAS: "NASWorker",
    Intent.CLARIFY: "DirectResponseWorker",
    Intent.DIRECT: "DirectResponseWorker",
}


# Intent → 사람이 읽을 수 있는 기능 설명 (HANDOFF 프롬프트용)
WORKER_CAPABILITIES = {
    Intent.MAIL: "메일 조회/검색/요약 (받은편지함, 보낸편지함, 메일 본문, 답장 초안)",
    Intent.APPROVAL: "전자결재 조회 (결재 대기함, 기안함, 결재 완료함, 참조함)",
    Intent.WEB_SEARCH: "실시간 웹 검색 (뉴스, 날씨, 주가, 최신 정보)",
    Intent.CORP_RAG: "사내 문서 검색 (인사, 회계, IT, 안전 규정)",
    Intent.USER_FILES: "업로드 파일 분석 (PDF, DOCX, XLSX, TXT)",
    Intent.IT_SUPPORT: "IT 지원 VOC 검색 (IT/보안 문의 사례)",
    Intent.ACCT_SUPPORT: "회계/재경 VOC 검색 (회계 문의 사례)",
    Intent.BOARD: "사내 게시판 검색 (공지사항, 게시글)",
    Intent.OUTLINE: "L&F Wiki 문서 검색/조회 (위키 문서, 컬렉션 탐색)",
    Intent.RESERVATION: "회의실/자산 예약 조회, 빈 회의실 검색, 예약 등록/취소",
    Intent.CALENDAR: "캘린더 일정 조회/등록/삭제, 빈 시간 검색, 타인 공개 캘린더 조회",
    Intent.NAS: "NAS 공유 폴더 파일 탐색, 검색, 다운로드",
    Intent.XLSX: "엑셀 파일 생성/수정 (서식, 차트, 피벗테이블)",
    Intent.PPT_GENERATION: "PPT 프레젠테이션 생성",
    Intent.YOUTUBE: "YouTube 영상 요약",
    Intent.URL_FETCH: "웹 페이지 콘텐츠 추출",
}


class AgentState(TypedDict):
    """Orchestrator와 Worker 간 공유 상태"""
    # 메시지 히스토리 (누적)
    messages: Annotated[List[BaseMessage], operator.add]

    # 분류된 의도
    intent: Optional[Intent]

    # 선택된 Worker 이름
    worker_name: Optional[str]

    # 컨텍스트 정보 (세션, 워크스페이스 등)
    context: Dict[str, Any]

    # Worker 응답 결과
    worker_response: Optional[str]

    # 수집된 메타데이터 (출처, YouTube 요약 등)
    metadata: Dict[str, Any]


class RequestContext(TypedDict):
    """요청 컨텍스트 (chat.py에서 전달)"""
    session_id: Optional[str]
    user_id: str
    workspace_id: Optional[str]  # UUID string
    workspace_uuid: Optional[str]  # Deprecated: use workspace_id
    workspace_instructions: Optional[str]
    workspace_has_files: bool  # 워크스페이스에 문서가 있는지 여부
    workspace_name: Optional[str]  # 워크스페이스 이름 (인텐트 분류용)
    workspace_description: Optional[str]  # 워크스페이스 설명 (인텐트 분류용)
    workspace_file_names: List[str]  # 워크스페이스 업로드 파일명 목록 (인텐트 분류용)
    has_files: bool  # 세션에 사용자 파일이 업로드되었는지 여부
    has_session_xlsx: bool  # 세션에 xlsx 파일이 업로드되었는지 여부 (인텐트 분류용)
    chat_mode: str
    gosso_cookie: Optional[str]  # 사용자 LFON GOSSOcookie (캘린더 API 사용자 인증용)

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
    VISUALIZATION = "visualization" # PDF 생성, 문서 변환, 시각화
    PPT_GENERATION = "ppt_generation" # PPT 프레젠테이션 생성
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
    Intent.VISUALIZATION: "VisualizationWorker",
    Intent.PPT_GENERATION: "PPTWorker",
    Intent.DIRECT: "DirectResponseWorker",
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
    has_files: bool  # 세션에 사용자 파일이 업로드되었는지 여부
    chat_mode: str

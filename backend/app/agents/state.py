"""A2A 에이전트 공유 상태 정의"""

from dataclasses import dataclass, field
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
    Intent.RESERVATION: "CalendarWorker",
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


class RequestContext(TypedDict, total=False):
    """요청 컨텍스트 (chat.py에서 전달)

    total=False: 모든 필드가 optional. Planner-Executor 경로에서는 task_goal이 추가되고,
    기존 경로는 task_goal 없이 동작 (하위 호환).
    """
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

    # 첨부 이미지 — Planner-Executor 경로의 depends=[] task에 multimodal로 동봉
    # (trivial 경로는 orchestrator._build_messages가 직접 처리하므로 사용 안 함)
    images: Optional[List[Dict[str, str]]]  # [{"media_type": ..., "base64_data": ...}, ...]
    has_images: bool                         # Planner 라우팅 힌트용 (이미지 분석은 direct 워커로)

    # Planner-Executor 경로 전용 필드 (PLANNER_ENABLED=true일 때만 주입)
    task_goal: Optional[str]             # 현재 워커가 처리할 sub-task 목표 (한 줄)
    task_id: Optional[str]                # 현재 task의 id (블랙보드 참조용)
    task_dependencies: Optional[Dict[str, str]]  # 선행 task 결과 맵 {task_id: result}


# ============================================================
# Planner-Executor 아키텍처 전용 타입 (2026-04-20 도입)
# ============================================================

class TaskStatus(str, Enum):
    """Task 실행 상태"""
    PENDING = "pending"                   # 아직 시작 안 함
    RUNNING = "running"                   # 실행 중
    DONE = "done"                         # 성공 완료
    FAILED = "failed"                     # 실행 실패
    SKIPPED = "skipped"                   # 의존 task 실패/거부로 건너뜀
    AWAITING_CONFIRM = "awaiting_confirm" # 사용자 승인 대기 중


@dataclass
class Task:
    """단일 sub-task 정의 (Planner 출력 단위, Executor 실행 단위)

    Planner가 사용자 요청을 분해하여 생성. Executor가 depends를 기반으로
    위상정렬하여 병렬/순차 실행.
    """
    id: str                          # "t1", "t2" ... (Plan 내 유일)
    worker: str                      # INTENT_TO_WORKER 매핑에 사용될 intent 값 (예: "mail", "calendar")
    goal: str                        # 워커가 받을 목표 (한 줄, 구체적)
    depends: List[str] = field(default_factory=list)  # 선행 task id 목록
    needs_confirm: bool = False      # 쓰기 작업 등 사용자 승인 필요 여부

    # 실행 결과 (Executor가 채움)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None     # 성공 시 워커 출력 텍스트
    error: Optional[str] = None      # 실패 시 에러 메시지
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def is_ready(self, completed_task_ids: set) -> bool:
        """모든 선행 task가 완료되었으면 실행 가능"""
        return all(dep in completed_task_ids for dep in self.depends)

    def elapsed_ms(self) -> Optional[int]:
        """실행 소요 시간 (밀리초)"""
        if self.started_at is None or self.completed_at is None:
            return None
        return int((self.completed_at - self.started_at) * 1000)


@dataclass
class Plan:
    """Planner의 출력 — 사용자 요청을 분해한 Task DAG

    is_trivial=True면 단일 task의 단순 요청 (기존 경로와 동등).
    Executor는 tasks를 위상정렬하여 depends 만족된 것부터 실행.
    """
    tasks: List[Task] = field(default_factory=list)
    rationale: str = ""              # Planner가 왜 이렇게 쪼갰는지 (디버그/로그용)
    is_trivial: bool = False         # True면 단일 단순 task → 기존 경로 우회 가능

    def get_task(self, task_id: str) -> Optional[Task]:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_ready_tasks(self, completed_ids: set) -> List[Task]:
        """실행 준비된 PENDING task들 반환 (병렬 실행 후보)"""
        return [t for t in self.tasks
                if t.status == TaskStatus.PENDING and t.is_ready(completed_ids)]

    def validate(self) -> Optional[str]:
        """DAG 유효성 검증. 문제 시 에러 메시지 반환, OK면 None.

        - task id 중복 검사
        - 존재하지 않는 depends 참조 검사
        - 순환 의존성 검사 (DFS)
        """
        ids = [t.id for t in self.tasks]
        if len(ids) != len(set(ids)):
            return f"Duplicate task ids: {ids}"

        id_set = set(ids)
        for t in self.tasks:
            for dep in t.depends:
                if dep not in id_set:
                    return f"Task '{t.id}' depends on unknown task '{dep}'"

        # 순환 감지 (DFS white/gray/black)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in id_set}
        task_map = {t.id: t for t in self.tasks}

        def visit(tid: str) -> Optional[str]:
            if color[tid] == GRAY:
                return f"Cycle detected at task '{tid}'"
            if color[tid] == BLACK:
                return None
            color[tid] = GRAY
            for dep in task_map[tid].depends:
                err = visit(dep)
                if err:
                    return err
            color[tid] = BLACK
            return None

        for tid in id_set:
            err = visit(tid)
            if err:
                return err

        return None

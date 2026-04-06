"""A2A 스트리밍 로직 - chat.py에서 호출"""

import asyncio
import json
import time
import re
from typing import Callable, Dict, AsyncIterator, List, Optional

from pathlib import Path

from app.agents import get_orchestrator
from app.agents.state import RequestContext

# xlsx 업로드 디렉토리 (세션별 xlsx 파일 존재 여부 확인용)
_XLSX_UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "xlsx_upload"


def _has_session_xlsx(session_id: Optional[str]) -> bool:
    """세션에 xlsx 파일이 업로드되었는지 확인 (인텐트 분류용)"""
    if not session_id:
        return False
    session_dir = _XLSX_UPLOAD_DIR / session_id
    if not session_dir.exists():
        return False
    return any(
        f.suffix.lower() in ('.xlsx', '.xls')
        for f in session_dir.iterdir()
        if f.is_file()
    )


# ============================================================================
# Heartbeat 설정 - 긴 작업 중 사용자 피드백 제공
# ============================================================================
HEARTBEAT_INTERVAL = 5.0  # 초

# 기본 하트비트 메시지 (PDF, 차트 등)
DEFAULT_HEARTBEAT_MESSAGES = [
    "📝 정보를 바탕으로 문서를 요약하고 있습니다...",
    "📝 내용을 깔끔하게 정리하고 있습니다...",
]

# PPT 전용 하트비트 메시지
PPT_HEARTBEAT_MESSAGES = [
    "📊 PPT 슬라이드를 구성하고 있습니다...",
    "📊 PPT 생성은 슬라이드 수에 따라 시간이 더 소요될 수 있습니다.",
    "📊 텍스트, 테이블, 차트 등 슬라이드 요소를 배치하고 있습니다...",
    "📊 템플릿 스타일을 적용하고 있습니다...",
    "📊 거의 완성되어 가고 있습니다. 조금만 더 기다려주세요!",
]

# Heartbeat를 활성화할 도구 목록 (긴 작업이 예상되는 도구)
HEARTBEAT_TOOLS = [
    "create_document_pdf",
    "create_table_spec_pdf",
    "create_presentation",
    "create_workbook",
    "write_data_to_excel",
    "create_line_chart",
    "create_bar_chart",
    "create_pie_chart",
    "create_multi_chart",
]

# 도구별 하트비트 메시지 매핑
TOOL_HEARTBEAT_MESSAGES = {
    "create_presentation": PPT_HEARTBEAT_MESSAGES,
}


async def heartbeat_producer(
    event_queue: asyncio.Queue,
    interval: float,
    stop_event: asyncio.Event,
    messages: list = None,
):
    """
    백그라운드에서 주기적 heartbeat 메시지를 이벤트 큐에 넣음

    Args:
        event_queue: 통합 이벤트 큐 (orchestrator + heartbeat)
        interval: heartbeat 간격 (초)
        stop_event: 중지 시그널
        messages: 사용할 하트비트 메시지 목록 (없으면 기본 메시지)
    """
    heartbeat_messages = messages or DEFAULT_HEARTBEAT_MESSAGES
    idx = 0
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            # stop_event가 set되면 루프 종료
            break
        except asyncio.TimeoutError:
            # 타임아웃 = interval 경과 → heartbeat 전송
            if not stop_event.is_set():
                msg = heartbeat_messages[idx % len(heartbeat_messages)]
                await event_queue.put({"_source": "heartbeat", "message": msg, "index": idx})
                idx += 1


async def orchestrator_producer(
    event_queue: asyncio.Queue,
    orchestrator,
    message: str,
    context: dict,
    all_tools: list,
    message_history: list,
    images: list,
):
    """
    Orchestrator 스트림 이벤트를 큐에 넣음
    """
    try:
        async for event in orchestrator.stream(
            message=message,
            context=context,
            all_tools=all_tools,
            message_history=message_history,
            images=images,
        ):
            await event_queue.put({"_source": "orchestrator", **event})
    finally:
        # 스트림 완료 시 종료 신호
        await event_queue.put({"_source": "done"})

# Corp 모드 RAG 도구 목록 (출처 표시용)
CORP_RAG_TOOLS = [
    "search_hr_docs",
    "search_ac_docs",
    "search_it_docs",
    "search_safety_docs",
]

# 도구 실행 상태 메시지
TOOL_STATUS_MESSAGES = {
    "tavily_search": "🌌 웹을 검색해보고 있습니다. 조금만 기다려주세요!",
    "search_user_files": "📄 파일 검색해보고 있습니다. 조금만 기다려주세요!",
    "youtube_summarize": "📺 YouTube 영상을 요약하고 있습니다. 조금만 기다려주세요!",
    "search_workspace_docs": "📁 워크스페이스에 업로드 된 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    # Corp RAG 도구
    "search_hr_docs": "📋 인사 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_ac_docs": "💰 재경 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_it_docs": "💻 IT 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_safety_docs": "⚠️ 안전환경 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    # 조직도 검색 도구
    "execute_org_chart_query": "🏢 조직도에서 검색하고 있습니다. 조금만 기다려주세요!",
    # PDF 생성 도구
    "create_document_pdf": "📄 PDF 문서를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_table_spec_pdf": "📋 테이블 정의서 PDF를 생성하고 있습니다. 조금만 기다려주세요!",
    "list_generated_pdfs": "📂 생성된 PDF 목록을 조회하고 있습니다.",
    # 차트 생성 도구
    "create_line_chart": "📈 라인 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_bar_chart": "📊 막대 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_pie_chart": "🥧 파이 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_multi_chart": "📉 복합 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    # PPT 생성 도구
    "create_presentation": "📊 PPT 프레젠테이션을 생성하고 있습니다. 조금만 기다려주세요!",
    "list_ppt_templates": "📋 PPT 템플릿 정보를 조회하고 있습니다.",
    "list_generated_ppts": "📂 생성된 PPT 목록을 조회하고 있습니다.",
    # 메일 조회 도구
    "get_inbox_mail": "📬 받은편지함을 조회하고 있습니다. 조금만 기다려주세요!",
    "get_sent_mail": "📤 보낸편지함을 조회하고 있습니다. 조금만 기다려주세요!",
    "search_mail": "🔍 메일을 검색하고 있습니다. 조금만 기다려주세요!",
    "get_mail_folders": "📁 메일함 목록을 조회하고 있습니다. 조금만 기다려주세요!",
    "get_unread_mail": "📩 안 읽은 메일을 조회하고 있습니다. 조금만 기다려주세요!",
    "get_mail_detail": "📧 메일 전체 본문을 조회하고 있습니다. 조금만 기다려주세요!",
    # 전자결재 조회 도구
    "get_user_approval_info": "👤 사용자 결재 정보를 확인하고 있습니다. 조금만 기다려주세요!",
    "execute_approval_query": "📋 전자결재 문서를 조회하고 있습니다. 조금만 기다려주세요!",
    # Excel(XLSX) 도구
    "create_workbook": "📊 엑셀 파일을 생성하고 있습니다.",
    "write_data_to_excel": "📊 데이터를 입력하고 있습니다.",
    "read_data_from_excel": "📊 엑셀 데이터를 읽고 있습니다.",
    "get_workbook_metadata": "📊 엑셀 파일 구조를 확인하고 있습니다.",
    "format_range": "📊 서식을 적용하고 있습니다.",
    "apply_formula": "📊 수식을 적용하고 있습니다.",
    "create_chart": "📊 엑셀 차트를 생성하고 있습니다.",
    "create_pivot_table": "📊 피벗테이블을 생성하고 있습니다.",
    "create_table": "📊 엑셀 테이블을 생성하고 있습니다.",
}

# 다단계 도구 — 여러 번 연속 호출되는 도구 (매 호출마다 "취합 완료" 표시 억제)
MULTI_STEP_TOOLS = {
    "create_workbook", "create_worksheet", "write_data_to_excel",
    "format_range", "apply_formula", "merge_cells", "unmerge_cells",
    "insert_rows", "insert_columns", "delete_sheet_rows", "delete_sheet_columns",
    "copy_range", "delete_range", "rename_worksheet", "copy_worksheet",
    "delete_worksheet", "create_table", "create_chart", "create_pivot_table",
}


# ============================================================================
# Context-aware 도구 상태 메시지 생성
# ============================================================================

def _truncate(text: str, max_len: int = 20) -> str:
    """표시용 텍스트 자르기 (초과 시 ... 추가)"""
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    return text[:max_len] + "..." if len(text) > max_len else text


# 도구별 파라미터 기반 동적 메시지 생성기
# 반환값이 None이면 TOOL_STATUS_MESSAGES 정적 메시지로 폴백
TOOL_CONTEXT_GENERATORS: Dict[str, Callable[[Dict], Optional[str]]] = {
    # 웹 검색
    "tavily_search": lambda inp: (
        f"🌌 '{_truncate(inp.get('query', ''))}' 에 대해 웹에서 검색하고 있습니다..."
        if inp.get("query") else None
    ),
    # 사내 문서 RAG
    "search_hr_docs": lambda inp: (
        f"📋 '{_truncate(inp.get('query', ''))}' 관련 인사 문서를 찾아보고 있습니다..."
        if inp.get("query") else None
    ),
    "search_ac_docs": lambda inp: (
        f"💰 '{_truncate(inp.get('query', ''))}' 관련 재경 문서를 찾아보고 있습니다..."
        if inp.get("query") else None
    ),
    "search_it_docs": lambda inp: (
        f"💻 '{_truncate(inp.get('query', ''))}' 관련 IT 문서를 찾아보고 있습니다..."
        if inp.get("query") else None
    ),
    "search_safety_docs": lambda inp: (
        f"⚠️ '{_truncate(inp.get('query', ''))}' 관련 안전환경 문서를 찾아보고 있습니다..."
        if inp.get("query") else None
    ),
    # 사용자 파일/워크스페이스
    "search_user_files": lambda inp: (
        f"📄 '{_truncate(inp.get('query', ''))}' 관련 파일을 검색하고 있습니다..."
        if inp.get("query") else None
    ),
    "search_workspace_docs": lambda inp: (
        f"📁 '{_truncate(inp.get('query', ''))}' 관련 워크스페이스 문서를 검색하고 있습니다..."
        if inp.get("query") else None
    ),
    # IT VOC 검색
    "search_it_voc": lambda inp: (
        f"🔍 '{_truncate(inp.get('keyword', ''))}' 관련 IT 지원 사례를 찾아보고 있습니다..."
        if inp.get("keyword") else None
    ),
    # 메일 검색
    "search_mail": lambda inp: (
        f"🔍 '{_truncate(inp.get('keyword', ''))}' 관련 메일을 검색하고 있습니다..."
        if inp.get("keyword") else None
    ),
    # URL fetch
    "fetch": lambda inp: (
        "🌐 웹 페이지 내용을 가져오고 있습니다..."
    ),
}


def get_tool_status_message(tool_name: str, tool_input: Dict) -> str:
    """도구 파라미터 기반 context-aware 상태 메시지 생성

    우선순위:
    1. TOOL_CONTEXT_GENERATORS 동적 메시지 (파라미터 포함)
    2. TOOL_STATUS_MESSAGES 정적 메시지
    3. 제네릭 폴백
    """
    generator = TOOL_CONTEXT_GENERATORS.get(tool_name)
    if generator:
        try:
            msg = generator(tool_input or {})
            if msg:
                return msg
        except Exception:
            pass
    return TOOL_STATUS_MESSAGES.get(tool_name, f"🔧 작업을 수행하고 있습니다...")


# 도구 완료 시 context-aware 메시지
TOOL_COMPLETION_MESSAGES = {
    "tavily_search": "🌌 웹 검색 결과를 정리하고 있습니다...",
    "search_hr_docs": "📋 인사 문서 검색 결과를 정리하고 있습니다...",
    "search_ac_docs": "💰 재경 문서 검색 결과를 정리하고 있습니다...",
    "search_it_docs": "💻 IT 문서 검색 결과를 정리하고 있습니다...",
    "search_safety_docs": "⚠️ 안전환경 문서 검색 결과를 정리하고 있습니다...",
    "search_user_files": "📄 파일 검색 결과를 정리하고 있습니다...",
    "search_workspace_docs": "📁 워크스페이스 문서 검색 결과를 정리하고 있습니다...",
    "youtube_summarize": "📺 영상 분석 결과를 정리하고 있습니다...",
    "search_it_voc": "🔍 IT 지원 사례 검색 결과를 정리하고 있습니다...",
    "execute_it_voc_query": "🔍 IT 지원 사례 조회 결과를 정리하고 있습니다...",
    "execute_org_chart_query": "🏢 조직도 결과를 정리하고 있습니다...",
    "execute_acct_voc_query": "💰 회계 VOC 조회 결과를 정리하고 있습니다...",
    "execute_approval_query": "📋 전자결재 조회 결과를 정리하고 있습니다...",
    "search_mail": "🔍 메일 검색 결과를 정리하고 있습니다...",
    "get_inbox_mail": "📬 받은편지함 조회 결과를 정리하고 있습니다...",
    "get_sent_mail": "📤 보낸편지함 조회 결과를 정리하고 있습니다...",
    "get_unread_mail": "📩 안 읽은 메일 조회 결과를 정리하고 있습니다...",
    "get_mail_detail": "📧 메일 내용을 분석하고 있습니다...",
    "fetch": "🌐 웹 페이지 내용을 분석하고 있습니다...",
}


async def stream_a2a_response(
    message: str,
    user_id: str,
    session_id: Optional[str],
    workspace_id: Optional[str],  # UUID string
    workspace_context: Optional[Dict],
    has_files: bool,
    chat_mode: str,
    message_history: Optional[List[Dict]],
    images: Optional[List[Dict]],
    all_tools: List,
    start_time: float,
) -> AsyncIterator[str]:
    """
    A2A Hierarchical Agent 스트리밍 응답 생성

    Returns:
        SSE 형식의 문자열 스트림
    """
    # 응답 수집 변수
    collected_response = ""
    collected_sources = []
    collected_youtube_summary = None
    collected_chart_data = None  # 차트 데이터 (display 모드)
    collected_svg_data = None  # SVG 시각화 데이터
    all_searched_corp_sources = []  # 검색된 모든 문서 (Tool 결과)
    chunk_count = 0
    first_chunk_time = None
    tool_calls_made = []  # 호출된 도구 목록 (출처 수집 등에 사용)
    tool_messages_sent: set = set()  # 이미 보낸 상태 메시지 (중복 억제용)
    tool_call_counts: Dict[str, int] = {}  # 도구별 호출 횟수 (루프 감지용)
    tool_end_time = None  # 도구 완료 시간 (지연 분석용)
    last_content_time = None  # 마지막 콘텐츠 청크 시간 (지연 분석용)
    needs_newline_after_tool = False  # 도구 완료 후 다음 텍스트 앞에 개행 삽입 필요 여부
    MAX_SAME_TOOL_CALLS = 50  # 같은 도구 최대 호출 횟수

    # tool_call/tool_response/HTML comment 태그 필터링 상태
    _inside_tool_tag = False  # 태그 내부 여부
    _inside_comment = False   # <!-- --> 코멘트 내부 여부 (FOLLOW_UP 캡처용)
    _tag_buffer = ""  # 부분 태그 감지용 버퍼
    _tag_filter_notified = False  # 필터링 시작 시 상태 메시지 전송 여부
    _stripped_comments = []  # 스트리밍 중 제거된 HTML 코멘트 (FOLLOW_UP 후처리용)

    # 리포트용 수집 변수
    classified_intent = None
    classified_worker = None
    is_error = False
    collected_follow_ups = None  # 팔로우업 제안 (LLM 응답에서 파싱)
    total_input_tokens = 0
    total_output_tokens = 0
    total_llm_calls = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0

    # 통합 이벤트 큐 (orchestrator + heartbeat 이벤트 병합)
    event_queue: asyncio.Queue = asyncio.Queue()
    heartbeat_stop_event = asyncio.Event()
    heartbeat_task: Optional[asyncio.Task] = None
    heartbeat_active = False  # heartbeat가 활성화된 상태인지

    # 로그는 chat.py에서 이미 출력하므로 여기서는 생략

    # RequestContext 구성
    req_context: RequestContext = {
        "session_id": session_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "workspace_uuid": workspace_context.get("uuid") if workspace_context else None,
        "workspace_instructions": workspace_context.get("instructions") if workspace_context else None,
        "workspace_has_files": workspace_context.get("has_files", False) if workspace_context else False,
        "workspace_name": workspace_context.get("name") if workspace_context else None,
        "workspace_description": workspace_context.get("description") if workspace_context else None,
        "workspace_file_names": workspace_context.get("file_names", []) if workspace_context else [],
        "has_files": has_files,
        "has_session_xlsx": _has_session_xlsx(session_id),
        "chat_mode": chat_mode,
        "session_file_names": [],  # 아래에서 채움
    }

    # 세션 업로드 파일명 목록 조회 (OutlineWorker 등에서 파일명 주입용)
    if has_files and session_id:
        try:
            from app.services.chromadb_service import get_chromadb_service
            chromadb = get_chromadb_service()
            req_context["session_file_names"] = chromadb.get_session_file_names(session_id)
        except Exception:
            pass

    # 이전 턴의 intent 조회 (follow-up 판단용)
    previous_intent = None
    if session_id:
        try:
            from app.services.chat_log_service import get_chat_log_service
            previous_intent = get_chat_log_service().get_last_intent(session_id)
            if previous_intent:
                print(f"[CHAT_STREAM] Previous intent: {previous_intent}")
        except Exception as e:
            print(f"[CHAT_STREAM] Previous intent lookup error (non-fatal): {e}")

    req_context["previous_intent"] = previous_intent

    # Orchestrator 스트리밍
    orchestrator = get_orchestrator()

    # Orchestrator producer 태스크 시작
    orchestrator_task = asyncio.create_task(
        orchestrator_producer(
            event_queue=event_queue,
            orchestrator=orchestrator,
            message=message,
            context=req_context,
            all_tools=all_tools,
            message_history=message_history,
            images=images,
        )
    )

    # 통합 큐에서 이벤트 처리
    try:
        while True:
            event = await event_queue.get()

            # 스트림 종료 체크
            if event.get("_source") == "done":
                break

            # Heartbeat 이벤트 처리
            if event.get("_source") == "heartbeat":
                yield f"data: {json.dumps({'type': 'tool_status', 'tool': 'heartbeat', 'message': event['message']})}\n\n"
                continue

            # Orchestrator 이벤트 처리
            event_type = event.get("type") or event.get("event")

            # A2A 전용 이벤트 처리
            if event_type == "intent_classified":
                if event.get("is_fallback"):
                    # Fallback intent는 별도 저장 (primary 덮어쓰기 방지)
                    print(f"[CHAT_STREAM] Fallback intent: {event.get('intent')} -> {event.get('worker')}")
                elif event.get("is_handoff"):
                    # Handoff 선행 워커 intent는 primary 덮어쓰기 방지
                    print(f"[CHAT_STREAM] Handoff intent: {event.get('intent')} -> {event.get('worker')}")
                else:
                    classified_intent = event.get("intent")
                    classified_worker = event.get("worker")
                yield f"data: {json.dumps(event)}\n\n"
                continue

            if event_type == "orchestrator_timing":
                yield f"data: {json.dumps({'type': 'timing', 'step': 'orchestrator', 'timing': event})}\n\n"
                continue

            # 토큰 사용량 수집
            if event_type == "token_usage":
                total_input_tokens += event.get("input_tokens", 0)
                total_output_tokens += event.get("output_tokens", 0)
                total_llm_calls += event.get("llm_call_count", 0)
                total_cache_read_tokens += event.get("cache_read_tokens", 0)
                total_cache_write_tokens += event.get("cache_write_tokens", 0)
                continue

            # Worker 이벤트 처리
            if event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                tool_start_ms = int((time.time() - start_time) * 1000)
                print(f"[TIMING] Tool '{tool_name}' started at {tool_start_ms}ms")

                # 도구 호출 횟수 카운트 (루프 감지)
                tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
                if tool_call_counts[tool_name] > MAX_SAME_TOOL_CALLS:
                    print(f"[LOOP DETECTED] Tool '{tool_name}' called {tool_call_counts[tool_name]} times, breaking loop")
                    yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': f'⚠️ {tool_name} 도구가 {tool_call_counts[tool_name]}회 반복 호출되어 중단합니다. 결과를 확인해주세요.'})}\n\n"
                    # 루프 감지 시 더 이상 진행하지 않음 - orchestrator 취소
                    if not orchestrator_task.done():
                        orchestrator_task.cancel()
                    break

                # SQL 쿼리 도구인 경우 쿼리 내용 로깅
                if tool_name in ("execute_it_voc_query", "execute_org_chart_query", "execute_acct_voc_query", "execute_approval_query") and tool_input:
                    sql_query = tool_input.get("sql_query", str(tool_input))
                    print(f"[SQL QUERY - {tool_name}] {sql_query}")
                # 도구 호출 기록 (출처 수집 등에 사용)
                if tool_name not in tool_calls_made:
                    tool_calls_made.append(tool_name)

                # context-aware 상태 메시지 생성 (파라미터 기반)
                print(f"[TOOL_STATUS_DEBUG] tool_name={tool_name}, tool_input={str(tool_input)[:200]}")
                status_msg = get_tool_status_message(tool_name, tool_input)
                print(f"[TOOL_STATUS_DEBUG] Generated message: {status_msg}")
                if status_msg not in tool_messages_sent:
                    tool_messages_sent.add(status_msg)
                    print(f"[TOOL_STATUS] Sending: {status_msg}")
                    yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': status_msg})}\n\n"
                else:
                    print(f"[TOOL_STATUS_DEBUG] Skipped (already sent): {status_msg}")
                    if tool_name in MULTI_STEP_TOOLS:
                        # 다단계 도구: 반복 호출 시 진행 상태 표시
                        step = tool_call_counts[tool_name]
                        yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': f'📊 엑셀 작업 진행 중... (단계 {step})'})}\n\n"

                # HEARTBEAT_TOOLS에 해당하면 하트비트 시작 (도구 실행 중 사용자 피드백)
                if tool_name in HEARTBEAT_TOOLS and not heartbeat_active:
                    heartbeat_stop_event.clear()
                    tool_messages = TOOL_HEARTBEAT_MESSAGES.get(tool_name)
                    heartbeat_task = asyncio.create_task(
                        heartbeat_producer(event_queue, HEARTBEAT_INTERVAL, heartbeat_stop_event, messages=tool_messages)
                    )
                    heartbeat_active = True
                    print(f"[HEARTBEAT] Started for tool '{tool_name}'")

            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                tool_output = event.get("data", {}).get("output", "")

                # 도구 완료 시간 기록 (지연 분석용)
                tool_end_time = time.time()
                tool_end_ms = int((tool_end_time - start_time) * 1000)
                print(f"[TIMING] Tool '{tool_name}' completed at {tool_end_ms}ms")

                # 도구 결과 디버깅 로그
                try:
                    output_str = tool_output.content if hasattr(tool_output, 'content') else str(tool_output)
                    # 예약/캘린더 도구는 전문 로깅 (LLM 데이터 누락 디버깅)
                    if tool_name in ("get_daily_reservations", "get_calendar_events"):
                        print(f"[TOOL_OUTPUT] {tool_name}: (full, {len(output_str)} chars)\n{output_str}")
                    else:
                        print(f"[TOOL_OUTPUT] {tool_name}: {output_str[:300]}")
                except Exception:
                    print(f"[TOOL_OUTPUT] {tool_name}: (cannot read output)")

                # 도구 완료 시 하트비트 중지 (모든 도구)
                # tool_use_detected에서 시작된 하트비트가 non-HEARTBEAT_TOOLS에서도 정상 중지
                # HEARTBEAT_TOOLS는 on_tool_start에서 다시 시작하므로 영향 없음
                if heartbeat_active:
                    heartbeat_stop_event.set()
                    heartbeat_active = False
                    print(f"[HEARTBEAT] Stopped (tool '{tool_name}' completed)")

                # 도구 완료 전 이미 텍스트가 있었으면, 다음 텍스트 앞에 개행 삽입 필요
                if collected_response:
                    needs_newline_after_tool = True

                # 응답 생성 중 상태 메시지 (다단계 도구는 중간 단계이므로 억제)
                if tool_name not in MULTI_STEP_TOOLS:
                    completion_msg = TOOL_COMPLETION_MESSAGES.get(tool_name, '✨ 결과를 바탕으로 응답을 작성하고 있습니다...')
                    yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': completion_msg, 'status': 'generating'})}\n\n"

                # Corp 문서 출처 수집 (검색된 모든 문서 + 청크 텍스트)
                if tool_name in CORP_RAG_TOOLS:
                    output_str = str(tool_output.content if hasattr(tool_output, 'content') else tool_output)
                    # 헤더 + 청크 내용까지 캡처하는 패턴
                    pattern_with_content = r'\[(인사|재경|IT|안전환경) 문서 (\d+): (.+?) \(유사도: ([\d.]+)\)\]\n(.*?)(?=\n\[(?:인사|재경|IT|안전환경) 문서 \d+:|$)'
                    matches = re.findall(pattern_with_content, output_str, re.DOTALL)
                    if matches:
                        for category, doc_num, filename, similarity, chunk_text in matches:
                            all_searched_corp_sources.append({
                                "filename": filename.strip(),
                                "category": category,
                                "tool": tool_name,
                                "similarity": float(similarity) if similarity else 0,
                                "chunk_text": chunk_text.strip()
                            })
                    else:
                        # 폴백: 헤더만 추출 (청크 내용 없음)
                        pattern_header = r'\[(인사|재경|IT|안전환경) 문서 \d+: (.+?) \(유사도: ([\d.]+)\)\]'
                        header_matches = re.findall(pattern_header, output_str)
                        if not header_matches:
                            pattern_legacy = r'\[(인사|재경|IT|안전환경) 문서 \d+: (.+?)\]\n'
                            header_matches = [(cat, fn, "0") for cat, fn in re.findall(pattern_legacy, output_str)]
                        for category, filename, similarity in header_matches:
                            all_searched_corp_sources.append({
                                "filename": filename.strip(),
                                "category": category,
                                "tool": tool_name,
                                "similarity": float(similarity) if similarity else 0,
                                "chunk_text": ""
                            })

                # Tavily 출처 수집
                if "tavily" in tool_name.lower():
                    output_str = tool_output.content if hasattr(tool_output, 'content') else tool_output
                    if isinstance(output_str, str):
                        pattern = r'Title:\s*(.+?)\s*\nURL:\s*(.+?)(?:\s*\nContent:|$)'
                        matches = re.findall(pattern, output_str, re.MULTILINE | re.DOTALL)
                        sources_data = []
                        for i, (title, url) in enumerate(matches[:5]):
                            if url.strip().startswith('http'):
                                sources_data.append({
                                    'url': url.strip(),
                                    'title': title.strip(),
                                    'score': 1.0 - (i * 0.1)
                                })
                        if sources_data:
                            collected_sources.extend(sources_data)
                            yield f"data: {json.dumps({'type': 'search_sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"

                # YouTube 요약 수집
                if tool_name == "youtube_summarize":
                    try:
                        content_str = tool_output.content if hasattr(tool_output, 'content') else str(tool_output)
                        youtube_data = json.loads(content_str) if isinstance(content_str, str) else content_str
                        if isinstance(youtube_data, dict) and not youtube_data.get("error"):
                            collected_youtube_summary = youtube_data
                    except Exception:
                        pass

                # 차트 데이터 수집 (display 모드)
                if tool_name in ["create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart"]:
                    try:
                        # tool_output 형식 디버깅
                        print(f"[CHART DEBUG] tool_output type: {type(tool_output)}")
                        print(f"[CHART DEBUG] tool_output repr: {repr(tool_output)[:500]}")

                        # content 속성이 있으면 사용, 없으면 str 변환
                        if hasattr(tool_output, 'content'):
                            content_str = tool_output.content
                            print(f"[CHART DEBUG] Using .content attribute")
                        else:
                            content_str = str(tool_output)
                            print(f"[CHART DEBUG] Using str() conversion")

                        print(f"[CHART DEBUG] content_str: {content_str[:300] if content_str else 'None'}...")

                        # JSON 파싱
                        if isinstance(content_str, str) and content_str.strip():
                            chart_data = json.loads(content_str)
                        else:
                            chart_data = content_str

                        print(f"[CHART DEBUG] Parsed chart_data type: {type(chart_data)}")
                        if isinstance(chart_data, dict):
                            print(f"[CHART DEBUG] chart_data keys: {list(chart_data.keys())}")
                            print(f"[CHART DEBUG] chart_data.get('type'): {chart_data.get('type')}")

                        # chart_data 타입 체크 및 SSE 전송
                        if isinstance(chart_data, dict) and chart_data.get("type") == "chart_data":
                            print(f"[CHART] Sending chart_data SSE event for {chart_data.get('chart_type')}")
                            collected_chart_data = chart_data  # DB 저장용으로 수집
                            yield f"data: {json.dumps({'type': 'chart_data', 'chart': chart_data}, ensure_ascii=False)}\n\n"
                        else:
                            print(f"[CHART DEBUG] Skipped - not chart_data type or not dict")
                    except Exception as e:
                        print(f"[CHART ERROR] Failed to process chart data: {e}")
                        import traceback
                        traceback.print_exc()

                # SVG 시각화 데이터 수집
                if tool_name == "create_svg_visual":
                    try:
                        content_str = tool_output.content if hasattr(tool_output, 'content') else str(tool_output)
                        if isinstance(content_str, str) and content_str.strip():
                            svg_data = json.loads(content_str)
                        else:
                            svg_data = content_str

                        if isinstance(svg_data, dict) and svg_data.get("type") == "svg_visual" and svg_data.get("success"):
                            print(f"[SVG] Sending svg_visual SSE event: {svg_data.get('title')}")
                            collected_svg_data = svg_data
                            yield f"data: {json.dumps({'type': 'svg_visual', 'svg_data': svg_data}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        print(f"[SVG ERROR] Failed to process SVG data: {e}")

            elif event_type == "on_chat_model_stream":
                chunk_data = event.get("data", {})
                if "chunk" in chunk_data:
                    msg_chunk = chunk_data["chunk"]
                    content = ""
                    has_tool_use = False

                    if hasattr(msg_chunk, "content"):
                        if isinstance(msg_chunk.content, str):
                            content = msg_chunk.content
                        elif isinstance(msg_chunk.content, list):
                            for item in msg_chunk.content:
                                if isinstance(item, dict):
                                    if "text" in item:
                                        content += item["text"]
                                    elif item.get("type") == "tool_use":
                                        has_tool_use = True
                                elif isinstance(item, str):
                                    content += item
                        # tool_use 블록이 별도 속성으로 올 수 있음
                        # Note: hasattr(msg_chunk, "tool_calls")는 AIMessageChunk에서 항상 True
                        # (기본 빈 리스트 필드) → 실제 값이 있는지 확인해야 함
                        if hasattr(msg_chunk, "tool_use"):
                            has_tool_use = True
                        elif hasattr(msg_chunk, "tool_calls") and msg_chunk.tool_calls:
                            has_tool_use = True

                    # tool_use 블록 생성 감지 시 heartbeat 시작
                    # 매 tool_use마다 재시작 (2번째+ 도구 인수 생성 중에도 피드백 제공)
                    if has_tool_use and not heartbeat_active:
                        yield f"data: {json.dumps({'type': 'tool_status', 'tool': 'preparing', 'message': '🔧 도구를 준비하고 있습니다...'})}\n\n"
                        heartbeat_stop_event.clear()
                        heartbeat_task = asyncio.create_task(
                            heartbeat_producer(event_queue, HEARTBEAT_INTERVAL, heartbeat_stop_event)
                        )
                        heartbeat_active = True
                        print(f"[HEARTBEAT] Started for tool_use generation")

                    if content:
                        # 텍스트 콘텐츠 스트리밍 시작 시 하트비트 중지 (안전 장치)
                        # on_tool_end에서 중지 못한 경우에도 최종 텍스트 응답 시 확실히 중지
                        if heartbeat_active:
                            heartbeat_stop_event.set()
                            heartbeat_active = False
                            print(f"[HEARTBEAT] Stopped (content streaming started)")

                        # <search> 태그 제거 (모델이 도구 대신 텍스트로 출력하는 경우 방지)
                        content = re.sub(r'<search>.*?</search>\s*', '', content)
                        if not content:
                            continue

                        # 모델이 tool_use 대신 텍스트로 도구 호출을 출력하는 경우 필터링
                        # HTML 코멘트(<!--...-->)도 필터링: HANDOFF, NO_RESULTS, FOLLOW_UP 마커 제거
                        _FILTER_OPEN_TAGS = ["<tool_call>", "<tool_response>", "<function_calls>", "<function_result>", "<!--"]
                        _FILTER_CLOSE_TAGS = ["</tool_call>", "</tool_response>", "</function_calls>", "</function_result>", "-->"]
                        _MAX_TAG_LEN = max(len(t) for t in _FILTER_OPEN_TAGS + _FILTER_CLOSE_TAGS)  # 18

                        filtered_content = ""
                        for char in content:
                            _tag_buffer += char
                            if _inside_tool_tag:
                                # 종료 태그 감지
                                if any(_tag_buffer.endswith(t) for t in _FILTER_CLOSE_TAGS):
                                    # HTML 코멘트 캡처 (FOLLOW_UP 후처리용)
                                    if _inside_comment and _tag_buffer.endswith("-->"):
                                        _stripped_comments.append("<!--" + _tag_buffer)
                                    _inside_tool_tag = False
                                    _inside_comment = False
                                    _tag_buffer = ""
                                elif len(_tag_buffer) > 50000:
                                    # 안전장치: 종료 태그 없이 너무 길면 버림
                                    _tag_buffer = ""
                            else:
                                # 시작 태그 감지
                                matched_tag = None
                                for t in _FILTER_OPEN_TAGS:
                                    if _tag_buffer.endswith(t):
                                        matched_tag = t
                                        break
                                if matched_tag:
                                    pre_tag = _tag_buffer[:-len(matched_tag)]
                                    filtered_content += pre_tag
                                    _inside_tool_tag = True
                                    _inside_comment = (matched_tag == "<!--")
                                    _tag_buffer = ""
                                    if not _inside_comment:
                                        _tag_filter_notified = True
                                elif len(_tag_buffer) > _MAX_TAG_LEN:
                                    filtered_content += _tag_buffer
                                    _tag_buffer = ""
                                elif "<" not in _tag_buffer:
                                    filtered_content += _tag_buffer
                                    _tag_buffer = ""

                        # 태그 내부가 아니고 버퍼에 태그 시작 가능성 없으면 flush
                        if not _inside_tool_tag and _tag_buffer and "<" not in _tag_buffer:
                            filtered_content += _tag_buffer
                            _tag_buffer = ""

                        content = filtered_content

                        # 필터링으로 콘텐츠가 비었고, 태그 내부 진입 시 상태 메시지 전송
                        if not content and _tag_filter_notified:
                            _tag_filter_notified = False
                            yield f"data: {json.dumps({'type': 'tool_status', 'tool': 'processing', 'message': '🔍 검색 중입니다...'})}\n\n"
                            continue
                        if not content:
                            continue

                        # Note: Heartbeat는 on_tool_end(모든 도구) 또는 content 수신 시 중지됨
                        # tool_use arguments 생성 중에는 content가 없으므로 하트비트 유지

                        if first_chunk_time is None:
                            first_chunk_time = int((time.time() - start_time) * 1000)
                            # 도구 완료 후 첫 청크까지의 지연 시간 계산
                            if tool_end_time:
                                delay_after_tool = int((time.time() - tool_end_time) * 1000)
                                print(f"[TIMING] First chunk received: {first_chunk_time}ms (delay after tool: {delay_after_tool}ms)")
                                yield f"data: {json.dumps({'type': 'timing', 'step': 'first_chunk', 'timing': {'ms': first_chunk_time, 'delay_after_tool_ms': delay_after_tool}})}\n\n"
                            else:
                                print(f"[TIMING] First chunk received: {first_chunk_time}ms (no tool call)")
                                yield f"data: {json.dumps({'type': 'timing', 'step': 'first_chunk', 'timing': {'ms': first_chunk_time}})}\n\n"

                        # 도구 완료 후 첫 텍스트 → 개행 삽입 (텍스트 붙어버리는 문제 방지)
                        if needs_newline_after_tool:
                            separator = "\n\n"
                            collected_response += separator
                            yield f"data: {json.dumps({'type': 'content', 'chunk': separator})}\n\n"
                            needs_newline_after_tool = False

                        chunk_count += 1
                        collected_response += content
                        last_content_time = time.time()  # 마지막 콘텐츠 시간 기록
                        yield f"data: {json.dumps({'type': 'content', 'chunk': content})}\n\n"

    finally:
        # Orchestrator 태스크 정리
        if not orchestrator_task.done():
            orchestrator_task.cancel()
            try:
                await orchestrator_task
            except asyncio.CancelledError:
                pass

    # Heartbeat cleanup
    if heartbeat_active or heartbeat_task:
        heartbeat_stop_event.set()
        if heartbeat_task and not heartbeat_task.done():
            try:
                await asyncio.wait_for(heartbeat_task, timeout=1.0)
            except asyncio.TimeoutError:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
        print(f"[HEARTBEAT] Cleanup completed")

    # 완료 처리
    complete_start_time = time.time()
    if last_content_time:
        delay_to_complete = int((complete_start_time - last_content_time) * 1000)
        print(f"[TIMING] Delay from last content to complete: {delay_to_complete}ms")  # ← 핵심 지연!

    if collected_youtube_summary:
        yield f"data: {json.dumps({'type': 'youtube_summary', 'summary': collected_youtube_summary}, ensure_ascii=False)}\n\n"

    # 검색된 Corp 문서를 UI에 전송 (유사도 필터링은 RAG 레벨에서 이미 적용됨)
    if all_searched_corp_sources:
        source_map = {}
        for item in all_searched_corp_sources:
            key = item["filename"]
            if key not in source_map:
                source_map[key] = {
                    "filename": item["filename"],
                    "category": item["category"],
                    "similarity": item.get("similarity", 0),
                    "count": 0,
                    "chunks": []
                }
            source_map[key]["count"] += 1
            if item.get("chunk_text"):
                source_map[key]["chunks"].append({
                    "text": item["chunk_text"],
                    "similarity": item.get("similarity", 0)
                })
            # 최고 유사도 유지
            if item.get("similarity", 0) > source_map[key]["similarity"]:
                source_map[key]["similarity"] = item["similarity"]
        yield f"data: {json.dumps({'type': 'corp_sources', 'sources': list(source_map.values())}, ensure_ascii=False)}\n\n"

    # Follow-up suggestions 파싱
    # 스트리밍 중 버퍼링으로 캡처된 코멘트에서 우선 검색, 없으면 collected_response 폴백
    _follow_up_source = " ".join(_stripped_comments) if _stripped_comments else collected_response
    follow_up_match = re.search(r'<!--FOLLOW_UP:\[(.+?)\]-->', _follow_up_source)
    if follow_up_match:
        try:
            collected_follow_ups = json.loads('[' + follow_up_match.group(1) + ']')
            if (isinstance(collected_follow_ups, list)
                    and len(collected_follow_ups) == 3
                    and all(isinstance(s, str) for s in collected_follow_ups)):
                yield f"data: {json.dumps({'type': 'follow_up_suggestions', 'suggestions': collected_follow_ups}, ensure_ascii=False)}\n\n"
                print(f"[FOLLOW_UP] Sending {len(collected_follow_ups)} suggestions")
            else:
                collected_follow_ups = None
        except (json.JSONDecodeError, Exception) as e:
            print(f"[FOLLOW_UP] Parsing failed: {e}")
            collected_follow_ups = None

    # DB 저장용 텍스트에서 마커 및 tool 태그 제거 (항상 실행)
    collected_response = re.sub(r'<tool_call>[\s\S]*?</tool_call>\s*', '', collected_response)
    collected_response = re.sub(r'<tool_response>[\s\S]*?</tool_response>\s*', '', collected_response)
    collected_response = re.sub(r'<function_calls>[\s\S]*?</function_calls>\s*', '', collected_response)
    collected_response = re.sub(r'<function_result>[\s\S]*?</function_result>\s*', '', collected_response)
    collected_response = re.sub(r'<!--NO_RESULTS-->\s*', '', collected_response)
    collected_response = re.sub(r'<!--HANDOFF:\w+-->\s*', '', collected_response)
    collected_response = re.sub(r'\s*<!--FOLLOW_UP:.*?-->\s*$', '', collected_response).rstrip()

    total_time = int((time.time() - start_time) * 1000)
    print(f"[CHAT_STREAM] A2A Completed: {chunk_count} chunks, {total_time}ms")
    yield f"data: {json.dumps({'type': 'timing', 'step': 'complete', 'timing': {'chunk_count': chunk_count, 'total_ms': total_time}, 'chat_mode': chat_mode})}\n\n"
    yield f"data: {json.dumps({'complete': True, 'chat_mode': chat_mode})}\n\n"

    # 수집된 데이터 반환 (로그 저장용)
    # 토큰 사용량 로깅
    if total_input_tokens > 0:
        cache_log = ""
        if total_cache_read_tokens or total_cache_write_tokens:
            cache_log = f" cache_read={total_cache_read_tokens:,} cache_write={total_cache_write_tokens:,}"
        print(f"[CHAT_STREAM] Token usage: input={total_input_tokens:,} output={total_output_tokens:,}{cache_log} llm_calls={total_llm_calls}")

    yield f"data: {json.dumps({'type': '_internal_collected', 'response': collected_response, 'sources': collected_sources, 'youtube_summary': collected_youtube_summary, 'corp_sources': all_searched_corp_sources, 'chart_data': collected_chart_data, 'svg_data': collected_svg_data, 'intent': classified_intent, 'worker_name': classified_worker, 'response_time_ms': int((time.time() - start_time) * 1000), 'is_error': is_error, 'tools_used': tool_calls_made, 'input_tokens': total_input_tokens, 'output_tokens': total_output_tokens, 'cache_read_tokens': total_cache_read_tokens, 'cache_write_tokens': total_cache_write_tokens, 'llm_call_count': total_llm_calls})}\n\n"

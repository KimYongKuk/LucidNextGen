"""채팅 API - 통합 Agent 경로 (LangGraph 기반)"""
import json
import time
import logging
import os
import base64
import io
from datetime import datetime
from typing import Optional, List, Union, Any
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from app.services.bedrock_service import BedrockService, get_bedrock_service
from app.services.chromadb_service import ChromaDBService, get_chromadb_service
from app.services.chat_log_service import ChatLogService, get_chat_log_service
from app.core.model_config import is_hierarchical_agent_enabled
from app.agents.a2a_streaming import stream_a2a_response

logger = logging.getLogger(__name__)
router = APIRouter()

# 세마포어: AWS Bedrock 동시 호출 제한 (RPM 1000 ≈ TPS 16)
# 안전 마진을 위해 15로 설정
BEDROCK_SEMAPHORE = asyncio.Semaphore(15)


# ============================================================================
# Pydantic Models
# ============================================================================

class ImageData(BaseModel):
    media_type: str
    base64_data: str
    stored_filename: Optional[str] = None


class MessageHistory(BaseModel):
    role: str  # "user" or "assistant"
    content: Union[str, List[Any]]  # 문자열 또는 리스트 (멀티모달 지원)


class ChatRequest(BaseModel):
    message: str
    chat_mode: str = "normal"
    session_id: Optional[str] = None
    user_id: str = "anonymous"
    images: Optional[List[ImageData]] = None
    message_history: Optional[List[MessageHistory]] = None
    workspace_id: Optional[str] = None  # UUID string


# ============================================================================
# Image Compression (Bedrock 5MB limit)
# ============================================================================

# Bedrock ConverseStream API는 이미지를 base64 → bytes로 변환 후 전송
# bytes 기준 5MB(5,242,880) 제한 → base64 기준 약 3.93MB
BEDROCK_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5MB (bytes 기준)

def _compress_image_if_needed(base64_data: str, media_type: str) -> tuple[str, str]:
    """Bedrock 5MB 제한 초과 시 이미지를 JPEG 압축하여 반환.

    Returns:
        (compressed_base64, updated_media_type)
    """
    try:
        raw_bytes = base64.b64decode(base64_data)
        if len(raw_bytes) <= BEDROCK_IMAGE_MAX_BYTES:
            return base64_data, media_type

        from PIL import Image

        img = Image.open(io.BytesIO(raw_bytes))

        # RGBA → RGB 변환 (JPEG는 알파 미지원)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        # 1단계: 해상도 축소 (긴 변 4096px 제한)
        max_dim = 4096
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # 2단계: JPEG quality 단계적 하향
        for quality in (85, 70, 50, 30):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= BEDROCK_IMAGE_MAX_BYTES:
                compressed = base64.b64encode(buf.getvalue()).decode("utf-8")
                logger.info(
                    f"[Image Compress] {len(raw_bytes)/1024/1024:.1f}MB → "
                    f"{buf.tell()/1024/1024:.1f}MB (quality={quality})"
                )
                return compressed, "image/jpeg"

        # 3단계: 그래도 초과하면 추가 리사이즈
        for max_d in (2048, 1024):
            ratio = max_d / max(img.size)
            resized = img.resize(
                (int(img.size[0] * ratio), int(img.size[1] * ratio)),
                Image.LANCZOS,
            )
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=50, optimize=True)
            if buf.tell() <= BEDROCK_IMAGE_MAX_BYTES:
                compressed = base64.b64encode(buf.getvalue()).decode("utf-8")
                logger.info(
                    f"[Image Compress] {len(raw_bytes)/1024/1024:.1f}MB → "
                    f"{buf.tell()/1024/1024:.1f}MB (resize={max_d}px)"
                )
                return compressed, "image/jpeg"

        # 최종 폴백: 가장 작은 결과라도 반환
        logger.warning("[Image Compress] Could not compress below 5MB, using best effort")
        compressed = base64.b64encode(buf.getvalue()).decode("utf-8")
        return compressed, "image/jpeg"

    except Exception as e:
        logger.warning(f"[Image Compress] Failed, using original: {e}")
        return base64_data, media_type


# ============================================================================
# Helper Functions
# ============================================================================

async def _save_chat_log_background(
    chat_log,
    user_id: str,
    input_log: str,
    output_log: str,
    session_id: str,
    chat_mode: str,
    metadata: dict,
    workspace_id: Optional[str],  # UUID string
    intent: Optional[str] = None,
    worker_name: Optional[str] = None,
    response_time_ms: Optional[int] = None,
):
    """Background task for saving chat log (prevents streaming delay)"""
    try:
        print(f"[BACKGROUND] Saving chat log: {len(output_log)} chars")
        await chat_log.save_chat_log(
            user_id=user_id,
            input_log=input_log,
            output_log=output_log,
            session=session_id,
            chat_mode=chat_mode,
            category_text="temp",
            metadata=metadata,
            workspace_id=workspace_id,
            intent=intent,
            worker_name=worker_name,
            response_time_ms=response_time_ms,
        )
        print(f"[BACKGROUND] Chat log saved successfully")

        # ============ 워크스페이스 메모리 업데이트 트리거 ============
        print(f"[BACKGROUND] workspace_id={workspace_id}, user_id={user_id}")
        if workspace_id:
            try:
                from app.services.memory_service import get_memory_service
                memory_service = get_memory_service()

                if await memory_service.should_update_summary(workspace_id, user_id):
                    # 비동기 백그라운드 실행 (응답 지연 없음)
                    asyncio.create_task(
                        memory_service.update_summary(workspace_id, user_id)
                    )
                    print(f"[BACKGROUND] Triggered memory update for workspace {workspace_id}")
                else:
                    print(f"[BACKGROUND] Memory update not needed yet for workspace {workspace_id}")
            except Exception as mem_e:
                print(f"[BACKGROUND] Memory update error (non-fatal): {mem_e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[BACKGROUND] No workspace_id, skipping workspace memory update")

        # ============ 전역 사용자 메모리 업데이트 트리거 ============
        if user_id and user_id != "anonymous":
            try:
                from app.services.memory_service import get_user_memory_service, USER_MEMORY_ENABLED
                if USER_MEMORY_ENABLED:
                    user_mem_service = get_user_memory_service()
                    if await user_mem_service.should_extract_facts(user_id):
                        asyncio.create_task(
                            user_mem_service.extract_and_update_facts(user_id)
                        )
                        print(f"[BACKGROUND] Triggered global user memory extraction for {user_id}")
            except Exception as mem_e:
                print(f"[BACKGROUND] User memory update error (non-fatal): {mem_e}")

    except Exception as e:
        print(f"[BACKGROUND] Failed to save chat log: {e}")
        import traceback
        traceback.print_exc()


def _get_current_date_info() -> str:
    """현재 날짜 정보를 한국어로 반환"""
    now = datetime.now()
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    weekday_kr = weekdays[now.weekday()]
    return f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"


def build_system_prompt(
    has_files: bool,
    session_id: Optional[str],
    message_history: Optional[list] = None,
    workspace_id: Optional[str] = None,  # UUID string
    workspace_context: Optional[dict] = None
) -> str:
    """
    파일 존재 여부, 워크스페이스, 대화 히스토리를 고려한 동적 System Prompt 생성

    우선순위 로직 (Workspace 세션 기준):
    1. has_files=True (사용자 파일 업로드됨) → search_user_files 먼저
    2. has_files=False (워크스페이스만 존재) → search_workspace_docs 먼저

    Args:
        has_files: 사용자가 파일을 업로드했는지 여부
        session_id: 세션 ID (파일 검색용)
        message_history: 이전 대화 히스토리
        workspace_id: 워크스페이스 ID
        workspace_context: 워크스페이스 컨텍스트 (uuid, name, instructions)

    Returns:
        완성된 system prompt 문자열
    """
    current_date = _get_current_date_info()

    # Base prompt (모든 경우에 공통)
    base = f"""Today is {current_date}.

You are a helpful AI assistant with access to many tools.

CRITICAL RULE: You MUST use tools for real-time information.
- Simple facts (weather, news, stocks) → Use tavily_search (빠른 검색)
- Deep research/analysis → Use perplexity_research (심층 보고서)
- Complex reasoning tasks → Use perplexity_reason (복잡한 추론)
- YouTube URLs → Use youtube_summarize
- Schedules/Calendar → Use get_schedule_guide + execute_schedule_query
- Board posts → Use get_board_guide + execute_board_query
- Company documents → Use search_hr_docs, search_accounting_docs, etc.

TAVILY vs PERPLEXITY 선택 기준:
- tavily_search: 간단한 정보 조회 (날씨, 주가, 빠른 팩트체크)
- perplexity_research: 주제 심층 분석, 종합 보고서 필요 시
- perplexity_reason: 복잡한 논리/분석 문제, 다단계 추론

DO NOT answer from memory. DO NOT guess. USE TOOLS FIRST.

⚠️ CRITICAL EFFICIENCY RULES (MUST FOLLOW):
1. Call each tool ONLY ONCE per user query
2. NEVER retry the same tool with the same query
3. If a tool returns results (even if partial), USE THEM and move on
4. DO NOT call the same tool multiple times to "get more information"
5. You CAN combine DIFFERENT tools (e.g., search_hr_docs + tavily_search)
6. After tool execution completes, immediately use the results to answer

VIOLATION EXAMPLES (DO NOT DO THIS):
❌ Call search_hr_docs twice in one turn
❌ Call search_safety_docs multiple times with similar queries
❌ Retry a tool that already returned valid results

CORRECT USAGE:
✓ Call search_hr_docs once, get results, answer immediately
✓ Call search_hr_docs + tavily_search (different tools) if both needed"""

    # 워크스페이스 컨텍스트 확인
    workspace_uuid = workspace_context.get("uuid") if workspace_context else None
    workspace_name = workspace_context.get("name", "Workspace") if workspace_context else None
    workspace_instructions = workspace_context.get("instructions") if workspace_context else None

    # ============================================================================
    # 우선순위 결정 로직 (Workspace 세션 기준)
    # ============================================================================

    if has_files and session_id:
        # Case 1: 사용자 파일 업로드됨 → user_files 최우선
        file_priority = f"""

🔴 CRITICAL PRIORITY: User has uploaded files in session {session_id}.

FILE SEARCH PRIORITY (MUST FOLLOW THIS ORDER):
1st: ALWAYS use search_user_files FIRST for ANY question
2nd: You MAY ALSO use other tools (workspace docs, web search) as supplementary sources

USER FILE RULES:
- User does NOT need to mention "file" or "document" keywords
- Even for greetings or simple questions, acknowledge the uploaded files
- COMBINE with other tools when appropriate:
  - "file analysis + latest news" → search_user_files + tavily_search
  - "file + company policy" → search_user_files + search_hr_docs

When calling search_user_files, always pass session_id="{session_id}"."""
        base += file_priority

        # 워크스페이스도 있는 경우 → secondary로 추가 (단, 워크스페이스에 파일이 있을 때만)
        if workspace_uuid:
            workspace_has_docs = workspace_context.get("has_files", False) if workspace_context else False
            if workspace_has_docs:
                workspace_secondary = f"""

SECONDARY SOURCE: User is also in workspace "{workspace_name}" (UUID: {workspace_uuid}).

WORKSPACE AS SECONDARY:
- After checking uploaded files, you MAY ALSO use search_workspace_docs for additional context
- Use search_workspace_docs(workspace_uuid="{workspace_uuid}") as supplementary source
- This is SECONDARY to user-uploaded files"""
                base += workspace_secondary
            else:
                # 워크스페이스에 파일이 없으면 도구 호출 지시 없이 컨텍스트만 알림
                workspace_notice = f"""

WORKSPACE CONTEXT: User is in workspace "{workspace_name}".
Note: No documents have been uploaded to this workspace yet. Focus on uploaded session files."""
                base += workspace_notice

    elif workspace_uuid:
        # Case 2: 워크스페이스만 존재 (사용자 파일 없음)
        workspace_has_docs = workspace_context.get("has_files", False) if workspace_context else False

        if workspace_has_docs:
            # 워크스페이스에 문서가 있으면 → search_workspace_docs 최우선
            workspace_priority = f"""

🔴 CRITICAL PRIORITY: User is in workspace "{workspace_name}" (UUID: {workspace_uuid}).
User has NOT uploaded any files in this session.

WORKSPACE SEARCH PRIORITY (MUST FOLLOW THIS ORDER):
1st: ALWAYS use search_workspace_docs FIRST for ANY question
2nd: You MAY ALSO use other tools (web search, corp docs) as supplementary sources

WORKSPACE RULES:
- User does NOT need to mention "file" or "document" keywords
- Even for greetings or simple questions, acknowledge the workspace context
- MANDATORY: search_workspace_docs(workspace_uuid="{workspace_uuid}")

When calling search_workspace_docs, always pass workspace_uuid="{workspace_uuid}"."""
            base += workspace_priority
        else:
            # 워크스페이스에 문서가 없으면 → 도구 호출 지시 없이 컨텍스트만 알림
            workspace_empty = f"""

WORKSPACE CONTEXT: User is in workspace "{workspace_name}".
Note: No documents have been uploaded to this workspace yet.
- Do NOT call search_workspace_docs (no documents available)
- Answer questions using your general knowledge or other available tools (web search, corp docs)
- If the user asks about workspace documents, inform them that no files have been uploaded yet"""
            base += workspace_empty

    elif session_id:
        # Case 3: 세션만 존재 (워크스페이스 없음, 파일 업로드 여부는 has_files로 확인됨)
        # 이 경우는 has_files=False이지만 session_id가 있는 경우 (아직 파일 없는 일반 세션)
        pass  # 특별한 우선순위 없음

    # 워크스페이스 instructions 추가 (있는 경우)
    if workspace_instructions:
        instructions_section = f"""

WORKSPACE INSTRUCTIONS (Follow these guidelines):
{workspace_instructions}"""
        base += instructions_section

    # 멀티턴 대화 강화 (조건부 추가)
    if message_history and len(message_history) > 0:
        multiturn = """

For real-time data (schedules, news, weather), always use tools even if you answered before."""
        base += multiturn

    # 포맷팅 규칙 (모든 경우에 공통)
    formatting = """

FORMATTING RULES:
- Answer in Korean with markdown formatting
- Use professional tone without emojis
- Be clear, concise, and refined in your responses
- Use markdown horizontal rules (---) to separate major sections
- CRITICAL: Always add a horizontal rule (---) before the summary section
- ALWAYS end your response with a summary section that briefly recaps the key points of your answer

Example format:
[Main content here]

---

**요약:**
[Summary of key points]"""

    # 디버그 로그
    workspace_has_docs = workspace_context.get("has_files", False) if workspace_context else False
    print(f"[SYSTEM_PROMPT] Priority: has_files={has_files}, workspace={bool(workspace_uuid)}, workspace_has_docs={workspace_has_docs}, session={bool(session_id)}")

    return base + formatting


def build_message_payload(request) -> list:
    """
    메시지 히스토리 + 이미지 + 현재 메시지를 LangChain 형식으로 결합

    Args:
        request: ChatRequest 객체

    Returns:
        LangChain Message 객체 리스트
    """
    messages = []

    # 이전 대화 히스토리 추가
    if request.message_history:
        for msg in request.message_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

    # 현재 메시지 (이미지 포함 가능, Bedrock 5MB 제한 초과 시 자동 압축)
    if request.images:
        image_contents = []
        for img in request.images:
            # Pydantic 모델 또는 딕셔너리 처리
            if hasattr(img, "media_type"):
                media_type = img.media_type
                data = img.base64_data
            else:
                media_type = img.get("media_type", "image/jpeg")
                data = img.get("base64_data", "")

            if data:
                data, media_type = _compress_image_if_needed(data, media_type)
                image_contents.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data
                    }
                })

        messages.append(HumanMessage(content=[
            *image_contents,
            {"type": "text", "text": request.message}
        ]))
    else:
        messages.append(HumanMessage(content=request.message))

    return messages


# ============================================================================
# Main Chat API
# ============================================================================

@router.post("/v1/chat/message/stream")
async def chat_stream(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    bedrock: BedrockService = Depends(get_bedrock_service),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
):
    """
    LangGraph 기반 채팅 스트리밍 (통합 Agent 경로)

    Agent가 필요에 따라 자동으로 도구를 조합하여 사용:
    - search_user_files (파일 검색)
    - tavily_search (웹 검색)
    - search_hr_docs, search_accounting_docs 등 (사내 문서)
    - YouTube, 일정, 게시판 등 (기타 도구)
    """
    chat_log = get_chat_log_service(bedrock_service=bedrock)

    print("\n" + "="*60)
    print(f"[CHAT_STREAM] Unified Agent API CALLED!")
    print(f"  User ID: {request.user_id}")
    print(f"  Session ID: {request.session_id}")
    print(f"  Message: {request.message[:50]}...")
    print(f"  Chat Mode: {request.chat_mode}")
    print("="*60 + "\n")

    start_time = time.time()

    async def generate():
        collected_response = ""
        collected_sources = []
        collected_youtube_summary = None
        chunk_count = 0
        first_chunk_time = None
        chat_mode = "general"
        is_a2a_route = False  # A2A 경로 플래그 (finally에서 중복 저장 방지)

        try:
            # 세마포어 대기 시작 알림
            semaphore_locked = BEDROCK_SEMAPHORE.locked()
            if semaphore_locked:
                print(f"[SEMAPHORE] Queue is full, user will wait...")
                yield f"data: {json.dumps({'type': 'waiting', 'message': '다른 사용자의 요청을 처리 중입니다. 잠시만 기다려주세요...'})}\n\n"

            # 세마포어 획득 (대기 시작)
            semaphore_wait_start = time.time()
            async with BEDROCK_SEMAPHORE:
                semaphore_wait_time = int((time.time() - semaphore_wait_start) * 1000)

                if semaphore_wait_time > 100:  # 100ms 이상 대기했으면 로그
                    print(f"[SEMAPHORE] Waited {semaphore_wait_time}ms to acquire semaphore")
                    yield f"data: {json.dumps({'type': 'waiting_complete', 'wait_time_ms': semaphore_wait_time})}\n\n"

                print(f"[SEMAPHORE] Acquired! Processing request...")
                yield f"data: {json.dumps({'type': 'processing_start'})}\n\n"

                # 1. 파일 존재 여부 확인 (프롬프트 컨텍스트용)
                has_files = False
                if request.session_id:
                    check_start = time.time()
                    has_files = chromadb.has_session_files(request.session_id)
                    check_time = int((time.time() - check_start) * 1000)
                    print(f"[CHAT_STREAM] File check: {has_files} ({check_time}ms)")

                # 2. 통합 Agent 경로 (모든 요청)
                print("[CHAT_STREAM] Route: Unified Agent")
                print(f"[CHAT_STREAM] has_files: {has_files}")
                print(f"[CHAT_STREAM] Model: {os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')}")
                print("="*60)

                # === 1. MCP Adapter 로드 ===
                mcp_adapter_start = time.time()
                print("[TIMING] [1/4] MCP Adapter loading...")

                from app.main import get_mcp_adapter
                adapter = await get_mcp_adapter()

                mcp_adapter_time = int((time.time() - mcp_adapter_start) * 1000)
                print(f"[TIMING] [1/4] MCP Adapter loaded: {mcp_adapter_time}ms")

                # === 2. Tools 가져오기 ===
                tools_start = time.time()
                print("[TIMING] [2/4] Getting MCP tools...")
                tools = await adapter.get_tools()
                tools_time = int((time.time() - tools_start) * 1000)
                print(f"[TIMING] [2/4] Tools ready: {tools_time}ms ({len(tools)} tools)")
                print(f"[DEBUG] Available tool names: {[t.name for t in tools]}")

                # ============================================================
                # A2A Hierarchical Agent 경로 (Feature Flag)
                # ============================================================
                if is_hierarchical_agent_enabled():
                    is_a2a_route = True  # A2A 경로 플래그 설정
                    print("[CHAT_STREAM] Route: A2A Hierarchical Agent")

                    # 워크스페이스 컨텍스트 조회 (workspace_id is now UUID)
                    workspace_context = None
                    if request.workspace_id:
                        from app.services.workspace_service import get_workspace_service
                        workspace_service = get_workspace_service()
                        workspace_data = workspace_service.get_workspace_by_uuid(request.workspace_id)
                        if workspace_data:
                            workspace_has_files = workspace_service.has_files(workspace_data["id"])
                            # 워크스페이스에 파일이 있으면 파일명 목록도 로드 (인텐트 분류용)
                            file_names = []
                            if workspace_has_files:
                                try:
                                    files = workspace_service.list_files(workspace_data["id"])
                                    file_names = [f["filename"] for f in files]
                                except Exception:
                                    pass
                            workspace_context = {
                                "uuid": workspace_data.get("uuid"),
                                "name": workspace_data.get("name"),
                                "description": workspace_data.get("description"),
                                "instructions": workspace_data.get("instructions"),
                                "has_files": workspace_has_files,
                                "file_names": file_names,
                            }
                            print(f"[CHAT_STREAM] Workspace context loaded: {workspace_data.get('name')} (has_files={workspace_has_files}, files={file_names})")

                    # 메시지 히스토리 변환
                    msg_history = None
                    if request.message_history:
                        msg_history = [{"role": m.role, "content": m.content} for m in request.message_history]

                    # 이미지 변환 (Bedrock 5MB 제한 초과 시 자동 압축)
                    img_data = None
                    if request.images:
                        img_data = []
                        for i in request.images:
                            compressed_data, compressed_type = _compress_image_if_needed(
                                i.base64_data, i.media_type
                            )
                            img_data.append({"media_type": compressed_type, "base64_data": compressed_data})

                    # A2A 스트리밍 위임
                    a2a_collected_data = {}
                    async for sse in stream_a2a_response(
                        message=request.message,
                        user_id=request.user_id,
                        session_id=request.session_id,
                        workspace_id=request.workspace_id,
                        workspace_context=workspace_context,
                        has_files=has_files,
                        chat_mode=request.chat_mode,
                        message_history=msg_history,
                        images=img_data,
                        all_tools=tools,
                        start_time=start_time,
                    ):
                        # 내부 수집 데이터 처리
                        if '"type": "_internal_collected"' in sse:
                            try:
                                a2a_collected_data = json.loads(sse.replace("data: ", "").strip())
                            except Exception:
                                pass
                            continue
                        yield sse

                    # A2A 경로 로그 저장 (BackgroundTasks로 비동기 처리 - 지연 방지)
                    if request.session_id and a2a_collected_data.get("response"):
                        metadata = {
                            "sources": a2a_collected_data.get("sources", []),
                        }
                        if a2a_collected_data.get("youtube_summary"):
                            metadata["youtube_summary"] = a2a_collected_data["youtube_summary"]
                        if a2a_collected_data.get("corp_sources"):
                            metadata["corp_sources"] = a2a_collected_data["corp_sources"]
                        if a2a_collected_data.get("chart_data"):
                            metadata["chart_data"] = a2a_collected_data["chart_data"]
                        if a2a_collected_data.get("svg_data"):
                            metadata["svg_data"] = a2a_collected_data["svg_data"]
                        if a2a_collected_data.get("is_error"):
                            metadata["is_error"] = True
                        if a2a_collected_data.get("tools_used"):
                            metadata["tools_used"] = a2a_collected_data["tools_used"]
                        if a2a_collected_data.get("input_tokens"):
                            metadata["input_tokens"] = a2a_collected_data["input_tokens"]
                            metadata["output_tokens"] = a2a_collected_data.get("output_tokens", 0)
                            metadata["llm_call_count"] = a2a_collected_data.get("llm_call_count", 0)
                            metadata["cache_read_tokens"] = a2a_collected_data.get("cache_read_tokens", 0)
                            metadata["cache_write_tokens"] = a2a_collected_data.get("cache_write_tokens", 0)
                        if request.images:
                            metadata["image_count"] = len(request.images)
                            image_refs = [
                                {"stored_filename": img.stored_filename, "media_type": img.media_type}
                                for img in request.images if img.stored_filename
                            ]
                            if image_refs:
                                metadata["images"] = image_refs

                        print(f"[CHAT_STREAM] A2A scheduling background save: {len(a2a_collected_data.get('response', ''))} chars")
                        background_tasks.add_task(
                            _save_chat_log_background,
                            chat_log,
                            request.user_id,
                            request.message,
                            a2a_collected_data.get("response", ""),
                            request.session_id,
                            chat_mode,
                            metadata,
                            request.workspace_id,
                            a2a_collected_data.get("intent"),
                            a2a_collected_data.get("worker_name"),
                            a2a_collected_data.get("response_time_ms"),
                        )

                    return  # A2A 경로 종료 (finally 블록에서 저장하지 않음)


                # ============================================================
                # Legacy 단일 Agent 경로
                # ============================================================
                print("[CHAT_STREAM] Route: Legacy Single Agent")

                # 워크스페이스 컨텍스트 조회 (A2A와 동일, workspace_id is UUID)
                workspace_context = None
                if request.workspace_id:
                    from app.services.workspace_service import get_workspace_service
                    workspace_service = get_workspace_service()
                    workspace_data = workspace_service.get_workspace_by_uuid(request.workspace_id)
                    if workspace_data:
                        workspace_has_files = workspace_service.has_files(workspace_data["id"])
                        workspace_context = {
                            "uuid": workspace_data.get("uuid"),
                            "name": workspace_data.get("name"),
                            "instructions": workspace_data.get("instructions"),
                            "has_files": workspace_has_files,
                        }
                        print(f"[CHAT_STREAM] Workspace context loaded: {workspace_data.get('name')} (has_files={workspace_has_files})")

                # === 3. System Prompt 동적 생성 ===
                agent_create_start = time.time()
                print("[TIMING] [3/4] Creating LangGraph Agent with dynamic prompt...")

                system_prompt = build_system_prompt(
                    has_files=has_files,
                    session_id=request.session_id,
                    message_history=request.message_history,
                    workspace_id=request.workspace_id,
                    workspace_context=workspace_context
                )
                print(f"[AGENT] System prompt generated (has_files={has_files}, workspace={bool(workspace_context)})")

                # === 4. Agent 생성 ===
                llm = ChatBedrockConverse(
                    model=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
                    temperature=0.7,
                    max_tokens=8192,
                    disable_streaming=False,
                )
                agent = create_react_agent(llm, tools, state_modifier=system_prompt)
                agent_create_time = int((time.time() - agent_create_start) * 1000)
                print(f"[TIMING] [3/4] Agent created: {agent_create_time}ms")
                print("="*60)

                # === 5. 메시지 준비 ===
                messages = build_message_payload(request)
                message_payload = {"messages": messages}
                print(f"[AGENT] Total messages in payload: {len(messages)}")

                yield f"data: {json.dumps({'type': 'timing', 'step': 'agent_start'})}\n\n"

                # === 6. Agent 스트리밍 실행 ===
                print("[TIMING] [4/4] Streaming Agent execution started...")
                agent_start = time.time()

                tool_calls_made = []
                is_streaming_content = False
                buffered_chunks = []
                is_tool_running = False

                print("[AGENT] Starting astream_events with version='v2'")

                async for event in agent.astream_events(message_payload, version="v2"):
                    event_type = event.get("event")

                    # Tool 호출 시작
                    if event_type == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        if tool_name not in tool_calls_made:
                            tool_calls_made.append(tool_name)
                            is_tool_running = True

                            tool_input = event.get("data", {}).get("input", {})
                            print(f"[AGENT] Tool calling: {tool_name}")
                            print(f"[CoT] Tool input: {str(tool_input)[:200]}")

                            # 버퍼 플러시
                            if buffered_chunks:
                                print(f"[AGENT] Flushing {len(buffered_chunks)} buffered chunks")
                                if len(tool_calls_made) > 1:
                                    chunk_count += 1
                                    collected_response += "\n"
                                    yield f"data: {json.dumps({'type': 'content', 'chunk': '\\n'})}\n\n"
                                for buffered_content in buffered_chunks:
                                    chunk_count += 1
                                    collected_response += buffered_content
                                    yield f"data: {json.dumps({'type': 'content', 'chunk': buffered_content})}\n\n"
                                buffered_chunks = []

                            # Tool 상태 메시지
                            tool_messages = {
                                "tavily_search": "🔍 도구를 사용하여 웹 검색하겠습니다...",
                                "search_user_files": "📄 도구를 사용하여 업로드된 파일을 검색하겠습니다...",
                                "youtube_summarize": "📺 도구를 사용하여 YouTube 영상을 요약하겠습니다...",
                                "get_schedule_guide": "📅 일정 가이드를 조회하겠습니다...",
                                "execute_schedule_query": "🔎 일정 DB를 쿼리하겠습니다...",
                            }
                            status_msg = tool_messages.get(tool_name, f"🔧 도구를 사용하여 작업하겠습니다... ({tool_name})")
                            yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': status_msg})}\n\n"

                    # Tool 호출 완료
                    elif event_type == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        is_tool_running = False

                        tool_output = event.get("data", {}).get("output", "")
                        print(f"[AGENT] Tool completed: {tool_name}")
                        print(f"[CoT] Tool output: {str(tool_output)[:200]}...")

                        # YouTube 요약 메타데이터 수집
                        if tool_name == "youtube_summarize":
                            try:
                                content_str = tool_output
                                if hasattr(tool_output, 'content'):
                                    content_str = tool_output.content
                                elif not isinstance(tool_output, str):
                                    content_str = str(tool_output)

                                youtube_data = json.loads(content_str) if isinstance(content_str, str) else content_str

                                if isinstance(youtube_data, dict) and not youtube_data.get("error"):
                                    print(f"[YOUTUBE] Summary received: {youtube_data.get('title', 'N/A')[:50]}...")
                                    collected_youtube_summary = youtube_data
                            except Exception as e:
                                print(f"[YOUTUBE] Error processing summary: {str(e)}")

                        # Tavily 검색 결과 처리 (모든 tavily 관련 도구 포함)
                        if "tavily" in tool_name.lower():
                            print(f"[TAVILY] Processing search results...")
                            print(f"[TAVILY] Raw tool_output type: {type(tool_output)}")
                            print(f"[TAVILY] Raw tool_output (first 500 chars): {str(tool_output)[:500]}")

                            sources_data = []

                            # 타입 변환
                            if hasattr(tool_output, 'content'):
                                tool_output = tool_output.content
                                print(f"[TAVILY] Extracted .content: {str(tool_output)[:500]}")
                            elif not isinstance(tool_output, (str, list, dict)):
                                tool_output = str(tool_output)

                            # JSON 파싱 시도
                            if isinstance(tool_output, str):
                                stripped = tool_output.strip()
                                if stripped.startswith("{") or stripped.startswith("["):
                                    try:
                                        tool_output = json.loads(stripped)
                                        print(f"[TAVILY] Parsed JSON successfully")
                                    except Exception as e:
                                        print(f"[TAVILY] JSON parse failed: {e}")
                                        pass

                            # 출처 추출
                            if isinstance(tool_output, list):
                                print(f"[TAVILY] tool_output is list with {len(tool_output)} items")
                                for result in tool_output[:5]:
                                    if isinstance(result, dict) and 'url' in result:
                                        sources_data.append({
                                            'url': result['url'],
                                            'title': result.get('title', ''),
                                            'score': result.get('score', 0)
                                        })
                            elif isinstance(tool_output, dict):
                                print(f"[TAVILY] tool_output is dict with keys: {list(tool_output.keys())}")
                                if 'results' in tool_output:
                                    print(f"[TAVILY] Found 'results' key with {len(tool_output['results'])} items")
                                    for result in tool_output['results'][:5]:
                                        if isinstance(result, dict) and 'url' in result:
                                            sources_data.append({
                                                'url': result['url'],
                                                'title': result.get('title', ''),
                                                'score': result.get('score', 0)
                                            })
                                else:
                                    print(f"[TAVILY] No 'results' key found in dict")
                            elif isinstance(tool_output, str):
                                # 텍스트 형식 파싱 (Tavily MCP의 기본 출력 형식)
                                print(f"[TAVILY] Attempting to parse text format...")
                                import re
                                # "Title: ... \nURL: ... \nContent: ..." 패턴 찾기
                                pattern = r'Title:\s*(.+?)\s*\nURL:\s*(.+?)(?:\s*\nContent:|$)'
                                matches = re.findall(pattern, tool_output, re.MULTILINE | re.DOTALL)

                                if matches:
                                    print(f"[TAVILY] Found {len(matches)} sources via text parsing")
                                    for i, (title, url) in enumerate(matches[:5]):
                                        title = title.strip()
                                        url = url.strip()
                                        if url.startswith('http'):
                                            sources_data.append({
                                                'url': url,
                                                'title': title,
                                                'score': 1.0 - (i * 0.1)  # 순서 기반 점수
                                            })
                                else:
                                    print(f"[TAVILY] No text pattern matches found")
                            else:
                                print(f"[TAVILY] tool_output is neither list, dict, nor string, type: {type(tool_output)}")

                            if sources_data:
                                print(f"[TAVILY] ✓ Sending {len(sources_data)} sources to frontend")
                                for i, src in enumerate(sources_data):
                                    print(f"[TAVILY]   [{i+1}] {src['title'][:50]}... - {src['url']}")
                                collected_sources.extend(sources_data)
                                yield f"data: {json.dumps({'type': 'search_sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"
                            else:
                                print(f"[TAVILY] ✗ No sources extracted from tool output")

                    # LLM 스트리밍 출력
                    elif event_type == "on_chat_model_stream":
                        chunk_data = event.get("data", {})

                        if "chunk" in chunk_data:
                            msg_chunk = chunk_data["chunk"]
                            content = ""

                            # AIMessageChunk 처리
                            if hasattr(msg_chunk, "content"):
                                if isinstance(msg_chunk.content, str):
                                    content = msg_chunk.content
                                elif isinstance(msg_chunk.content, list):
                                    for item in msg_chunk.content:
                                        if isinstance(item, dict) and "text" in item:
                                            content += item["text"]
                                        elif isinstance(item, str):
                                            content += item

                            # dict 타입 처리
                            elif isinstance(msg_chunk, dict):
                                if "messages" in msg_chunk:
                                    messages_list = msg_chunk["messages"]
                                    if isinstance(messages_list, list) and len(messages_list) > 0:
                                        last_msg = messages_list[-1]

                                        # ToolMessage 스킵
                                        if type(last_msg).__name__ == "ToolMessage":
                                            content = ""
                                        elif hasattr(last_msg, "content"):
                                            msg_content = last_msg.content
                                            if isinstance(msg_content, str):
                                                content = msg_content
                                            elif isinstance(msg_content, list):
                                                for item in msg_content:
                                                    if isinstance(item, dict) and "text" in item:
                                                        content += item["text"]
                                                    elif isinstance(item, str):
                                                        content += item

                            # 실제 텍스트 청크만 처리
                            if content:
                                if not is_streaming_content:
                                    is_streaming_content = True
                                    print("[AGENT] Started streaming LLM response")

                                if first_chunk_time is None:
                                    first_chunk_time = int((time.time() - start_time) * 1000)
                                    yield f"data: {json.dumps({'type': 'timing', 'step': 'first_chunk', 'timing': {'ms': first_chunk_time}})}\n\n"
                                    print(f"[TIMING] First chunk received: {first_chunk_time}ms")

                                # Tool 실행 중이면 버퍼링, 아니면 즉시 전송
                                if is_tool_running:
                                    buffered_chunks.append(content)
                                else:
                                    # 수동 청킹 (5자씩)
                                    CHUNK_SIZE = 5
                                    for i in range(0, len(content), CHUNK_SIZE):
                                        mini_chunk = content[i:i+CHUNK_SIZE]
                                        chunk_count += 1
                                        collected_response += mini_chunk
                                        yield f"data: {json.dumps({'type': 'content', 'chunk': mini_chunk})}\n\n"
                                        await asyncio.sleep(0.005)

            # 남은 버퍼 플러시
            if buffered_chunks:
                print(f"[AGENT] Flushing {len(buffered_chunks)} remaining buffered chunks")
                if tool_calls_made:
                    chunk_count += 1
                    collected_response += "\n"
                    yield f"data: {json.dumps({'type': 'content', 'chunk': '\\n'})}\n\n"
                for buffered_content in buffered_chunks:
                    chunk_count += 1
                    collected_response += buffered_content
                    yield f"data: {json.dumps({'type': 'content', 'chunk': buffered_content})}\n\n"

            agent_time = int((time.time() - agent_start) * 1000)
            print(f"[TIMING] [4/4] Agent streaming complete: {agent_time}ms")
            print(f"[AGENT] Tools used: {', '.join(tool_calls_made) if tool_calls_made else 'None'}")
            print("="*60)

            # YouTube 요약 전송
            if collected_youtube_summary:
                print(f"[YOUTUBE] Sending summary after response completion")
                yield f"data: {json.dumps({'type': 'youtube_summary', 'summary': collected_youtube_summary}, ensure_ascii=False)}\n\n"

            # 완료 메시지 전송 전에 BackgroundTasks로 DB 저장 예약 (지연 방지)
            if not is_a2a_route and request.session_id and collected_response:
                response_to_save = collected_response if isinstance(collected_response, str) else str(collected_response)
                metadata = {
                    "sources": collected_sources if collected_sources else [],
                }
                if collected_youtube_summary:
                    metadata["youtube_summary"] = collected_youtube_summary

                print(f"[CHAT_STREAM] Scheduling background save: {len(response_to_save)} chars, {len(collected_sources)} sources")
                background_tasks.add_task(
                    _save_chat_log_background,
                    chat_log,
                    request.user_id,
                    request.message,
                    response_to_save,
                    request.session_id,
                    chat_mode,
                    metadata,
                    request.workspace_id,
                )

            # 완료 메시지
            total_time = int((time.time() - start_time) * 1000)
            model_used = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
            print(f"[CHAT_STREAM] Completed: {chunk_count} chunks, {total_time}ms, {len(collected_response)} chars")
            print(f"[CHAT_STREAM] Model used: {model_used}")
            yield f"data: {json.dumps({'type': 'timing', 'step': 'complete', 'timing': {'chunk_count': chunk_count, 'total_ms': total_time}, 'chat_mode': chat_mode})}\n\n"
            yield f"data: {json.dumps({'complete': True, 'chat_mode': chat_mode})}\n\n"

        except Exception as e:
            error_msg = str(e)
            print(f"\n[ERROR] Stream error: {error_msg}\n")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

        finally:
            # DB 저장은 이제 BackgroundTasks에서 처리됨 (스트리밍 지연 방지)
            if is_a2a_route:
                print("[CHAT_STREAM] A2A route - save handled internally")
            else:
                print("[CHAT_STREAM] Legacy route - save scheduled via BackgroundTasks")

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================================
# Session Management APIs
# ============================================================================

@router.get("/v1/chat/sessions")
async def list_chat_sessions(
    user_id: str = Query(...),
    range_scope: str = Query("recent7", alias="range"),
    chat_mode: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),  # UUID string
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """사용자 세션 목록 조회 (최근 7일/전체, 커서 페이지네이션)"""
    try:
        result = chat_log.list_sessions(
            user_id=user_id,
            chat_mode=chat_mode,
            range_scope=range_scope,
            limit=limit,
            cursor=cursor,
            workspace_id=workspace_id,
        )
        return {
            "sessions": result["sessions"],
            "hasMore": result["has_more"],
            "nextCursor": result["next_cursor"],
            "status": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch chat sessions")


@router.get("/v1/chat/sessions/search")
async def search_chat_sessions(
    user_id: str = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """대화 세션 검색 (제목 및 메시지 내용 기반, 전역 검색)"""
    try:
        sessions = chat_log.search_sessions(
            user_id=user_id,
            query=q,
            limit=limit,
        )
        return {
            "sessions": sessions,
            "query": q,
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Failed to search sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to search sessions")


@router.patch("/v1/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    title: Optional[str] = Query(None),
    chat_mode: Optional[str] = Query(None),
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """세션 메타데이터 수정 (제목, 모드)"""
    if title is None and chat_mode is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    if chat_mode and chat_mode not in ("normal", "corp"):
        raise HTTPException(status_code=400, detail="Invalid chat_mode")
    try:
        updated = chat_log.update_session(
            session_id=session_id,
            title=title,
            chat_mode=chat_mode,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "ok", "session_id": session_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update session")


@router.get("/v1/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """세션 메시지 히스토리 조회"""
    try:
        messages = chat_log.get_session_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

        # 세션 정보에서 workspace_id 가져오기
        session_info = chat_log.get_session(session_id)
        workspace_id = session_info.get("workspace_id") if session_info else None

        return {
            "session_id": session_id,
            "messages": messages,
            "total_count": len(messages),
            "workspace_id": workspace_id,
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Failed to fetch session messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@router.delete("/v1/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Query(...),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """세션 삭제 (업로드된 파일 포함)"""
    try:
        # 세션과 연관된 파일 삭제
        result = await chromadb.delete_session_files(session_id)
        # 메타데이터 및 로그 삭제
        chat_log.delete_session(session_id)
        return {
            "status": "ok",
            "message": "Session deleted successfully",
            "session_id": session_id,
            "files_deleted": result.get("success", False)
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete session")


class PinRequest(BaseModel):
    is_pinned: bool


@router.post("/v1/chat/sessions/{session_id}/pin")
async def toggle_session_pin(
    session_id: str,
    request: PinRequest,
    chat_log: ChatLogService = Depends(get_chat_log_service),
):
    """세션 고정/해제 (Pin/Unpin)"""
    try:
        success = chat_log.toggle_pin_status(session_id, request.is_pinned)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "status": "ok",
            "session_id": session_id,
            "is_pinned": request.is_pinned
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle pin status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update pin status")

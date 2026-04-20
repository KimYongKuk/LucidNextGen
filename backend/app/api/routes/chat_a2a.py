"""A2A (Agent-to-Agent) 채팅 API - 별도 엔드포인트"""

import json
import time
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.chromadb_service import ChromaDBService, get_chromadb_service
from app.services.chat_log_service import get_chat_log_service
from app.services.bedrock_service import get_bedrock_service
from app.agents.a2a_streaming import stream_a2a_response

router = APIRouter()

# 세마포어: AWS Bedrock 동시 호출 제한
BEDROCK_LIMIT = 15
BEDROCK_SEMAPHORE = asyncio.Semaphore(BEDROCK_LIMIT)


class ImageData(BaseModel):
    media_type: str
    base64_data: str


class MessageHistory(BaseModel):
    role: str
    content: str | List


class A2AChatRequest(BaseModel):
    message: str
    chat_mode: str = "normal"
    session_id: Optional[str] = None
    user_id: str = "anonymous"
    images: Optional[List[ImageData]] = None
    message_history: Optional[List[MessageHistory]] = None
    workspace_id: Optional[str] = None  # UUID string


@router.post("/v1/chat/a2a/stream")
async def chat_a2a_stream(
    request: A2AChatRequest,
    chromadb: ChromaDBService = Depends(get_chromadb_service),
):
    """
    A2A Hierarchical Agent 채팅 스트리밍

    Orchestrator(Haiku)가 의도를 분류하고 적절한 Worker에게 위임
    """
    bedrock = get_bedrock_service()
    chat_log = get_chat_log_service(bedrock_service=bedrock)

    print("\n" + "="*60)
    print(f"[A2A_CHAT] A2A Hierarchical Agent API CALLED!")
    print(f"  User ID: {request.user_id}")
    print(f"  Session ID: {request.session_id}")
    print(f"  Message: {request.message[:50]}...")
    print(f"  Chat Mode: {request.chat_mode}")
    print(f"  Workspace ID: {request.workspace_id}")
    print("="*60 + "\n")

    start_time = time.time()

    async def generate():
        collected_response = ""

        try:
            # ── Security Guard: 기존 차단 사용자 조기 단절 ──
            try:
                from app.services.security_guard_service import (
                    get_security_guard_service, SECURITY_GUARD_ENABLED
                )
                if SECURITY_GUARD_ENABLED and request.user_id and request.user_id != "anonymous":
                    guard = get_security_guard_service()
                    block_status = await guard.get_block_status(request.user_id)
                    if block_status.blocked:
                        blocked_msg = guard._build_blocked_message(block_status)
                        print(f"[A2A_CHAT] Early block: user={request.user_id}, type={block_status.block_type}")
                        yield f"data: {json.dumps({'type': 'security_blocked', 'block_type': block_status.block_type, 'message': blocked_msg, 'expires_at': block_status.expires_at.isoformat() if block_status.expires_at else None})}\n\n"
                        yield f"data: {json.dumps({'type': 'content', 'content': blocked_msg})}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return
            except Exception as sec_e:
                print(f"[A2A_CHAT] Security early-check error (non-fatal): {sec_e}")

            # 세마포어 대기
            semaphore_locked = BEDROCK_SEMAPHORE.locked()
            if semaphore_locked:
                print(f"[SEMAPHORE] Queue is full, user will wait...")
                yield f"data: {json.dumps({'type': 'waiting', 'message': '다른 사용자의 요청을 처리 중입니다...'})}\n\n"

            async with BEDROCK_SEMAPHORE:
                yield f"data: {json.dumps({'type': 'processing_start'})}\n\n"

                # 파일 존재 여부 확인
                has_files = False
                if request.session_id:
                    has_files = chromadb.has_session_files(request.session_id)
                    print(f"[A2A_CHAT] File check: {has_files}")

                # MCP Tools 로드
                from app.main import get_mcp_adapter
                adapter = await get_mcp_adapter()
                tools = await adapter.get_tools()
                print(f"[A2A_CHAT] Tools loaded: {len(tools)}")

                # 메시지 히스토리 변환
                msg_history = None
                if request.message_history:
                    msg_history = [{"role": m.role, "content": m.content} for m in request.message_history]

                # 이미지 변환
                img_data = None
                if request.images:
                    img_data = [{"media_type": i.media_type, "base64_data": i.base64_data} for i in request.images]

                # A2A 스트리밍
                async for sse in stream_a2a_response(
                    message=request.message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    workspace_id=request.workspace_id,
                    workspace_context=None,
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
                            data = json.loads(sse.replace("data: ", "").strip())
                            collected_response = data.get("response", "")
                        except Exception:
                            pass
                        continue
                    yield sse

        except Exception as e:
            print(f"[A2A_CHAT] Error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        finally:
            # 로그 저장
            if request.session_id and collected_response:
                try:
                    await chat_log.save_chat_log(
                        user_id=request.user_id,
                        input_log=request.message,
                        output_log=collected_response,
                        session=request.session_id,
                        chat_mode=request.chat_mode,
                        category_text="a2a"
                    )
                except Exception as e:
                    print(f"[A2A_CHAT] Failed to save log: {e}")

    return StreamingResponse(generate(), media_type="text/event-stream")

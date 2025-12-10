"""채팅 API - 스트리밍 및 세션 관리"""
import json
import time
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.bedrock_service import BedrockService, get_bedrock_service
from app.services.chromadb_service import ChromaDBService, get_chromadb_service
from app.services.chat_log_service import ChatLogService, get_chat_log_service

router = APIRouter()


class ImageData(BaseModel):
    media_type: str
    base64_data: str


class MessageHistory(BaseModel):
    role: str  # "user" or "assistant"
    content: str | List  # 텍스트 문자열 또는 복합 콘텐츠


class ChatRequest(BaseModel):
    message: str
    chat_mode: str = "normal"  # normal or corp
    session_id: Optional[str] = None
    user_id: str = "anonymous"
    images: Optional[List[ImageData]] = None
    message_history: Optional[List[MessageHistory]] = None  # 대화 히스토리


@router.post("/v1/chat/message/stream")
async def chat_stream(
    request: ChatRequest,
    bedrock: BedrockService = Depends(get_bedrock_service),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    chat_log: ChatLogService = Depends(get_chat_log_service)
):
    """스트리밍 채팅 (SSE 형식, 파일 컨텍스트 포함)"""

    start_time = time.time()

    async def generate():
        # 응답 수집을 위한 변수
        collected_response = ""

        try:
            # 1. 파일 검색 (모드별 분기)
            search_start = time.time()
            file_results = []

            if request.chat_mode == "normal":
                # Normal 모드: 세션별 사용자 업로드 파일 검색
                if request.session_id:
                    file_results = await chromadb.search(
                        request.message,
                        request.user_id,
                        session_id=request.session_id,
                        limit=3
                    )
                    if file_results:
                        search_time = int((time.time() - search_start) * 1000)
                        yield f"data: {json.dumps({'type': 'timing', 'step': '업로드된 파일 검색 중', 'timing': {'user_file_search': search_time}})}\n\n"

            elif request.chat_mode == "corp":
                # Corp 모드: 사내 문서 검색 (user별 영구 저장 컬렉션)
                # TODO: 사내 문서용 별도 ChromaDB 컬렉션 또는 vector_service 사용
                file_results = await chromadb.search(
                    request.message,
                    request.user_id,
                    session_id=None,  # 영구 컬렉션 사용
                    limit=3
                )
                if file_results:
                    search_time = int((time.time() - search_start) * 1000)
                    yield f"data: {json.dumps({'type': 'timing', 'step': '사내 문서 검색 중', 'timing': {'corp_search': search_time}})}\n\n"

            # 2. 컨텍스트 구성
            context_start = time.time()
            context = ""

            if file_results:
                context = "\n\n".join([
                    f"[파일: {r['metadata'].get('filename', 'Unknown')}]\n{r['text']}"
                    for r in file_results
                ])

            # 이미지가 있으면 시스템 프롬프트에 추가
            system_prompt = ""
            if request.images:
                system_prompt = f"사용자가 {len(request.images)}개의 이미지를 첨부했습니다. 이미지 내용을 분석하여 답변해주세요."

            context_time = int((time.time() - context_start) * 1000)
            yield f"data: {json.dumps({'type': 'timing', 'step': '컨텍스트 준비 완료', 'timing': {'context_preparation': context_time}})}\n\n"

            # 3. 메시지 히스토리 준비 (Bedrock 형식으로 변환)
            message_history = []
            if request.message_history:
                for msg in request.message_history:
                    message_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })

            # 4. Bedrock 스트리밍 시작
            chunk_count = 0
            first_chunk_time = None

            yield f"data: {json.dumps({'type': 'timing', 'step': 'AI 응답 생성 중'})}\n\n"

            async for chunk in bedrock.stream_chat(
                request.message,
                system_prompt=system_prompt,
                context=context,
                images=request.images,
                message_history=message_history if message_history else None
            ):
                if first_chunk_time is None:
                    first_chunk_time = int((time.time() - start_time) * 1000)
                    yield f"data: {json.dumps({'type': 'timing', 'step': '첫 응답 수신', 'timing': {'first_chunk_latency': first_chunk_time}})}\n\n"

                chunk_count += 1
                # 응답 수집 (로그 저장용)
                collected_response += chunk
                # 콘텐츠 청크 전송 - 범용 SSE 형식
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            # 5. 완료 메시지
            total_time = int((time.time() - start_time) * 1000)
            yield f"data: {json.dumps({'type': 'timing', 'step': '완료', 'timing': {'chunk_count': chunk_count, 'total_response_time': total_time}})}\n\n"
            yield f"data: {json.dumps({'complete': True})}\n\n"

            # 6. 채팅 로그 저장 (스트리밍 완료 후)
            if request.session_id and collected_response:
                await chat_log.save_chat_log(
                    user_id=request.user_id,
                    input_log=request.message,
                    output_log=collected_response,
                    session=request.session_id,
                    chat_mode=request.chat_mode,
                    category_text="temp"
                )

        except Exception as e:
            error_msg = str(e)
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# 세션 관리 API (간단한 메모리 기반 - 실제로는 DB 사용)
# 지금은 빈 응답만 반환 (프론트엔드가 에러 없이 작동하도록)

@router.get("/v1/chat/users/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    chat_mode: Optional[str] = Query(None),
    limit: int = Query(20)
):
    """사용자 세션 목록 조회 (현재는 빈 목록 반환)"""
    return {
        "user_id": user_id,
        "sessions": [],
        "total_sessions": 0,
        "status": "ok"
    }


@router.get("/v1/chat/legacy/users/{user_id}/sessions")
async def get_user_sessions_legacy(
    user_id: str,
    chat_mode: Optional[str] = Query(None),
    limit: int = Query(20)
):
    """사용자 세션 목록 조회 - Legacy 엔드포인트 (현재는 빈 목록 반환)"""
    return {
        "user_id": user_id,
        "sessions": [],
        "total_sessions": 0,
        "status": "ok"
    }


@router.get("/v1/chat/legacy/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    user_id: str = Query(...)
):
    """세션 히스토리 조회 (현재는 빈 목록 반환)"""
    return {
        "session_id": session_id,
        "messages": [],
        "status": "ok"
    }


@router.delete("/v1/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Query(...),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """세션 삭제 (업로드된 파일 포함)"""

    # 세션의 업로드된 파일 삭제
    result = await chromadb.delete_session_files(session_id)

    return {
        "status": "ok",
        "message": "Session deleted successfully",
        "session_id": session_id,
        "files_deleted": result.get("success", False)
    }

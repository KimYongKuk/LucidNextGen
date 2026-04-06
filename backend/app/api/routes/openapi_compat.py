"""OpenAI-compatible Chat Completions API

사내 서비스들이 OpenAI SDK로 그대로 연결할 수 있도록
Bedrock 호출을 OpenAI 형식으로 래핑합니다.

사용법 (클라이언트):
    from openai import OpenAI
    client = OpenAI(base_url="http://서버:8000/v1", api_key="sk-lucid-common-2026")
    resp = client.chat.completions.create(
        model="claude-sonnet",
        messages=[{"role": "user", "content": "안녕하세요"}],
        stream=True,
    )
"""

import asyncio
import json
import time
import uuid
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies.api_key_auth import APIKeyInfo, verify_api_key
from app.services.openapi_bedrock_service import (
    MODEL_MAP,
    get_openapi_bedrock_service,
)
from app.services.token_usage_service import get_token_usage_service

router = APIRouter()


# ── Pydantic 모델 ──────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List] = ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=8192)
    system: Optional[str] = None  # OpenAI에는 없지만, 편의를 위해 지원


# ── 유틸 ────────────────────────────────────────────────────

def _gen_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:29]


def _map_stop_reason(reason: str) -> str:
    return "stop" if reason == "end_turn" else "length"


def _build_messages(messages: List[ChatMessage]) -> tuple[str, list]:
    """OpenAI messages → Bedrock messages + system prompt 분리"""
    system_parts = []
    bedrock_msgs = []

    for msg in messages:
        if msg.role == "system":
            system_parts.append(msg.content if isinstance(msg.content, str) else str(msg.content))
            continue

        if isinstance(msg.content, str):
            content = [{"type": "text", "text": msg.content}]
        elif isinstance(msg.content, list):
            content = msg.content
        else:
            content = [{"type": "text", "text": str(msg.content)}]

        bedrock_msgs.append({"role": msg.role, "content": content})

    system = "\n\n".join(system_parts) if system_parts else ""
    return system, bedrock_msgs


def _error_response(status: int, message: str, error_type: str = "invalid_request_error"):
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type}},
    )


# ── /v1/chat/completions ───────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    svc = get_openapi_bedrock_service()

    # 모델 검증
    if svc.resolve_model_id(request.model) is None:
        available = ", ".join(MODEL_MAP.keys())
        return _error_response(
            400,
            f"Unknown model: '{request.model}'. Available: {available}",
        )

    # 시스템 프롬프트 + 메시지 분리
    system_from_msgs, bedrock_msgs = _build_messages(request.messages)
    system = request.system or system_from_msgs

    if not bedrock_msgs:
        return _error_response(400, "At least one non-system message is required.")

    completion_id = _gen_id()
    created = int(time.time())

    # ── 스트리밍 ──
    if request.stream:
        async def event_generator():
            try:
                # 첫 chunk: role
                first = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"

                final_usage = None
                async for text_delta, finish_reason, usage in svc.invoke_stream(
                    messages=bedrock_msgs,
                    model=request.model,
                    system=system,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    if text_delta:
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "choices": [{"index": 0, "delta": {"content": text_delta}, "finish_reason": None}],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                    if finish_reason:
                        final_usage = usage
                        done_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                        }
                        if usage:
                            done_chunk["usage"] = {
                                "prompt_tokens": usage["input_tokens"],
                                "completion_tokens": usage["output_tokens"],
                                "total_tokens": usage["input_tokens"] + usage["output_tokens"],
                            }
                        yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"

                yield "data: [DONE]\n\n"

                # 토큰 사용량 로깅
                if final_usage:
                    asyncio.create_task(
                        get_token_usage_service().log(
                            caller=f"openapi:{api_key.name}",
                            model_id=svc.resolve_model_id(request.model),
                            input_tokens=final_usage["input_tokens"],
                            output_tokens=final_usage["output_tokens"],
                            api_key_name=api_key.name,
                        )
                    )

            except Exception as e:
                error_chunk = {
                    "error": {"message": str(e), "type": "server_error"},
                }
                yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Non-streaming ──
    try:
        result = await svc.invoke(
            messages=bedrock_msgs,
            model=request.model,
            system=system,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        return _error_response(500, f"Bedrock error: {str(e)}", "server_error")

    # 토큰 사용량 로깅
    asyncio.create_task(
        get_token_usage_service().log(
            caller=f"openapi:{api_key.name}",
            model_id=svc.resolve_model_id(request.model),
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            api_key_name=api_key.name,
        )
    )

    return JSONResponse(content={
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result["text"]},
                "finish_reason": _map_stop_reason(result["stop_reason"]),
            }
        ],
        "usage": {
            "prompt_tokens": result["input_tokens"],
            "completion_tokens": result["output_tokens"],
            "total_tokens": result["input_tokens"] + result["output_tokens"],
        },
    })


# ── /v1/models ──────────────────────────────────────────────

@router.get("/v1/models")
async def list_models(api_key: APIKeyInfo = Depends(verify_api_key)):
    """사용 가능한 모델 목록 (OpenAI 형식)"""
    models = []
    for name in MODEL_MAP:
        models.append({
            "id": name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "lucid-ai",
        })
    return {"object": "list", "data": models}

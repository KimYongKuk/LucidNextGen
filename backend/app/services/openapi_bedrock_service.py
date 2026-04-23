"""OpenAI-compatible API 전용 Bedrock 서비스 (별도 IAM 자격증명)

기존 BedrockService와 완전 분리 — AWS 쿼터를 공유하지 않도록
별도 IAM/계정의 자격증명을 사용합니다.
"""

import os
import json
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import boto3

from app.utils.bedrock_exceptions import is_throttling_error

# 모델 매핑: OpenAI 모델명 → Bedrock 모델 ID
MODEL_MAP: Dict[str, str] = {
    "claude-sonnet": os.getenv("OPENAPI_SONNET_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
    "claude-haiku": os.getenv("OPENAPI_HAIKU_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
}

# 모델별 max_tokens 상한
_MODEL_MAX_TOKENS: Dict[str, int] = {
    "claude-sonnet": 32768,
    "claude-haiku": 8192,
}

_MAX_RETRIES = 2
_RETRY_DELAY_SEC = 1.0


class OpenAPIBedrockService:
    """OpenAI-compatible API 전용 Bedrock 클라이언트"""

    def __init__(self):
        self._client = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=os.getenv("OPENAPI_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("OPENAPI_AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("OPENAPI_AWS_REGION", "us-east-1"),
        )

    def resolve_model_id(self, model: str) -> Optional[str]:
        """OpenAI 모델명 → Bedrock 모델 ID. 없으면 None."""
        return MODEL_MAP.get(model)

    def get_max_tokens(self, model: str, requested: int) -> int:
        """요청된 max_tokens를 모델 상한 이내로 제한"""
        cap = _MODEL_MAX_TOKENS.get(model, 4096)
        return min(requested, cap)

    @staticmethod
    def available_models() -> List[Dict]:
        """사용 가능한 모델 목록"""
        return [
            {"id": name, "bedrock_id": bid}
            for name, bid in MODEL_MAP.items()
        ]

    # ── Non-streaming ──────────────────────────────────────────

    async def invoke(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict:
        """
        Non-streaming 호출. 반환값:
        {
            "text": str,
            "input_tokens": int,
            "output_tokens": int,
            "stop_reason": str,   # "end_turn" | "max_tokens"
        }
        """
        model_id = self.resolve_model_id(model)
        max_tokens = self.get_max_tokens(model, max_tokens)

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            request_body["system"] = system

        last_exc = None
        for retry in range(_MAX_RETRIES):
            try:
                print(f"[OPENAPI_BEDROCK] invoke model={model} ({model_id})")
                response = self._client.invoke_model(
                    modelId=model_id,
                    body=json.dumps(request_body),
                )
                body = json.loads(response["body"].read())

                text = ""
                if body.get("content"):
                    text = body["content"][0].get("text", "")

                usage = body.get("usage", {})
                return {
                    "text": text,
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "stop_reason": body.get("stop_reason", "end_turn"),
                }

            except Exception as e:
                last_exc = e
                if is_throttling_error(e) and retry < _MAX_RETRIES - 1:
                    print(f"[OPENAPI_BEDROCK] Throttled, retry {retry + 1}/{_MAX_RETRIES}")
                    await asyncio.sleep(_RETRY_DELAY_SEC)
                else:
                    raise

        raise last_exc  # type: ignore

    # ── Streaming ──────────────────────────────────────────────

    async def invoke_stream(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[Tuple[str, Optional[str], Optional[Dict]], None]:
        """
        스트리밍 호출. 각 yield:
            (text_delta, finish_reason_or_None, usage_dict_or_None)

        - text_delta: 텍스트 조각 (빈 문자열이면 메타 이벤트)
        - finish_reason: 마지막 chunk에서만 "stop" 또는 "length"
        - usage: 마지막 chunk에서만 {"input_tokens": N, "output_tokens": N}
        """
        model_id = self.resolve_model_id(model)
        max_tokens = self.get_max_tokens(model, max_tokens)

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            request_body["system"] = system

        last_exc = None
        for retry in range(_MAX_RETRIES):
            try:
                print(f"[OPENAPI_BEDROCK] stream model={model} ({model_id})")
                response = self._client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(request_body),
                )

                input_tokens = 0
                output_tokens = 0

                for event in response["body"]:
                    chunk = json.loads(event["chunk"]["bytes"])
                    chunk_type = chunk.get("type", "")

                    if chunk_type == "message_start":
                        # input_tokens 는 여기서 옴
                        usage = chunk.get("message", {}).get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)

                    elif chunk_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            yield (text, None, None)

                    elif chunk_type == "message_delta":
                        # output_tokens + stop_reason
                        usage = chunk.get("usage", {})
                        output_tokens = usage.get("output_tokens", 0)
                        stop = chunk.get("delta", {}).get("stop_reason", "end_turn")
                        finish = "stop" if stop == "end_turn" else "length"
                        yield (
                            "",
                            finish,
                            {"input_tokens": input_tokens, "output_tokens": output_tokens},
                        )

                return  # 성공 — generator 종료

            except Exception as e:
                last_exc = e
                if is_throttling_error(e) and retry < _MAX_RETRIES - 1:
                    print(f"[OPENAPI_BEDROCK] Stream throttled, retry {retry + 1}/{_MAX_RETRIES}")
                    await asyncio.sleep(_RETRY_DELAY_SEC)
                else:
                    raise

        raise last_exc  # type: ignore


# 싱글톤
_service: Optional[OpenAPIBedrockService] = None


def get_openapi_bedrock_service() -> OpenAPIBedrockService:
    global _service
    if _service is None:
        _service = OpenAPIBedrockService()
    return _service

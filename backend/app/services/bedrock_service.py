"""AWS Bedrock 스트리밍 서비스 (자동 Fallback + 리전 폴백 지원)"""
import os
import json
import asyncio
import boto3
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple

from app.core.model_config import get_model_chain, RETRY_CONFIG, ModelConfig
from app.core.region_fallback import get_region_fallback_manager
from app.utils.bedrock_exceptions import is_throttling_error


class BedrockService:
    def __init__(self):
        self._region_mgr = get_region_fallback_manager()

        # Primary 리전 client
        self._primary_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=self._region_mgr.primary_region,
        )
        # Fallback 리전 client (lazy 생성)
        self._fallback_client = None

        # 모델 체인 (Primary -> Fallback)
        self.model_chain = get_model_chain()
        # 기본 모델 ID (하위 호환성)
        self.model_id = self.model_chain[0].model_id if self.model_chain else os.getenv(
            'BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        )
        # 테스트 모드: 첫 번째 모델 강제 실패
        self.force_fallback_test = os.getenv('FORCE_FALLBACK_TEST', 'false').lower() == 'true'

    @property
    def _fallback_client_lazy(self):
        """Fallback 리전 boto3 client (최초 사용 시 1회만 생성)"""
        if self._fallback_client is None:
            self._fallback_client = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=self._region_mgr.fallback_region,
            )
            print(f"[BEDROCK] Fallback client created for region: {self._region_mgr.fallback_region}")
        return self._fallback_client

    @property
    def client(self):
        """현재 리전 상태에 따라 적절한 client 반환"""
        if self._region_mgr.is_fallback_active:
            return self._fallback_client_lazy
        return self._primary_client

    def _get_model_id(self, original_model_id: str) -> str:
        """현재 리전에 맞는 model ID 반환"""
        return self._region_mgr.get_model_id(original_model_id)

    def _on_all_retries_exhausted(self):
        """모든 모델+리트라이 실패 시 리전 폴백 활성화"""
        if not self._region_mgr.is_fallback_active:
            self._region_mgr.activate_fallback()

    async def stream_chat(
        self,
        message: str,
        system_prompt: str = "",
        context: str = "",
        images: list = None,
        message_history: list = None
    ) -> AsyncGenerator[str, None]:
        """스트리밍 채팅 (이미지 및 멀티턴 대화 지원, 자동 Fallback)"""

        # 시스템 프롬프트 구성
        system = system_prompt or """당신은 친절한 AI 어시스턴트입니다.
답변 시 이모지를 사용하지 말고 전문적이고 세련된 톤으로 작성하세요.
답변의 마지막에는 반드시 핵심 내용을 요약하세요."""
        if context:
            system += f"\n\n다음 정보를 참고하세요:\n{context}"

        # 메시지 히스토리 처리
        messages = []

        if message_history:
            # 이전 대화 히스토리를 Bedrock 형식으로 변환
            for msg in message_history:
                role = msg.get("role")
                content = msg.get("content")

                # 텍스트만 있는 간단한 메시지
                if isinstance(content, str):
                    messages.append({
                        "role": role,
                        "content": [{"type": "text", "text": content}]
                    })
                # 이미 올바른 형식 (리스트)
                elif isinstance(content, list):
                    messages.append({
                        "role": role,
                        "content": content
                    })

        # 현재 메시지 콘텐츠 구성 (이미지 포함 가능)
        content = []

        # 이미지가 있으면 먼저 추가
        if images:
            for img in images:
                # Pydantic 모델이면 속성 접근, 딕셔너리면 .get() 사용
                if hasattr(img, 'media_type'):
                    # Pydantic ImageData 모델
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.media_type,
                            "data": img.base64_data
                        }
                    })
                else:
                    # 딕셔너리 형태
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/jpeg"),
                            "data": img.get("base64_data", "")
                        }
                    })

        # 텍스트 메시지 추가
        content.append({
            "type": "text",
            "text": message
        })

        # 현재 사용자 메시지 추가
        messages.append({"role": "user", "content": content})

        # === Fallback 로직으로 스트리밍 ===
        last_exception = None

        for model_idx, model_config in enumerate(self.model_chain):
            # 테스트 모드: 첫 번째 모델 강제 실패
            if self.force_fallback_test and model_idx == 0:
                print(f"[FALLBACK_TEST] Simulating throttling for {model_config.model_id}")
                last_exception = Exception("ThrottlingException (테스트 모드)")
                continue

            model_id = self._get_model_id(model_config.model_id)
            for retry in range(RETRY_CONFIG["max_retries"]):
                try:
                    # Bedrock 요청
                    request_body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": model_config.max_tokens,
                        "temperature": 0.7,
                        "system": system,
                        "messages": messages
                    }

                    region_tag = f"[{self._region_mgr.current_region}]" if self._region_mgr.is_fallback_active else ""
                    print(f"[BEDROCK] Streaming with model: {model_config.display_name} {region_tag}")
                    response = self.client.invoke_model_with_response_stream(
                        modelId=model_id,
                        body=json.dumps(request_body)
                    )

                    # 스트리밍 응답 처리
                    for event in response['body']:
                        chunk = json.loads(event['chunk']['bytes'])

                        if chunk['type'] == 'content_block_delta':
                            if 'delta' in chunk and 'text' in chunk['delta']:
                                yield chunk['delta']['text']

                    # 성공 시 함수 종료
                    return

                except Exception as e:
                    last_exception = e
                    if is_throttling_error(e):
                        if retry < RETRY_CONFIG["max_retries"] - 1:
                            delay = min(
                                RETRY_CONFIG["initial_delay_ms"] * (RETRY_CONFIG["backoff_multiplier"] ** retry),
                                RETRY_CONFIG["max_delay_ms"]
                            ) / 1000
                            print(f"[FALLBACK] Throttled, retry {retry + 1}/{RETRY_CONFIG['max_retries']} after {delay}s")
                            await asyncio.sleep(delay)
                        else:
                            print(f"[FALLBACK] {model_config.display_name} exhausted retries, trying next model...")
                            break  # 다음 모델로 이동
                    else:
                        raise  # 쓰로틀링이 아닌 에러는 즉시 raise

        # 모든 모델 실패 → 리전 폴백 활성화 후 재시도 안내
        self._on_all_retries_exhausted()
        raise Exception(f"모든 모델이 쓰로틀링으로 실패했습니다: {last_exception}")

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.3,
        caller: str = "",
        session_id: str = None,
        user_id: str = None,
    ) -> str:
        """단순 텍스트 생성 (non-streaming, 자동 Fallback) - title 생성 등에 사용"""
        last_exception = None

        for model_idx, model_config in enumerate(self.model_chain):
            # 테스트 모드: 첫 번째 모델 강제 실패
            if self.force_fallback_test and model_idx == 0:
                print(f"[FALLBACK_TEST] Simulating throttling for {model_config.model_id}")
                last_exception = Exception("ThrottlingException (테스트 모드)")
                continue

            model_id = self._get_model_id(model_config.model_id)
            for retry in range(RETRY_CONFIG["max_retries"]):
                try:
                    request_body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": min(max_tokens, model_config.max_tokens),
                        "temperature": temperature,
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"type": "text", "text": prompt}]
                            }
                        ]
                    }

                    print(f"[BEDROCK] generate_text with model: {model_config.display_name}")
                    response = self.client.invoke_model(
                        modelId=model_id,
                        body=json.dumps(request_body)
                    )

                    response_body = json.loads(response['body'].read())

                    # 토큰 사용량 로깅
                    if caller and "usage" in response_body:
                        usage = response_body["usage"]
                        try:
                            from app.services.token_usage_service import get_token_usage_service
                            asyncio.create_task(get_token_usage_service().log(
                                caller=caller,
                                model_id=model_id,
                                input_tokens=usage.get("input_tokens", 0),
                                output_tokens=usage.get("output_tokens", 0),
                                session_id=session_id,
                                user_id=user_id,
                            ))
                        except Exception as e:
                            print(f"[TOKEN_LOG] generate_text log error: {e}")

                    # Extract text from response
                    if 'content' in response_body and len(response_body['content']) > 0:
                        return response_body['content'][0]['text']

                    return ""

                except Exception as e:
                    last_exception = e
                    if is_throttling_error(e):
                        if retry < RETRY_CONFIG["max_retries"] - 1:
                            delay = min(
                                RETRY_CONFIG["initial_delay_ms"] * (RETRY_CONFIG["backoff_multiplier"] ** retry),
                                RETRY_CONFIG["max_delay_ms"]
                            ) / 1000
                            print(f"[FALLBACK] generate_text throttled, retry {retry + 1}/{RETRY_CONFIG['max_retries']} after {delay}s")
                            await asyncio.sleep(delay)
                        else:
                            print(f"[FALLBACK] {model_config.display_name} exhausted retries, trying next model...")
                            break
                    else:
                        raise

        self._on_all_retries_exhausted()
        raise Exception(f"모든 모델이 쓰로틀링으로 실패했습니다: {last_exception}")

    async def generate_text_haiku(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.3,
        caller: str = "",
        session_id: str = None,
        user_id: str = None,
    ) -> str:
        """
        Haiku 모델로 텍스트 생성 (메모리 요약 등 저비용 작업용)

        Fallback 없이 Haiku만 사용하여 비용 효율적인 텍스트 생성
        """
        haiku_model_id = os.getenv(
            "BEDROCK_FALLBACK_MODEL_ID",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        # 리전 폴백 시 model ID 변환
        effective_model_id = self._get_model_id(haiku_model_id)

        try:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            }

            print(f"[BEDROCK] generate_text_haiku: {effective_model_id}")
            response = self.client.invoke_model(
                modelId=effective_model_id,
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            # 토큰 사용량 로깅
            if caller and "usage" in response_body:
                usage = response_body["usage"]
                try:
                    from app.services.token_usage_service import get_token_usage_service
                    asyncio.create_task(get_token_usage_service().log(
                        caller=caller,
                        model_id=effective_model_id,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        session_id=session_id,
                        user_id=user_id,
                    ))
                except Exception as e:
                    print(f"[TOKEN_LOG] generate_text_haiku log error: {e}")

            if 'content' in response_body and len(response_body['content']) > 0:
                return response_body['content'][0]['text']

            return ""

        except Exception as e:
            if is_throttling_error(e):
                self._on_all_retries_exhausted()
            print(f"[BEDROCK] generate_text_haiku error: {e}")
            raise

    async def stream_text_haiku(
        self,
        prompt: str,
        max_tokens: int = 200,
        temperature: float = 0.2
    ):
        """
        Haiku 모델로 텍스트 스트리밍 생성 (SSE용 async generator)

        토큰 단위로 yield하여 실시간 스트리밍 지원
        """
        haiku_model_id = os.getenv(
            "BEDROCK_FALLBACK_MODEL_ID",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        effective_model_id = self._get_model_id(haiku_model_id)

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        }

        try:
            print(f"[BEDROCK] stream_text_haiku: {effective_model_id}")
            response = self.client.invoke_model_with_response_stream(
                modelId=effective_model_id,
                body=json.dumps(request_body)
            )

            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])
                if chunk["type"] == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta["text"]

        except Exception as e:
            if is_throttling_error(e):
                self._on_all_retries_exhausted()
            print(f"[BEDROCK] stream_text_haiku error: {e}")
            raise

    async def converse_with_tools(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Tool Calling을 지원하는 Bedrock Converse API (자동 Fallback)

        Args:
            messages: 대화 메시지 리스트 (Bedrock 형식)
            tools: Tool 정의 리스트 (Bedrock toolSpec 형식)
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 온도 (0.0-1.0)

        Returns:
            Bedrock Converse API 응답 (stopReason, output 등 포함)
        """
        last_exception = None

        for model_idx, model_config in enumerate(self.model_chain):
            # 테스트 모드: 첫 번째 모델 강제 실패
            if self.force_fallback_test and model_idx == 0:
                print(f"[FALLBACK_TEST] Simulating throttling for {model_config.model_id}")
                last_exception = Exception("ThrottlingException (테스트 모드)")
                continue

            model_id = self._get_model_id(model_config.model_id)
            for retry in range(RETRY_CONFIG["max_retries"]):
                try:
                    request = {
                        "modelId": model_id,
                        "messages": messages,
                        "inferenceConfig": {
                            "maxTokens": min(max_tokens, model_config.max_tokens),
                            "temperature": temperature
                        }
                    }

                    # 시스템 프롬프트 추가
                    if system_prompt:
                        request["system"] = [{"text": system_prompt}]

                    # Tools 추가
                    if tools:
                        request["toolConfig"] = {"tools": tools}

                    print(f"[BEDROCK] converse_with_tools with model: {model_config.display_name}")
                    response = self.client.converse(**request)
                    return response

                except Exception as e:
                    last_exception = e
                    if is_throttling_error(e):
                        if retry < RETRY_CONFIG["max_retries"] - 1:
                            delay = min(
                                RETRY_CONFIG["initial_delay_ms"] * (RETRY_CONFIG["backoff_multiplier"] ** retry),
                                RETRY_CONFIG["max_delay_ms"]
                            ) / 1000
                            print(f"[FALLBACK] converse_with_tools throttled, retry {retry + 1}/{RETRY_CONFIG['max_retries']} after {delay}s")
                            await asyncio.sleep(delay)
                        else:
                            print(f"[FALLBACK] {model_config.display_name} exhausted retries, trying next model...")
                            break
                    else:
                        raise

        self._on_all_retries_exhausted()
        raise Exception(f"모든 모델이 쓰로틀링으로 실패했습니다: {last_exception}")


# 싱글톤
_bedrock_service = None

def get_bedrock_service() -> BedrockService:
    global _bedrock_service
    if _bedrock_service is None:
        _bedrock_service = BedrockService()
    return _bedrock_service

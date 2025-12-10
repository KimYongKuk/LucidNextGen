"""AWS Bedrock 스트리밍 서비스"""
import os
import json
import boto3
from typing import AsyncGenerator


class BedrockService:
    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    #"anthropic.claude-3-5-sonnet-20240620-v1:0"
    #anthropic.claude-sonnet-4-5-20250929-v1:0
    #anthropic.claude-3-7-sonnet-20250219-v1:0
    async def stream_chat(
        self,
        message: str,
        system_prompt: str = "",
        context: str = "",
        images: list = None,
        message_history: list = None
    ) -> AsyncGenerator[str, None]:
        """스트리밍 채팅 (이미지 및 멀티턴 대화 지원)"""

        # 시스템 프롬프트 구성
        system = system_prompt or "당신은 친절한 AI 어시스턴트입니다."
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

        # Bedrock 요청
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.7,
            "system": system,
            "messages": messages
        }

        response = self.client.invoke_model_with_response_stream(
            modelId=self.model_id,
            body=json.dumps(request_body)
        )

        # 스트리밍 응답 처리
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'])

            if chunk['type'] == 'content_block_delta':
                if 'delta' in chunk and 'text' in chunk['delta']:
                    yield chunk['delta']['text']


# 싱글톤
_bedrock_service = None

def get_bedrock_service() -> BedrockService:
    global _bedrock_service
    if _bedrock_service is None:
        _bedrock_service = BedrockService()
    return _bedrock_service

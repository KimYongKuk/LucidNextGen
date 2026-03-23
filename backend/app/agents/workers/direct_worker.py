"""DirectResponseWorker - 도구 없이 직접 응답하는 Worker"""

from typing import List, Dict, Any, AsyncIterator, Optional
from langchain_core.messages import BaseMessage, SystemMessage

from app.core.model_config import get_worker_config
from .base_worker import BaseWorker, CachedChatBedrockConverse, BEDROCK_CONFIG


class DirectResponseWorker(BaseWorker):
    """
    직접 응답 Worker (Sonnet)

    담당 도구: 없음
    용도: 일반 대화, 코딩 도움, 번역, 계산 등 도구가 필요 없는 작업

    Sonnet 사용 이유: 코딩, 번역, 복잡한 대화 등 고품질 응답 필요
    """

    @property
    def name(self) -> str:
        return "DirectResponseWorker"

    @property
    def tool_names(self) -> List[str]:
        return []  # 전용 도구 없음

    @property
    def shared_tool_names(self) -> List[str]:
        """공유 도구: 차트(Recharts), PDF, DOCX 생성"""
        return [
            "create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
            "create_document_pdf", "create_table_spec_pdf", "create_document_docx",
        ]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (고품질 응답을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        return """You are 루시드AI(LucidAI), a helpful AI assistant.

You handle general conversations, coding help, translations, and other tasks
that don't require external tools.

GUIDELINES:
1. Be helpful and friendly
2. For coding questions, provide clear explanations and examples
3. For translations, maintain the original meaning
4. For math/calculations, show your work
5. Do not use emojis in responses unless explicitly requested by user
6. When users ask about your capabilities or what you can do, refer to the 루시드AI feature list in the system context

RESPONSE FORMAT:
- Answer in Korean (unless asked otherwise)
- Use markdown formatting
- For code, use appropriate code blocks
- End with "---" and "**요약:**" section"""

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: List,
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        공유 도구가 있으면 ReAct 루프, 없으면 직접 LLM 스트리밍
        """
        # 공유 도구 사용 가능 여부 확인
        available_tools = self.filter_tools(all_tools)
        if available_tools:
            # 공유 도구 사용 가능 → BaseWorker의 ReAct 루프 사용
            async for event in super().stream_response(
                messages, context, all_tools, memory_context, user_memory_context
            ):
                yield event
            return
        import time

        # Phase 0: 대화 히스토리가 길면 Haiku로 사전 요약
        summarize_start = time.time()
        processed_messages = await self._summarize_history_if_needed(messages)

        if len(processed_messages) < len(messages):
            summarize_time = int((time.time() - summarize_start) * 1000)
            print(f"[{self.name}] [TIMING] Haiku summarization: {summarize_time}ms")
            print(f"[{self.name}] Messages reduced: {len(messages)} -> {len(processed_messages)}")

            yield {
                "event": "summarization_complete",
                "original_count": len(messages),
                "summarized_count": len(processed_messages),
                "timing_ms": summarize_time,
            }

            messages = processed_messages

        setup_start = time.time()

        config = self.get_model_config()
        llm = CachedChatBedrockConverse(
            model=config.model_id,
            temperature=0.7,
            max_tokens=config.max_tokens,
            disable_streaming=False,
            config=BEDROCK_CONFIG,
        )

        # 시스템 프롬프트 적용 (메모리 컨텍스트 포함)
        system_prompt = self.build_system_prompt(context, memory_context, user_memory_context)
        full_messages = [SystemMessage(content=system_prompt)] + messages

        if memory_context:
            print(f"[{self.name}] Workspace memory injected: {len(memory_context.get('summary', ''))} chars")
        if user_memory_context:
            print(f"[{self.name}] User memory injected: {len(user_memory_context.get('key_facts', []))} facts")

        setup_time = int((time.time() - setup_start) * 1000)
        print(f"[{self.name}] [TIMING] Setup: {setup_time}ms")
        print(f"[{self.name}] Direct streaming with {config.display_name}")

        # LLM 직접 스트리밍
        first_token = False
        stream_start = time.time()

        async for chunk in llm.astream(full_messages):
            if not first_token:
                first_token_time = int((time.time() - stream_start) * 1000)
                print(f"[{self.name}] [TIMING] First LLM token: {first_token_time}ms")
                first_token = True

            # astream_events 형식으로 변환하여 일관성 유지
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": chunk},
            }

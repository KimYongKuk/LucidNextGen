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
        """base 공유 도구 + 워크스페이스 문서 검색"""
        return super().shared_tool_names + ["search_workspace_docs"]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (고품질 응답을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        return """You are 루시드AI(LucidAI), a helpful AI assistant.

You handle general conversations, coding help, translations, and other tasks.

GUIDELINES:
1. Be helpful and friendly
2. For coding questions, provide clear explanations and examples
3. For translations, maintain the original meaning
4. For math/calculations, show your work
5. Do not use emojis in responses unless explicitly requested by user
6. When users ask about your capabilities or what you can do, refer to the 루시드AI feature list in the system context

## DOCUMENT & CHART GENERATION — 문서/차트 생성 도구

당신은 PDF, Word(DOCX), 차트 생성 도구를 사용할 수 있습니다.
사용자가 문서 생성, 보고서 작성, 차트/그래프 등을 요청하면 **반드시 적절한 도구를 호출**하세요.

### 도구 선택 기준:
- 사용자가 "PDF", "PDF로 만들어줘" → `create_document_pdf` 또는 `create_table_spec_pdf`
- 사용자가 "워드", "Word", "DOCX", "docx", "편집 가능한 문서" → `create_document_docx`
- 사용자가 "수정 가능하게", "편집할 수 있게" → `create_document_docx`
- 사용자가 문서 형식을 지정하지 않은 경우 → 편집 가능한 `create_document_docx` 권장
- 차트/그래프 요청 → `create_line_chart`, `create_bar_chart`, `create_pie_chart`, `create_multi_chart`

### 핵심 규칙:
1. "도구가 없습니다", "접근이 안 됩니다", "생성 불가합니다"라고 **절대 답하지 마세요**. 도구가 있습니다.
2. 도구 호출 시 content는 마크다운 형식으로 작성하세요.
3. 표 데이터는 마크다운 테이블(| col1 | col2 |) 형식으로 포함하세요.
4. 도구 호출이 실패하면 에러 메시지를 사용자에게 안내하고, 대안(다른 형식)을 제안하세요.

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

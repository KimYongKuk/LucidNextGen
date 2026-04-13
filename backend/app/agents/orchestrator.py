"""Orchestrator Agent - A2A 아키텍처의 핵심 라우터"""

import json
import re
import time
from typing import Dict, Any, AsyncIterator, List, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.agents.state import Intent, INTENT_TO_WORKER, RequestContext
from app.agents.intent_classifier import get_intent_classifier
from app.agents.workers import get_worker

# Fallback 대상 인텐트 (검색형 워커만 — 결과 없음이 의미 있는 경우)
FALLBACK_ELIGIBLE_INTENTS = {
    Intent.APPROVAL, Intent.BOARD, Intent.CORP_RAG,
    Intent.IT_SUPPORT, Intent.ACCT_SUPPORT, Intent.WEB_SEARCH,
}

# HANDOFF 마커 패턴 (워커가 다른 워커의 데이터를 요청할 때)
HANDOFF_PATTERN = re.compile(r'<!--HANDOFF:(\w+)-->')


class Orchestrator:
    """
    A2A Orchestrator Agent

    역할:
    1. Intent Classification (Haiku) - 사용자 의도 분류
    2. Worker Dispatch - 적절한 Worker 선택 및 실행
    3. Event Passthrough - Worker의 스트리밍 이벤트를 그대로 전달
    """

    def __init__(self):
        self.classifier = get_intent_classifier()

    async def stream(
        self,
        message: str,
        context: RequestContext,
        all_tools: List[BaseTool],
        message_history: Optional[List[Dict]] = None,
        images: Optional[List[Dict]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Orchestrator 메인 스트리밍 함수

        Args:
            message: 사용자 메시지
            context: 요청 컨텍스트 (session_id, workspace_uuid 등)
            all_tools: MCP에서 로드된 전체 도구 리스트
            message_history: 이전 대화 히스토리
            images: 이미지 데이터

        Yields:
            SSE 이벤트 딕셔너리
        """
        start_time = time.time()

        # ============================================================
        # Phase 0a: Load Global User Memory (모든 세션)
        # ============================================================
        user_memory_context = None
        user_id = context.get("user_id", "anonymous")
        print(f"[ORCHESTRATOR] Phase 0a: user_id={user_id}")
        if user_id != "anonymous":
            try:
                from app.services.memory_service import get_user_memory_service, USER_MEMORY_ENABLED
                print(f"[ORCHESTRATOR] USER_MEMORY_ENABLED={USER_MEMORY_ENABLED}")
                if USER_MEMORY_ENABLED:
                    user_memory_service = get_user_memory_service()
                    user_memory_context = await user_memory_service.get_user_memory(user_id)
                    print(f"[ORCHESTRATOR] get_user_memory result: {type(user_memory_context)}, has_facts={bool(user_memory_context and user_memory_context.get('key_facts'))}")
                    if user_memory_context and user_memory_context.get("key_facts"):
                        print(f"[ORCHESTRATOR] Loaded user memory: {len(user_memory_context['key_facts'])} facts")
                    else:
                        print(f"[ORCHESTRATOR] No user memory facts found for {user_id}")
            except Exception as e:
                import traceback
                print(f"[ORCHESTRATOR] User memory load error (non-fatal): {e}")
                traceback.print_exc()

        # ============================================================
        # Phase 0b: Load Workspace Memory (if applicable)
        # ============================================================
        memory_context = None
        workspace_id = context.get("workspace_id")
        if workspace_id:
            try:
                from app.services.memory_service import get_memory_service
                memory_service = get_memory_service()
                memory_context = await memory_service.get_memory_context(
                    workspace_id=workspace_id,
                    user_id=context.get("user_id", "anonymous")
                )
                if memory_context and memory_context.get("summary"):
                    print(f"[ORCHESTRATOR] Loaded workspace memory: {len(memory_context.get('summary', ''))} chars")
            except Exception as e:
                print(f"[ORCHESTRATOR] Memory load error (non-fatal): {e}")

        # ============================================================
        # Phase 1: Intent Classification (Haiku, ~0.3-0.5초)
        # ============================================================
        classify_start = time.time()
        print(f"\n[ORCHESTRATOR] ===== A2A Pipeline Start =====")
        print(f"[ORCHESTRATOR] Message: {message[:50]}...")

        previous_intent = context.get("previous_intent")
        primary_intent, fallback_intent = await self.classifier.classify(message, context, message_history, previous_intent)
        intent = primary_intent

        # outline_embed 모드: 기본적으로 OUTLINE, 단순 인사/잡담만 DIRECT
        chat_mode = context.get("chat_mode", "normal")
        if chat_mode == "outline_embed":
            if intent != Intent.DIRECT:
                # 모든 비-DIRECT 인텐트 → OUTLINE
                if intent != Intent.OUTLINE:
                    print(f"[ORCHESTRATOR] outline_embed mode: {intent.value} -> OUTLINE")
                intent = Intent.OUTLINE
                fallback_intent = None
            else:
                # DIRECT인 경우: 질문/검색성이면 OUTLINE으로 전환
                import re
                search_like = re.search(
                    r'(찾아|검색|알려|보여|조회|어디|뭐가|있어|문서|자료|가이드|매뉴얼|방법|하는\s?법)',
                    message
                )
                if search_like:
                    print(f"[ORCHESTRATOR] outline_embed mode: direct -> OUTLINE (search-like query)")
                    intent = Intent.OUTLINE
                    fallback_intent = None

        # groupware_embed 모드: 그룹웨어 관련 인텐트만 허용
        elif chat_mode == "groupware_embed":
            GROUPWARE_ALLOWED = {
                Intent.MAIL, Intent.APPROVAL, Intent.BOARD,
                Intent.CALENDAR, Intent.RESERVATION,
                Intent.IT_SUPPORT, Intent.ACCT_SUPPORT,
                Intent.WEB_SEARCH, Intent.DIRECT,
            }
            if intent not in GROUPWARE_ALLOWED:
                print(f"[ORCHESTRATOR] groupware_embed mode: {intent.value} -> DIRECT")
                intent = Intent.DIRECT
                fallback_intent = None

        worker_name = INTENT_TO_WORKER.get(intent, "DirectResponseWorker")

        classify_time = int((time.time() - classify_start) * 1000)
        print(f"[ORCHESTRATOR] Intent: {intent.value} -> Worker: {worker_name}")
        if fallback_intent:
            print(f"[ORCHESTRATOR] Fallback intent: {fallback_intent.value}")
        print(f"[ORCHESTRATOR] Classification time: {classify_time}ms")

        # Intent 분류 이벤트 전송
        yield {
            "type": "intent_classified",
            "intent": intent.value,
            "worker": worker_name,
            "timing_ms": classify_time,
        }

        # ============================================================
        # Phase 1.5: CLARIFY 처리 — 모호한 요청 시 사용자에게 확인
        # ============================================================
        if intent == Intent.CLARIFY:
            context = dict(context)  # 원본 수정 방지
            context["clarify_mode"] = True
            print(f"[ORCHESTRATOR] CLARIFY intent → injecting clarify_mode into context")

        # ============================================================
        # Phase 1.8: Workspace-first routing
        # 워크스페이스에 파일이 있고, 전문 워커로 분류되었으면
        # → user_files를 1순위로 실행, NO_RESULTS 시 원래 워커로 폴백
        # ============================================================
        workspace_has_files = context.get("workspace_has_files", False)
        workspace_original_intent = None  # 원래 분류된 전문 인텐트 (폴백용)
        workspace_original_worker = None

        # user_files/direct가 아닌 전문 인텐트 + 워크스페이스에 파일 있음
        # → user_files를 먼저 실행하도록 교체
        _WS_FIRST_ELIGIBLE = {
            Intent.CORP_RAG, Intent.IT_SUPPORT, Intent.ACCT_SUPPORT,
            Intent.WEB_SEARCH, Intent.BOARD,
        }
        if workspace_has_files and intent in _WS_FIRST_ELIGIBLE:
            workspace_original_intent = intent
            workspace_original_worker = worker_name
            intent = Intent.USER_FILES
            worker_name = INTENT_TO_WORKER[Intent.USER_FILES]
            print(f"[ORCHESTRATOR] Workspace-first: {workspace_original_intent.value} → user_files (try workspace docs first)")

            yield {
                "type": "intent_classified",
                "intent": "user_files",
                "worker": worker_name,
                "timing_ms": classify_time,
                "workspace_first": True,
            }

        # ============================================================
        # Phase 2: Worker Dispatch (+ 도구 가용성 체크)
        # ============================================================
        worker_dispatch_start = time.time()
        worker = get_worker(worker_name)

        # 도구 기반 Worker의 도구가 0개면 DirectWorker로 폴백
        # (예: tavily-mcp 로드 실패 시 WebSearchWorker 도구 없음)
        if worker.tool_names:
            available = worker.filter_tools(all_tools)
            if not available:
                original_worker = worker_name
                worker_name = "DirectResponseWorker"
                worker = get_worker(worker_name)
                print(f"[ORCHESTRATOR] Tool fallback: {original_worker} → {worker_name} (no tools available)")
                yield {
                    "type": "intent_classified",
                    "intent": "direct",
                    "worker": worker_name,
                    "timing_ms": classify_time,
                    "tool_fallback": True,
                }

        worker_dispatch_time = int((time.time() - worker_dispatch_start) * 1000)
        print(f"[ORCHESTRATOR] [TIMING] Worker dispatch: {worker_dispatch_time}ms")
        print(f"[ORCHESTRATOR] Dispatching to {worker_name}")

        # ============================================================
        # Phase 3: Build Messages
        # ============================================================
        build_msg_start = time.time()
        messages = self._build_messages(message, message_history, images)
        build_msg_time = int((time.time() - build_msg_start) * 1000)
        print(f"[ORCHESTRATOR] [TIMING] Build messages: {build_msg_time}ms")

        # ============================================================
        # Phase 4: Worker Streaming (Event Passthrough + 텍스트 수집)
        # ============================================================
        worker_start = time.time()
        print(f"[ORCHESTRATOR] [TIMING] Entering worker.stream_response()")

        first_event = True
        collected_text = ""
        async for event in worker.stream_response(messages, context, all_tools, memory_context, user_memory_context):
            if first_event:
                first_event_time = int((time.time() - worker_start) * 1000)
                print(f"[ORCHESTRATOR] [TIMING] First event from worker: {first_event_time}ms")
                first_event = False

            # 텍스트 수집 (NO_RESULTS 마커 감지용)
            collected_text += self._extract_text(event)

            # Worker 이벤트를 그대로 전달 (기존 chat.py 이벤트 처리와 호환)
            yield event

        worker_time = int((time.time() - worker_start) * 1000)
        print(f"[ORCHESTRATOR] Worker execution time: {worker_time}ms")

        # ============================================================
        # Phase 4.5: Workspace-first fallback
        # user_files에서 NO_RESULTS → 원래 분류된 전문 워커로 폴백
        # ============================================================
        workspace_fallback_time = 0
        if (workspace_original_intent is not None
                and "<!--NO_RESULTS-->" in collected_text):

            print(f"[ORCHESTRATOR] Workspace-first fallback: user_files → {workspace_original_worker} (NO_RESULTS from workspace docs)")

            from langchain_core.messages import AIMessageChunk
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="\n\n---\n\n**워크스페이스 문서에서 관련 내용을 찾지 못해, 다른 곳에서 찾아보겠습니다...**\n\n")},
            }

            yield {
                "type": "intent_classified",
                "intent": workspace_original_intent.value,
                "worker": workspace_original_worker,
                "timing_ms": 0,
                "workspace_fallback": True,
            }

            # 원래 전문 워커로 폴백 실행
            ws_fb_start = time.time()
            ws_fb_worker = get_worker(workspace_original_worker)
            collected_text = ""  # NO_RESULTS 체크 리셋 (Phase 6 fallback과 연계)
            async for event in ws_fb_worker.stream_response(
                messages, context, all_tools, memory_context, user_memory_context
            ):
                collected_text += self._extract_text(event)
                yield event

            workspace_fallback_time = int((time.time() - ws_fb_start) * 1000)
            print(f"[ORCHESTRATOR] Workspace fallback worker time: {workspace_fallback_time}ms")

            # workspace 폴백 후에는 원래 intent로 복원 (Phase 6 fallback 판단용)
            intent = workspace_original_intent
            worker_name = workspace_original_worker

        # ============================================================
        # Phase 5: HANDOFF Check — 다른 워커의 데이터가 필요한 경우
        # ============================================================
        handoff_match = HANDOFF_PATTERN.search(collected_text)

        if handoff_match and not context.get("is_handoff_target"):
            handoff_intent_str = handoff_match.group(1)
            handoff_intent = None
            for i in Intent:
                if i.value == handoff_intent_str:
                    handoff_intent = i
                    break

            if handoff_intent and handoff_intent != intent:
                handoff_worker_name = INTENT_TO_WORKER.get(handoff_intent)

                if handoff_worker_name:
                    print(f"[ORCHESTRATOR] HANDOFF: {worker_name} → {handoff_worker_name}")

                    # 상태 이벤트
                    yield {
                        "type": "intent_classified",
                        "intent": handoff_intent.value,
                        "worker": handoff_worker_name,
                        "timing_ms": 0,
                        "is_handoff": True,
                    }

                    # 선행 워커 실행 (is_handoff_target=True → 재귀 방지)
                    ho_context = dict(context)
                    ho_context["is_handoff_target"] = True

                    prerequisite_worker = get_worker(handoff_worker_name)
                    prerequisite_text = ""
                    async for event in prerequisite_worker.stream_response(
                        messages, ho_context, all_tools, memory_context, user_memory_context
                    ):
                        yield event
                        prerequisite_text += self._extract_text(event)

                    # 구분선
                    from langchain_core.messages import AIMessageChunk
                    yield {
                        "event": "on_chat_model_stream",
                        "data": {"chunk": AIMessageChunk(content="\n\n---\n\n")},
                    }

                    # 원래 워커 재실행 (선행 결과를 히스토리에 주입)
                    enriched_messages = list(messages)
                    enriched_messages.insert(-1, AIMessage(
                        content=f"[이전 단계에서 가져온 데이터]\n{prerequisite_text}"
                    ))

                    rerun_worker = get_worker(worker_name)
                    collected_text = ""  # NO_RESULTS 체크용 리셋
                    async for event in rerun_worker.stream_response(
                        enriched_messages, context, all_tools, memory_context, user_memory_context
                    ):
                        collected_text += self._extract_text(event)
                        yield event

        # ============================================================
        # Phase 6: Fallback Check — NO_RESULTS 감지 시 2순위 워커 자동 실행
        # ============================================================
        fallback_worker_time = 0
        if (intent in FALLBACK_ELIGIBLE_INTENTS
                and "<!--NO_RESULTS-->" in collected_text
                and fallback_intent is not None
                and fallback_intent != intent):

            fallback_worker_name = INTENT_TO_WORKER.get(fallback_intent, "DirectResponseWorker")
            print(f"[ORCHESTRATOR] Fallback: {worker_name} → {fallback_worker_name} (NO_RESULTS detected)")

            # 구분선 이벤트 (on_chat_model_stream 형식 → a2a_streaming 호환)
            from langchain_core.messages import AIMessageChunk
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content="\n\n---\n\n**다른 곳에서도 찾아보겠습니다...**\n\n")},
            }

            # Fallback intent 이벤트
            yield {
                "type": "intent_classified",
                "intent": fallback_intent.value,
                "worker": fallback_worker_name,
                "timing_ms": 0,
                "is_fallback": True,
            }

            # Fallback context: is_final_attempt + already_searched
            fb_context = dict(context)
            fb_context["is_final_attempt"] = True
            fb_context["already_searched"] = worker_name

            # Fallback 워커 실행
            fallback_start = time.time()
            fb_worker = get_worker(fallback_worker_name)
            async for event in fb_worker.stream_response(
                messages, fb_context, all_tools, memory_context, user_memory_context
            ):
                yield event

            fallback_worker_time = int((time.time() - fallback_start) * 1000)
            print(f"[ORCHESTRATOR] Fallback worker execution time: {fallback_worker_time}ms")

        total_time = int((time.time() - start_time) * 1000)
        print(f"[ORCHESTRATOR] Total pipeline time: {total_time}ms")
        print(f"[ORCHESTRATOR] ===== A2A Pipeline End =====\n")

        # 타이밍 이벤트 전송
        timing_event = {
            "type": "orchestrator_timing",
            "classify_ms": classify_time,
            "worker_ms": worker_time,
            "fallback_worker_ms": fallback_worker_time,
            "total_ms": total_time,
        }
        if workspace_fallback_time:
            timing_event["workspace_fallback_ms"] = workspace_fallback_time
        yield timing_event

    @staticmethod
    def _extract_text(event: Dict[str, Any]) -> str:
        """on_chat_model_stream 이벤트에서 텍스트 추출 (NO_RESULTS/HANDOFF 마커 감지용)"""
        if event.get("event") == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Bedrock Converse API: [{"type": "text", "text": "..."}] 형태
                    text = ""
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text += item["text"]
                        elif isinstance(item, str):
                            text += item
                    return text
        return ""

    def _build_messages(
        self,
        current_message: str,
        message_history: Optional[List[Dict]],
        images: Optional[List[Dict]],
    ) -> List[BaseMessage]:
        """메시지 히스토리 + 현재 메시지를 LangChain 형식으로 결합"""
        messages = []

        # 이전 대화 히스토리 추가
        if message_history:
            for msg in message_history:
                role = msg.get("role")
                content = msg.get("content")

                # 멀티모달 content (이미지 포함) → 이미지 압축 적용
                if role == "user" and isinstance(content, list):
                    from app.api.routes.chat import _compress_image_if_needed
                    compressed_content = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "image":
                            source = block.get("source", {})
                            data = source.get("data", "")
                            media_type = source.get("media_type", "image/jpeg")
                            if data:
                                data, media_type = _compress_image_if_needed(data, media_type)
                            compressed_content.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": data}
                            })
                        else:
                            compressed_content.append(block)
                    messages.append(HumanMessage(content=compressed_content))
                elif role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        # 현재 메시지 (이미지 포함 가능)
        if images:
            image_contents = []
            for img in images:
                if hasattr(img, "media_type"):
                    media_type = img.media_type
                    data = img.base64_data
                else:
                    media_type = img.get("media_type", "image/jpeg")
                    data = img.get("base64_data", "")

                if data:
                    image_contents.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        }
                    })

            messages.append(HumanMessage(content=[
                *image_contents,
                {"type": "text", "text": current_message}
            ]))
        else:
            messages.append(HumanMessage(content=current_message))

        return messages


# ============================================================================
# Singleton
# ============================================================================

_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Orchestrator 싱글톤 반환"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator

"""Orchestrator Agent - A2A 아키텍처의 핵심 라우터"""

import json
import time
from typing import Dict, Any, AsyncIterator, List, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.agents.state import Intent, INTENT_TO_WORKER, RequestContext
from app.agents.intent_classifier import get_intent_classifier
from app.agents.workers import get_worker


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
        # Phase 1: Intent Classification (Haiku, ~0.3-0.5초)
        # ============================================================
        classify_start = time.time()
        print(f"\n[ORCHESTRATOR] ===== A2A Pipeline Start =====")
        print(f"[ORCHESTRATOR] Message: {message[:50]}...")

        intent = await self.classifier.classify(message, context)
        worker_name = INTENT_TO_WORKER.get(intent, "DirectResponseWorker")

        classify_time = int((time.time() - classify_start) * 1000)
        print(f"[ORCHESTRATOR] Intent: {intent.value} -> Worker: {worker_name}")
        print(f"[ORCHESTRATOR] Classification time: {classify_time}ms")

        # Intent 분류 이벤트 전송
        yield {
            "type": "intent_classified",
            "intent": intent.value,
            "worker": worker_name,
            "timing_ms": classify_time,
        }

        # ============================================================
        # Phase 2: Worker Dispatch
        # ============================================================
        worker_dispatch_start = time.time()
        worker = get_worker(worker_name)
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
        # Phase 4: Worker Streaming (Event Passthrough)
        # ============================================================
        worker_start = time.time()
        print(f"[ORCHESTRATOR] [TIMING] Entering worker.stream_response()")

        first_event = True
        async for event in worker.stream_response(messages, context, all_tools):
            if first_event:
                first_event_time = int((time.time() - worker_start) * 1000)
                print(f"[ORCHESTRATOR] [TIMING] First event from worker: {first_event_time}ms")
                first_event = False

            # Worker 이벤트를 그대로 전달 (기존 chat.py 이벤트 처리와 호환)
            yield event

        worker_time = int((time.time() - worker_start) * 1000)
        total_time = int((time.time() - start_time) * 1000)

        print(f"[ORCHESTRATOR] Worker execution time: {worker_time}ms")
        print(f"[ORCHESTRATOR] Total pipeline time: {total_time}ms")
        print(f"[ORCHESTRATOR] ===== A2A Pipeline End =====\n")

        # 타이밍 이벤트 전송
        yield {
            "type": "orchestrator_timing",
            "classify_ms": classify_time,
            "worker_ms": worker_time,
            "total_ms": total_time,
        }

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

                if role == "user":
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

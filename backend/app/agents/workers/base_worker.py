"""Worker Agent 기본 클래스"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, AsyncIterator, Optional
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.core.model_config import get_worker_config, ModelConfig


def _get_current_date_info() -> str:
    """현재 날짜 정보를 한국어로 반환"""
    now = datetime.now()
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    weekday_kr = weekdays[now.weekday()]
    return f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"


class BaseWorker(ABC):
    """
    Worker Agent 추상 기본 클래스

    각 Worker는 특정 도메인의 도구를 담당하며,
    MCP에서 로드된 도구 중 필요한 것만 필터링하여 사용
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Worker 이름"""
        pass

    @property
    @abstractmethod
    def tool_names(self) -> List[str]:
        """이 Worker가 사용할 도구 이름 목록"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Worker 전용 시스템 프롬프트"""
        pass

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 여부 (기본: False = Haiku)"""
        return False

    def get_model_config(self) -> ModelConfig:
        """모델 설정 반환"""
        return get_worker_config(use_sonnet=self.use_sonnet)

    def filter_tools(self, all_tools: List[BaseTool]) -> List[BaseTool]:
        """MCP 도구 중 이 Worker가 사용할 도구만 필터링"""
        if not self.tool_names:
            return []
        return [t for t in all_tools if t.name in self.tool_names]

    def build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        컨텍스트를 반영한 시스템 프롬프트 생성

        Args:
            context: 세션, 워크스페이스 등 컨텍스트 정보
        """
        prompt = self.system_prompt

        # 날짜 정보 추가
        current_date = _get_current_date_info()
        prompt = f"Today is {current_date}.\n\n{prompt}"

        # 세션 ID 주입
        session_id = context.get("session_id")
        if session_id:
            prompt = prompt.replace("{session_id}", session_id)

        # 워크스페이스 UUID 주입
        workspace_uuid = context.get("workspace_uuid")
        if workspace_uuid:
            prompt = prompt.replace("{workspace_uuid}", workspace_uuid)

        # 워크스페이스 instructions 주입
        workspace_instructions = context.get("workspace_instructions")
        if workspace_instructions:
            prompt = f"{workspace_instructions}\n\n{prompt}"

        return prompt

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: List[BaseTool],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        스트리밍 응답 생성

        Args:
            messages: 대화 메시지 리스트
            context: 요청 컨텍스트
            all_tools: MCP에서 로드된 전체 도구 리스트

        Yields:
            astream_events 이벤트 딕셔너리
        """
        import time
        worker_internal_start = time.time()

        # 모델 생성
        model_start = time.time()
        config = self.get_model_config()
        llm = ChatBedrockConverse(
            model=config.model_id,
            temperature=0.7,
            max_tokens=config.max_tokens,
            disable_streaming=False,
        )
        model_time = int((time.time() - model_start) * 1000)
        print(f"[{self.name}] [TIMING] Model creation: {model_time}ms")

        # 도구 필터링
        filter_start = time.time()
        filtered_tools = self.filter_tools(all_tools)
        filter_time = int((time.time() - filter_start) * 1000)
        print(f"[{self.name}] Using tools: {[t.name for t in filtered_tools]}")
        print(f"[{self.name}] [TIMING] Tool filtering: {filter_time}ms")

        # 시스템 프롬프트 생성
        prompt_start = time.time()
        system_prompt = self.build_system_prompt(context)
        prompt_time = int((time.time() - prompt_start) * 1000)
        print(f"[{self.name}] [TIMING] System prompt build: {prompt_time}ms")

        # Agent 생성
        agent_start = time.time()
        if filtered_tools:
            agent = create_react_agent(llm, filtered_tools, state_modifier=system_prompt)
        else:
            # 도구 없는 경우 (DirectResponseWorker)
            agent = create_react_agent(llm, [], state_modifier=system_prompt)
        agent_time = int((time.time() - agent_start) * 1000)
        print(f"[{self.name}] [TIMING] Agent creation: {agent_time}ms")

        # 스트리밍 실행
        total_setup_time = int((time.time() - worker_internal_start) * 1000)
        print(f"[{self.name}] [TIMING] Total setup before stream: {total_setup_time}ms")
        print(f"[{self.name}] Starting stream with {config.display_name}")

        # 타이밍 플래그
        llm_started = False
        first_token = False
        tool_started = False
        stream_start = time.time()

        async for event in agent.astream_events({"messages": messages}, version="v2"):
            event_kind = event.get("event", "")
            elapsed = int((time.time() - stream_start) * 1000)

            # LLM 호출 시작
            if event_kind == "on_chat_model_start" and not llm_started:
                print(f"[{self.name}] [TIMING] LLM call started: {elapsed}ms")
                llm_started = True

            # 첫 번째 LLM 토큰 (스트리밍 시작)
            if event_kind == "on_chat_model_stream" and not first_token:
                print(f"[{self.name}] [TIMING] First LLM token: {elapsed}ms")
                first_token = True

            # 도구 실행 시작
            if event_kind == "on_tool_start" and not tool_started:
                tool_name = event.get("name", "unknown")
                print(f"[{self.name}] [TIMING] Tool '{tool_name}' started: {elapsed}ms")
                tool_started = True

            yield event

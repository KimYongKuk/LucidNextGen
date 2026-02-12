"""Worker Agent 기본 클래스"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, AsyncIterator, Optional
from botocore.config import Config as BotoConfig
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.core.model_config import get_worker_config, ModelConfig

# Bedrock API 타임아웃 (복잡한 도구 호출 시 기본 60초 초과 방지)
BEDROCK_CONFIG = BotoConfig(read_timeout=120, connect_timeout=10)

# Agent 최대 반복 횟수 (도구 호출 루프 방지)
# LangGraph에서 recursion_limit은 graph step 단위 (LLM호출 + 도구실행 = 2 step)
# 예: 20 = 최대 10회 도구 호출 가능
AGENT_RECURSION_LIMIT = 20

# ============================================================================
# 루시드AI (LucidAI) 아이덴티티 및 기능 정의
# ============================================================================
LUCID_AI_IDENTITY = """## 루시드AI (LucidAI) - AI 어시스턴트

당신의 이름은 **루시드AI(LucidAI)**입니다.

### 수행 가능한 기능:
1. **일반 대화 및 지식 질의** - 코딩 도움, 번역, 수학 계산, 글쓰기, 요약, 아이디어 정리 등
2. **실시간 웹 검색** - 뉴스, 날씨, 주가, 최신 트렌드 등 실시간 정보 검색
3. **사내 문서 검색** - 인사(HR), 회계, IT, 안전 관련 사내 규정 및 문서 검색
4. **조직도 조회** - 부서, 근무지, 담당자 등 사내 조직 정보 검색
5. **파일 분석** - 업로드한 PDF, DOCX, XLSX, PPTX, TXT, CSV 파일 분석 및 질의응답
6. **PDF 문서 생성** - 보고서, 기술 문서 등을 PDF 파일로 생성
7. **차트/그래프 생성** - 라인, 막대, 파이, 복합 차트 등 데이터 시각화
8. **PPT 프레젠테이션 생성** - 발표자료 및 슬라이드 자동 생성 (표, 차트 포함)
9. **YouTube 영상 요약** - YouTube URL을 입력하면 핵심 내용 요약
10. **URL 콘텐츠 분석** - 뉴스 기사, 블로그, 웹 페이지 콘텐츠 추출 및 분석
11. **IT 지원** - IT 관련 문의 사례(VOC) 검색 및 IT 문제 해결 가이드
12. **회계/재경 지원** - 회계 관련 문의 사례(VOC) 검색, 전표 처리, 세금계산서 등 재경 업무 지원
13. **워크스페이스** - 독립적 작업 공간에서 문서 업로드, 커스텀 지시사항 설정, 대화 기억 등 프로젝트별 관리

사용자가 루시드AI의 기능이나 할 수 있는 일에 대해 물어보면 위 목록을 바탕으로 친절하게 안내하세요.
당신 자신을 소개할 때는 "루시드AI"라는 이름을 사용하세요.
"""


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

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        컨텍스트를 반영한 시스템 프롬프트 생성

        Args:
            context: 세션, 워크스페이스 등 컨텍스트 정보
            memory_context: 워크스페이스 메모리 (요약, 핵심 사실)
        """
        prompt = self.system_prompt

        # ============ 워크스페이스 메모리 주입 ============
        if memory_context and memory_context.get("summary"):
            key_facts = memory_context.get("key_facts", [])
            facts_text = "\n".join(f"  - {fact}" for fact in key_facts) if key_facts else "  (없음)"

            memory_section = f"""## Workspace Memory (이전 대화 기억)

**대화 요약:**
{memory_context["summary"]}

**핵심 사실:**
{facts_text}

---
위 메모리를 참고하여 일관성 있고 맥락에 맞는 응답을 제공하세요.
이전에 논의된 내용을 반복 질문하면 메모리를 참조하여 답변하세요.

"""
            prompt = memory_section + prompt

        # 날짜 정보 추가
        current_date = _get_current_date_info()
        prompt = f"""## Today's Date: {current_date}

## CRITICAL - 검색 결과 날짜 준수 (MUST FOLLOW):
오늘 날짜는 {current_date}입니다. 이 날짜를 기준으로 답변하세요.

**절대 규칙:**
1. 검색/도구 결과에서 가져온 날짜와 연도를 **절대로 수정하지 마세요**
2. 검색 결과에 나온 날짜를 **그대로** 출력하세요
3. 검색 결과의 정보를 답변에 사용하세요
4. 뉴스 기사의 날짜가 검색 결과에 명시되어 있으면 해당 날짜를 그대로 인용하세요
5. "최근 뉴스"를 요청받으면 검색 결과의 실제 날짜를 사용하세요

**금지 사항:**
- 검색 결과의 날짜를 임의로 수정하는 것
- 과거 날짜로 바꾸거나 추정하는 것

## 학습 데이터/지식 cutoff 관련 질문 대응:
사용자가 "언제까지 학습되었나요?", "데이터가 언제까지인가요?", "지식 cutoff가 언제인가요?" 등을 물으면:
- 특정 연도나 날짜를 언급하지 마세요
- 대신 이렇게 답변하세요: "저는 루시드AI로, 최신 정보는 웹 검색 기능을 통해 제공해 드릴 수 있습니다. 궁금하신 내용이 있으시면 질문해 주세요!"

{LUCID_AI_IDENTITY}

{prompt}"""

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
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        스트리밍 응답 생성

        Args:
            messages: 대화 메시지 리스트
            context: 요청 컨텍스트
            all_tools: MCP에서 로드된 전체 도구 리스트
            memory_context: 워크스페이스 메모리 (요약, 핵심 사실)

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
            config=BEDROCK_CONFIG,
        )
        model_time = int((time.time() - model_start) * 1000)
        print(f"[{self.name}] [TIMING] Model creation: {model_time}ms")

        # 도구 필터링
        filter_start = time.time()
        filtered_tools = self.filter_tools(all_tools)
        filter_time = int((time.time() - filter_start) * 1000)
        print(f"[{self.name}] Using tools: {[t.name for t in filtered_tools]}")
        print(f"[{self.name}] [TIMING] Tool filtering: {filter_time}ms")

        # 시스템 프롬프트 생성 (메모리 컨텍스트 포함)
        prompt_start = time.time()
        system_prompt = self.build_system_prompt(context, memory_context)
        prompt_time = int((time.time() - prompt_start) * 1000)
        print(f"[{self.name}] [TIMING] System prompt build: {prompt_time}ms")
        if memory_context:
            print(f"[{self.name}] Memory context injected: {len(memory_context.get('summary', ''))} chars")

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

        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        ):
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

"""Worker Agent 기본 클래스"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, AsyncIterator, Iterator, Optional
from botocore.config import Config as BotoConfig
from langchain_aws import ChatBedrockConverse
from langchain_aws.chat_models.bedrock_converse import (
    _messages_to_bedrock,
    _parse_response,
    _parse_stream_event,
    _snake_to_camel_keys,
)
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.core.model_config import get_worker_config, ModelConfig
from app.core.region_fallback import get_region_fallback_manager
from app.utils.bedrock_exceptions import is_throttling_error

# Bedrock API 타임아웃 (복잡한 도구 호출 시 기본 60초 초과 방지)
BEDROCK_CONFIG = BotoConfig(read_timeout=120, connect_timeout=10)

# Agent 최대 반복 횟수 (도구 호출 루프 방지)
# LangGraph에서 recursion_limit은 graph step 단위 (LLM호출 + 도구실행 = 2 step)
# 예: 20 = 최대 10회 도구 호출 가능
AGENT_RECURSION_LIMIT = 20

# ============================================================================
# 이전 Tool 결과 압축 설정 (ReAct loop 토큰 누적 방지)
# ============================================================================
COMPACT_KEEP_RECENT_PAIRS = 1    # 최근 N개 tool call 쌍은 원본 유지
COMPACT_SUMMARY_MAX_CHARS = 200  # 압축된 tool result 최대 길이
COMPACT_ARGS_MAX_CHARS = 300     # 압축된 tool_call args 최대 길이

# ============================================================================
# Haiku 대화 요약 파이프라인 설정 (멀티턴 토큰 누적 방지)
# ============================================================================
SUMMARIZATION_MESSAGE_THRESHOLD = 12    # 최소 메시지 개수 (6턴 대화)
SUMMARIZATION_CHAR_THRESHOLD = 15000   # 최소 총 문자 수

DEFAULT_SUMMARIZATION_PROMPT = """다음 대화 내용을 요약해줘.

## 핵심 원칙: 구조 보존 우선
요약하되 **원문의 구조와 라벨을 최대한 유지**한다. 내용을 줄이더라도 식별 가능한 형태를 보존한다.

## 요약 지침
1. **선택지/옵션 보존**: "옵션 A", "방안 1", "안 ①" 등 번호·라벨이 붙은 선택지는 각각의 핵심 내용을 라벨과 함께 보존. 사용자가 나중에 "옵션 A로 가자"라고 참조할 수 있어야 한다.
2. **구조화 데이터 보존**: 테이블, 목록, 비교표는 마크다운 원본 형식 유지 (테이블은 상위 10행 + "총 N행")
3. **핵심 데이터**: 숫자, 통계, 파일명, URL은 정확히 보존
4. **결정 사항 기록**: 사용자가 선택/확정/거부한 내용은 명시적으로 기록
5. **작업 맥락 보존**: 생성된 파일명, 사용한 데이터, 적용한 형식/조건
6. **사용자의 최종 요청** 명확히 기록
7. 마크다운 형식으로 정리
8. 최대 1000단어
9. "[이전 단계에서 가져온 데이터]"로 시작하는 메시지는 데이터 원본을 최대한 보존

## ⚠️ 절대 하지 말 것:
- 선택지를 "여러 옵션을 논의함"으로 뭉뚱그리기 — 각 옵션의 핵심을 개별 보존
- 테이블을 "표가 제시됨"으로 축약 — 구조 유지
- 라벨/번호 제거 — 원문의 식별자 유지

## 대화 내용:
{conversation}

---
## 요약:"""


# ============================================================================
# Prompt Caching 지원 ChatBedrockConverse
# ============================================================================
class CachedChatBedrockConverse(ChatBedrockConverse):
    """system prompt에 cachePoint를 추가하여 Bedrock Prompt Caching 활성화.

    Agent loop에서 동일 system prompt가 반복 전송될 때,
    첫 호출은 cache write, 이후 호출은 cache read (입력 토큰 90% 절감).
    """

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        bedrock_messages, system = _messages_to_bedrock(messages)
        if system:
            system.append({"cachePoint": {"type": "default"}})
        params = self._converse_params(
            stop=stop,
            **_snake_to_camel_keys(
                kwargs, excluded_keys={"inputSchema", "properties", "thinking"}
            ),
        )
        response = self.client.converse(
            messages=bedrock_messages, system=system, **params
        )
        response_message = _parse_response(response)
        response_message.response_metadata["model_name"] = self.model_id
        return ChatResult(generations=[ChatGeneration(message=response_message)])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        bedrock_messages, system = _messages_to_bedrock(messages)
        if system:
            system.append({"cachePoint": {"type": "default"}})
        params = self._converse_params(
            stop=stop,
            **_snake_to_camel_keys(
                kwargs, excluded_keys={"inputSchema", "properties", "thinking"}
            ),
        )
        response = self.client.converse_stream(
            messages=bedrock_messages, system=system, **params
        )
        added_model_name = False
        for event in response["stream"]:
            if message_chunk := _parse_stream_event(event):
                if (
                    hasattr(message_chunk, "usage_metadata")
                    and message_chunk.usage_metadata
                    and not added_model_name
                ):
                    message_chunk.response_metadata["model_name"] = self.model_id
                    added_model_name = True
                generation_chunk = ChatGenerationChunk(message=message_chunk)
                if run_manager:
                    run_manager.on_llm_new_token(
                        generation_chunk.text, chunk=generation_chunk
                    )
                yield generation_chunk

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
7. **Word(DOCX) 문서 생성** - 편집 가능한 Word 문서 생성 (보고서, 기안서 등)
8. **차트/그래프 생성** - 라인, 막대, 파이, 복합 차트 등 데이터 시각화
9. **PPT 프레젠테이션 생성** - 발표자료 및 슬라이드 자동 생성 (표, 차트 포함)
10. **YouTube 영상 요약** - YouTube URL을 입력하면 핵심 내용 요약
11. **URL 콘텐츠 분석** - 뉴스 기사, 블로그, 웹 페이지 콘텐츠 추출 및 분석
12. **IT 지원** - IT 관련 문의 사례(VOC) 검색 및 IT 문제 해결 가이드
13. **회계/재경 지원** - 회계 관련 문의 사례(VOC) 검색, 전표 처리, 세금계산서 등 재경 업무 지원
14. **워크스페이스** - 독립적 작업 공간에서 문서 업로드, 커스텀 지시사항 설정, 대화 기억 등 프로젝트별 관리
15. **메일 조회** - 받은편지함, 보낸편지함 조회, 메일 검색, 안 읽은 메일 확인, 메일 요약, 답장 초안 작성
16. **전자결재 조회** - 결재 대기함, 기안함, 결재 완료함, 참조함, 부서 문서함 조회, 결재 병목 분석
17. **엑셀(XLSX) 생성/수정** - 엑셀 파일 새로 생성, 기존 파일 수정, 서식 적용, 차트/피벗테이블
18. **사내 게시판 검색** - 사내 게시판 게시글 검색, 공지사항 조회, 본문 상세 조회

사용자가 루시드AI의 기능이나 할 수 있는 일에 대해 물어보면 위 목록을 바탕으로 친절하게 안내하세요.
당신 자신을 소개할 때는 "루시드AI"라는 이름을 사용하세요.
"""


def _get_current_date_info() -> str:
    """현재 날짜 정보를 한국어로 반환"""
    now = datetime.now()
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    weekday_kr = weekdays[now.weekday()]
    return f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"


# ============================================================================
# Worker별 팔로우업 제안 능력 메뉴
# ============================================================================
WORKER_FOLLOW_UP_CAPABILITIES = {
    "DirectResponseWorker": [
        "Deepen: 현재 주제 심화 (예시 요청, 비교 분석, 장단점, 구체적 사례)",
        "Transform: 결과를 PDF/PPT/엑셀로 변환, 차트로 시각화",
        "Explore: 관련 주제 웹 검색, 사내 문서 검색",
    ],
    "WebSearchWorker": [
        "Deepen: 검색 결과 심화 (특정 기업/인물/기간 집중, 상세 분석)",
        "Transform: 검색 결과를 보고서 PDF/PPT로 정리, 데이터 차트화",
        "Explore: 관련 트렌드, 경쟁사 비교, 사내 문서 교차 검색",
    ],
    "UserFilesWorker": [
        "Deepen: 파일의 다른 섹션 분석, 특정 데이터 심층 탐구",
        "Transform: 분석 결과를 차트/PDF/엑셀로 변환",
        "Explore: 파일 내 다른 주제, 통계 요약, 비교 분석",
    ],
    "CorpRAGWorker": [
        "Deepen: 규정의 구체적 조항, 예외사항, 적용 사례 확인",
        "Transform: 관련 규정 요약 PDF/PPT 생성",
        "Explore: 유사 규정 비교, 관련 IT/회계 VOC 검색",
    ],
    "YouTubeWorker": [
        "Deepen: 영상의 특정 구간 상세 분석, 핵심 인사이트 심화",
        "Transform: 요약을 PDF 보고서나 PPT로 변환",
        "Explore: 관련 주제 웹 검색, 유사 영상 탐색",
    ],
    "URLFetchWorker": [
        "Deepen: 기사/페이지의 특정 부분 상세 분석, 배경 설명",
        "Transform: 내용을 요약 PDF/PPT로 변환",
        "Explore: 관련 기사 웹 검색, 추가 출처 확인",
    ],
    "ITSupportWorker": [
        "Deepen: 해당 IT 이슈의 해결 절차 상세 안내, 유사 사례 비교",
        "Transform: 해결 가이드를 PDF로 정리",
        "Explore: 유사 IT 이슈 추가 검색, 관련 사내 규정 확인",
    ],
    "AcctSupportWorker": [
        "Deepen: 전표 처리 절차 상세, 예외 케이스 확인",
        "Transform: 회계 처리 가이드를 PDF로 정리",
        "Explore: 유사 회계 이슈 검색, 관련 사내 규정 확인",
    ],
    "MailWorker": [
        "Deepen: 메일 전체 본문 조회, 메일 요약, 답장 초안 작성",
        "Transform: 메일 목록을 엑셀로 정리, 요약 PDF 생성",
        "Explore: 다른 메일함 조회, 발신자/키워드별 검색, 안 읽은 메일 확인",
    ],
    "ApprovalWorker": [
        "Deepen: 특정 결재 문서 상세, 결재 진행 상태/이력 확인",
        "Transform: 결재 현황을 엑셀/PDF로 정리",
        "Explore: 다른 결재함 조회, 기간별/기안자별 분석",
    ],
    "PPTWorker": [
        "Deepen: 특정 슬라이드 수정, 내용 보강, 레이아웃 변경",
        "Transform: PPT 내용을 PDF로 변환, 데이터를 엑셀로 추출",
        "Explore: 관련 주제 웹 검색으로 추가 자료 수집",
    ],
    "XlsxWorker": [
        "Deepen: 추가 시트/수식/서식 적용, 데이터 검증",
        "Transform: 엑셀 데이터를 차트로 시각화, PDF 보고서 생성",
        "Explore: 피벗테이블 추가, 다른 분석 관점",
    ],
    "BoardWorker": [
        "Deepen: 특정 게시글 상세 조회, 작성자별 필터링",
        "Transform: 게시판 내용을 PDF/엑셀로 정리",
        "Explore: 다른 게시판 검색, 기간별 조회",
    ],
}

DEFAULT_FOLLOW_UP_CAPABILITIES = [
    "Deepen: 현재 주제에 대해 더 깊이 탐구",
    "Transform: 결과를 다른 형식(PDF/차트/엑셀/PPT)으로 변환",
    "Explore: 관련된 다른 주제 탐색 (웹 검색, 사내 문서 등)",
]


def _compact_tool_call_args(args: dict, max_chars: int = COMPACT_ARGS_MAX_CHARS) -> dict:
    """AIMessage의 tool_calls args를 축약.

    큰 값(data 배열, 긴 문자열)만 요약으로 대체.
    tool_call 구조(name, id)는 보존.
    """
    compacted = {}
    for key, val in args.items():
        val_str = str(val)
        if len(val_str) <= max_chars:
            compacted[key] = val
        elif isinstance(val, list):
            # data 배열 등: 행/열 개수만 표시
            if val and isinstance(val[0], list):
                compacted[key] = f"[{len(val)}행 x {len(val[0])}열 데이터 생략]"
            elif val and isinstance(val[0], dict):
                compacted[key] = f"[{len(val)}개 dict 항목 생략]"
            else:
                compacted[key] = f"[{len(val)}개 항목 생략]"
        elif isinstance(val, str) and len(val) > max_chars:
            compacted[key] = val[:max_chars] + f"... ({len(val):,}자 중 {max_chars}자)"
        else:
            compacted[key] = val_str[:max_chars] + f"... (생략)"
    return compacted


def _compact_tool_messages(
    messages: List[BaseMessage],
    keep_last_n: int = COMPACT_KEEP_RECENT_PAIRS,
    max_chars: int = COMPACT_SUMMARY_MAX_CHARS,
) -> List[BaseMessage]:
    """이전 단계의 ToolMessage content + AIMessage tool_calls args를 축약하여 토큰 누적 방지.

    - AIMessage(tool_calls) + ToolMessage 쌍을 식별
    - 최근 keep_last_n 쌍은 원본 유지
    - 이전 쌍의 ToolMessage.content 축약 + AIMessage tool_calls args 축약
    - tool_call_id 페어링 유지 (LangGraph ValidationError 방지)
    """
    # 1. tool call 쌍 인덱스 수집: (ai_index, [tool_msg_indices])
    chains: List[tuple] = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            tool_indices = []
            for j in range(i + 1, len(messages)):
                if isinstance(messages[j], ToolMessage):
                    tool_indices.append(j)
                elif isinstance(messages[j], AIMessage):
                    break
            if tool_indices:
                chains.append((i, tool_indices))

    if len(chains) <= keep_last_n:
        return messages  # 압축 불필요

    # 2. 압축 대상 인덱스 수집
    compact_ai_indices: set = set()
    compact_tool_indices: set = set()
    for ai_idx, tool_indices in chains[:-keep_last_n]:
        compact_ai_indices.add(ai_idx)
        compact_tool_indices.update(tool_indices)

    # 3. 메시지 복사 + 압축
    result = []
    compacted_tool_count = 0
    compacted_ai_count = 0
    original_chars = 0
    compacted_chars = 0

    for i, msg in enumerate(messages):
        if i in compact_tool_indices and isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            original_chars += len(content)

            if len(content) > max_chars:
                short = content[:max_chars].rstrip()
                new_content = f"[이전 결과] {short}... ({len(content):,}자 중 {max_chars}자 표시)"
                compacted_chars += len(new_content)
                compacted_tool_count += 1
                result.append(ToolMessage(
                    content=new_content,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None) or "tool",
                ))
            else:
                compacted_chars += len(content)
                result.append(msg)

        elif i in compact_ai_indices and isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # AIMessage tool_calls args 축약
            new_tool_calls = []
            args_compacted = False
            for tc in msg.tool_calls:
                tc_args = tc.get("args", {})
                tc_args_str = str(tc_args)
                if len(tc_args_str) > COMPACT_ARGS_MAX_CHARS:
                    compacted_args = _compact_tool_call_args(tc_args)
                    new_tool_calls.append({**tc, "args": compacted_args})
                    args_compacted = True
                    original_chars += len(tc_args_str)
                    compacted_chars += len(str(compacted_args))
                else:
                    new_tool_calls.append(tc)

            if args_compacted:
                compacted_ai_count += 1
                result.append(AIMessage(
                    content=msg.content,
                    tool_calls=new_tool_calls,
                ))
            else:
                result.append(msg)
        else:
            result.append(msg)

    total_compacted = compacted_tool_count + compacted_ai_count
    if total_compacted > 0:
        print(
            f"[COMPACT] ToolMsg={compacted_tool_count}개 + AIMsg_args={compacted_ai_count}개 압축: "
            f"{original_chars:,}자 → {compacted_chars:,}자 "
            f"({(1 - compacted_chars / max(original_chars, 1)) * 100:.0f}% 절감)"
        )

    return result


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

    @property
    def max_agent_steps(self) -> int:
        """Agent 최대 반복 횟수 (도구 호출이 많은 Worker에서 override)"""
        return AGENT_RECURSION_LIMIT

    @property
    def compact_previous_results(self) -> bool:
        """이전 단계 Tool 결과 압축 여부 (기본: False)

        True로 설정 시 ReAct agent loop에서 이전 tool 결과를 축약하여
        토큰 누적을 방지합니다. 다단계 도구 호출이 많은 Worker에서 사용.
        """
        return False

    @property
    def compact_keep_recent_pairs(self) -> int:
        """원본 유지할 최근 tool call 쌍 개수 (기본: COMPACT_KEEP_RECENT_PAIRS=1)

        - XlsxWorker 등 순차 빌드 패턴: 1 (이전 결과 불필요)
        - MailWorker 등 병렬 수집 패턴: 5+ (다건 상세 조회 후 종합 필요)
        """
        return COMPACT_KEEP_RECENT_PAIRS

    @property
    def summarization_prompt(self) -> str:
        """Haiku 요약용 프롬프트 (Worker별 커스터마이즈 가능)"""
        return DEFAULT_SUMMARIZATION_PROMPT

    @property
    def skip_summarization(self) -> bool:
        """대화 요약을 건너뛸지 여부 (기본: False)

        DirectWorker 등 특수 워커에서 직접 요약을 관리하는 경우 True로 오버라이드.
        """
        return False

    @property
    def shared_tool_names(self) -> List[str]:
        """공유 도구함 — 파일 산출물 생성용 (기본: 활성)

        차트(Recharts), PDF, DOCX 등 시각화/문서 생성 도구를 공유합니다.
        VisualizationWorker 없이도 각 에이전트가 필요 시 직접 사용 가능.
        모든 Worker에 기본 제공 — 불필요한 Worker에서 빈 리스트로 오버라이드.
        """
        return [
            "create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
            "create_document_pdf", "create_table_spec_pdf", "create_document_docx",
        ]

    def get_model_config(self) -> ModelConfig:
        """모델 설정 반환"""
        return get_worker_config(use_sonnet=self.use_sonnet)

    def filter_tools(self, all_tools: List[BaseTool]) -> List[BaseTool]:
        """MCP 도구 중 이 Worker가 사용할 도구만 필터링 (전용 + 공유)"""
        all_tool_names = self.tool_names + self.shared_tool_names
        if not all_tool_names:
            return []
        return [t for t in all_tools if t.name in all_tool_names]

    # Output 파일을 생성하는 MCP 도구 목록 (아카이브 대상)
    ARCHIVABLE_TOOLS = {
        "create_document_pdf", "create_table_spec_pdf", "create_document_docx",
        "create_presentation",
        "create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
        "create_workbook", "write_data_to_excel",
    }

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any]
    ) -> List[BaseTool]:
        """도구 후처리 훅 — 기본: Output 파일 아카이브 래핑"""
        return self._wrap_tools_for_archive(tools, context)

    def _wrap_tools_for_archive(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any],
    ) -> List[BaseTool]:
        """Output 파일 생성 도구에 아카이브 복사 후처리를 래핑"""
        from app.utils.file_archive import archive_file, extract_output_filepath

        user_id = context.get("user_id", "unknown")
        archivable = self.ARCHIVABLE_TOOLS

        for tool in tools:
            if tool.name not in archivable:
                continue

            # 이미 아카이브 래핑된 경우 스킵
            if getattr(tool, "_archive_wrapped", False):
                continue

            # 항상 현재 ainvoke를 사용 (보안 래핑이 이미 적용된 경우 보존)
            original_ainvoke = tool.ainvoke

            async def archive_ainvoke(
                input_data,
                config=None,
                *,
                _original=original_ainvoke,
                _user_id=user_id,
                _tool_name=tool.name,
                **kwargs,
            ):
                result = await _original(input_data, config, **kwargs)

                # 도구 결과에서 파일 경로 추출 후 아카이브
                try:
                    result_text = ""
                    if hasattr(result, "content"):
                        result_text = str(result.content)
                    elif isinstance(result, str):
                        result_text = result

                    if result_text:
                        filepath = extract_output_filepath(result_text)
                        if filepath:
                            archive_file(filepath, _user_id)
                except Exception as e:
                    print(f"[Archive] Warning: {_tool_name} archive failed: {e}")

                return result

            object.__setattr__(tool, "ainvoke", archive_ainvoke)
            object.__setattr__(tool, "_archive_wrapped", True)

        return tools

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        컨텍스트를 반영한 시스템 프롬프트 생성

        Args:
            context: 세션, 워크스페이스 등 컨텍스트 정보
            memory_context: 워크스페이스 메모리 (요약, 핵심 사실)
            user_memory_context: 사용자 전역 메모리 (key_facts만)
        """
        prompt = self.system_prompt

        # ============ 전역 사용자 메모리 주입 ============
        if user_memory_context and user_memory_context.get("key_facts"):
            facts = user_memory_context["key_facts"]
            facts_text = "\n".join(f"  - {fact}" for fact in facts)
            user_memory_section = f"""## User Profile (사용자 개인 특성)

이 사용자에 대해 알려진 정보:
{facts_text}

당신은 이 사용자와의 이전 대화 내용을 기억하고 있습니다.
- 사용자가 자신에 대해 물어보거나(이름, 관심사, 선호도 등), 이전 대화/기억에 대해 질문하면 위 정보를 기반으로 답변하세요.
- 그 외에는 불필요하게 언급하지 마세요.

"""
            prompt = user_memory_section + prompt

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
        prompt = f"""## Today: {current_date}

**날짜 규칙**: 검색/도구 결과의 날짜를 절대 수정하지 마세요. 결과에 나온 날짜를 그대로 출력하세요.
**학습 데이터 질문**: "저는 루시드AI로, 최신 정보는 웹 검색 기능을 통해 제공해 드릴 수 있습니다. 궁금하신 내용이 있으시면 질문해 주세요!"로 답변하세요.

{LUCID_AI_IDENTITY}

{prompt}"""

        # ============ 업로드 파일 컨텍스트 (모든 워커 공통) ============
        has_files = context.get("has_files", False)
        workspace_has_files = context.get("workspace_has_files", False)
        if has_files or workspace_has_files:
            session_id = context.get("session_id", "")
            workspace_uuid = context.get("workspace_uuid") or context.get("workspace_id", "")
            session_file_names = context.get("session_file_names", [])
            workspace_file_names = context.get("workspace_file_names", [])
            all_file_names = session_file_names + workspace_file_names

            file_list = ", ".join(all_file_names) if all_file_names else "(파일명 미확인)"
            file_section = f"""
## UPLOADED FILES — 사용자 업로드 파일

사용자가 파일을 업로드했습니다: {file_list}

**규칙:**
- 사용자가 "분석해줘", "요약해줘", "이거", "파일" 등 업로드 파일을 참조하는 것으로 보이면, 반드시 파일 검색 도구를 먼저 호출하세요.
- search_user_files(session_id="{session_id}", query="검색어") — 업로드 파일 검색
- search_workspace_docs(workspace_uuid="{workspace_uuid}", query="검색어") — 워크스페이스 문서 검색
- "파일에 접근할 수 없습니다"라고 절대 답하지 마세요. 위 도구로 검색 가능합니다.
"""
            prompt += file_section

        # ============ 대화 히스토리 데이터 활용 ============
        prompt += """

## CONVERSATION DATA — 대화 히스토리 데이터 활용

이전 대화에서 다른 기능(메일 조회, 웹 검색, 문서 검색 등)을 통해 가져온 데이터가 히스토리에 포함되어 있을 수 있습니다.

**규칙:**
1. 사용자가 이전 데이터를 참조하는 요청("이걸로 엑셀 만들어줘", "위 내용을 정리해줘" 등)을 하면, 히스토리에서 해당 데이터를 찾아 직접 활용하세요.
2. 히스토리에 필요한 데이터가 있는데 "접근할 수 없습니다" / "지원하지 않습니다"라고 답하지 마세요. 히스토리의 데이터는 당신이 사용할 수 있습니다.
3. 히스토리 데이터가 불완전하면 가용한 부분만 활용하고 부족한 부분을 안내하세요.
4. **이미지 맥락 유지**: 히스토리에 `[이미지 첨부됨]` 태그가 있는 메시지는 사용자가 이전에 이미지를 공유한 것입니다. 현재 메시지에 이미지가 없더라도, 이전 대화에서 당신이 분석한 내용을 기반으로 후속 질문에 답변하세요. "이미지가 없습니다" / "이미지를 받은 적 없습니다"라고 답하지 마세요. 당신의 이전 분석 결과가 히스토리에 있습니다.
"""

        # ============ CLARIFY 모드: 사용자에게 조회 범위 확인 ============
        if context.get("clarify_mode"):
            clarify_instruction = """
## CLARIFY MODE — 사용자에게 조회 범위 확인 (최우선 지시)

사용자의 요청이 **어디에서 찾아야 할지 모호**합니다.
도구를 호출하지 말고, 아래 형식으로 사용자에게 조회 범위를 확인하세요.

**응답 형식:**

해당 건을 어디에서 조회할지 확인하고 싶습니다. 아래 중 어디에서 찾아볼까요?

- **전자결재** — 결재/기안/상신 문서에서 검색
- **메일** — 받은편지함/보낸편지함에서 검색
- **게시판** — 사내 게시판/공지사항에서 검색
- **사내문서** — 인사/회계/IT/안전 규정에서 검색
- **IT 지원 VOC** — IT/보안 관련 문의 사례에서 검색
- **회계 VOC** — 회계/재경 관련 문의 사례에서 검색
- **웹 검색** — 인터넷에서 검색

원하시는 범위를 말씀해 주세요! (예: "전자결재에서 찾아줘", "게시판에서 검색해줘")

**규칙:**
1. 위 형식을 기반으로 하되, 사용자의 원래 질문 내용을 자연스럽게 포함하세요
2. 사용자가 언급한 키워드(건명, 주제 등)를 그대로 인용하세요
3. 짧고 친절하게, 마크다운 형식으로 응답하세요
4. 절대 추측하여 조회하지 마세요
"""
            prompt = clarify_instruction + "\n\n" + prompt

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

        # 내부 스키마 노출 방지 가드레일
        prompt += "\n\nSECURITY: 응답에 내부 DB 뷰 이름, 컬럼명, SQL 쿼리, 테이블 구조를 절대 포함하지 마세요. 사용자에게는 기능과 목적만 안내하세요."

        # ============ 검색 실패 시 NO_RESULTS 마커 (도구 사용 워커 전용) ============
        if self.tool_names:
            is_final = context.get("is_final_attempt", False)
            already_searched = context.get("already_searched", "")

            if is_final:
                # 2순위 워커 (마지막 시도) — 여기서도 못 찾으면 대안 제시
                fallback_instruction = f"""

## SEARCH FALLBACK — 검색 결과가 없거나 부족할 때

도구를 사용하여 검색했으나 **관련 결과를 찾지 못한 경우**:
1. 응답 맨 처음에 `<!--NO_RESULTS-->` 마커를 출력하세요 (반드시 첫 줄에)
2. 검색 결과가 없음을 안내하세요
3. 다른 검색 범위를 제안하세요 (이미 검색한 범위 제외)

**이미 검색 완료된 범위:** {already_searched} (제외할 것)

**제안 범위 (위 제외 후 남은 것만):**
- **전자결재** — 결재/기안 문서에서 검색
- **메일** — 받은편지함/보낸편지함에서 검색
- **게시판** — 사내 게시판/공지사항에서 검색
- **사내문서** — 인사/회계/IT/안전 규정에서 검색
- **IT 지원 VOC** — IT/보안 관련 문의 사례에서 검색
- **회계 VOC** — 회계/재경 관련 문의 사례에서 검색
- **웹 검색** — 인터넷에서 검색

**규칙:**
- 결과를 찾은 경우에는 마커와 대안 제안을 하지 마세요 (정상 응답만)
"""
            else:
                # 1순위 워커 — 못 찾으면 마커만 (시스템이 자동 fallback)
                fallback_instruction = """

## SEARCH FALLBACK — 검색 결과가 없거나 부족할 때

도구를 사용하여 검색했으나 **관련 결과를 찾지 못한 경우**:
1. 응답 맨 처음에 `<!--NO_RESULTS-->` 마커를 출력하세요 (반드시 첫 줄에)
2. 검색 결과가 없음을 간단히 안내하세요
3. 대안 검색 범위 목록은 제시하지 마세요 (시스템이 자동으로 다른 곳에서 검색합니다)

**규칙:**
- 결과를 찾은 경우에는 마커를 출력하지 마세요 (정상 응답만)
"""
            prompt += fallback_instruction

        # ============ 인라인 SVG 시각화 가이드 (모든 에이전트 공통) ============
        inline_viz_guide = """

## 시각화 활용 가이드

**기본 원칙: 텍스트와 마크다운이 기본입니다.**
대부분의 답변은 마크다운 텍스트(표, 목록, 코드블록 등)로 충분합니다.
시각화 도구(차트, SVG, HTML 위젯)는 아래 조건을 **모두** 만족할 때만 사용하세요:
1. 사용자가 명시적으로 시각화를 요청했거나 ("그래프로", "차트로", "도식화", "플로우차트", "비교표로 보여줘" 등)
2. 또는 데이터가 복잡하여 텍스트/마크다운 표로는 전달이 어려운 경우 (수치 데이터 5개 이상 비교, 복잡한 프로세스 흐름 등)

**하지 마세요:**
- 단순 정보 전달에 SVG/HTML 위젯 사용 (마크다운 표로 충분)
- 항목 3~4개 비교에 차트 도구 호출 (마크다운 표 사용)
- 사용자가 요청하지 않은 인포그래픽/다이어그램 자동 생성

### 선택 기준 (시각화가 필요하다고 판단된 경우)

**축이 있으면 → Recharts 차트 도구 호출**
수치 데이터의 추이/비교/분포. 5개 이상 데이터 포인트.
→ create_line_chart, create_bar_chart, create_pie_chart, create_multi_chart
(이 도구가 있는 경우에만 사용 가능)

**화살표가 있으면 → SVG 직접 생성**
프로세스, 관계, 구조, 흐름을 도식화. 박스+화살표가 핵심.
→ 응답에 `<svg>` 태그 직접 출력

**행/열이 있으면 → HTML 위젯**
비교표, 카드 그리드, 대시보드, 텍스트+구조 혼합 레이아웃.
→ 응답에 `<lucid-html>` 태그로 감싸서 출력

**회색지대:** 항목 5개 이하 단순 바 비교 → 마크다운 표 사용. 항목 5개 초과 → Recharts.
**애매한 경우:** 마크다운 표를 먼저 고려하고, 그래도 부족할 때만 도구 사용.

---

### SVG 모드 규칙
응답 텍스트에 `<svg>` 태그를 직접 출력하면 프론트엔드가 실시간 렌더링합니다.

**필수 속성:**
- `xmlns="http://www.w3.org/2000/svg"` 필수
- `viewBox="0 0 800 600"` (가로) 또는 `viewBox="0 0 600 900"` (세로)
- width/height 속성 생략 (프론트엔드가 반응형 처리)

**다크 테마 디자인:**
- 텍스트: `#E2E8F0`, 부제: `#94A3B8`
- 강조: `#60A5FA`(파랑), `#34D399`(초록), `#F87171`(빨강), `#FBBF24`(노랑), `#A78BFA`(보라)
- 카드: `fill="#2d2d2d" stroke="#404040" rx="12"`
- 폰트: `font-family="Malgun Gothic, sans-serif"`
- 연결선: `stroke="#94A3B8" stroke-width="2"`
- **모든 텍스트가 viewBox 안에 들어와야 함** (넘침 금지)

**금지:** `<script>`, `<foreignObject>`, `on*` 이벤트 핸들러

---

### HTML 위젯 모드 규칙
`<lucid-html>` 태그로 감싸서 출력하면 프론트엔드가 iframe 안에서 격리 렌더링합니다.

**출력 형식:**
```
<lucid-html>
<style>
  /* CSS 먼저 (짧게) */
</style>
<div class="dashboard">
  <!-- HTML 구조 -->
</div>
</lucid-html>
```

**스트리밍 친화 순서:** `<style>` 짧게 먼저 → HTML 구조 바로 이어서 → `<script>`는 맨 마지막 (선택)
이 순서를 지키면 사용자가 코드 완성 전에도 레이아웃이 점진적으로 보입니다.

**기본 스타일 (iframe이 자동 제공, 별도 선언 불필요):**
- `background`, `color`, `font-family`, `table`, `th`, `td` 등 기본 스타일 자동 적용

**CSS 변수 사용 (필수 — 테마 자동 대응):**
iframe에 미리 정의된 CSS 변수를 사용하세요. 하드코딩 색상 대신 변수를 쓰면 라이트/다크 테마가 자동 전환됩니다.

| 변수 | 용도 |
|------|------|
| `var(--w-bg)` | 메인 배경 |
| `var(--w-bg-sub)` | 서브 영역/카드 배경 |
| `var(--w-text)` | 기본 텍스트 |
| `var(--w-text-sub)` | 부제/캡션 텍스트 |
| `var(--w-border)` | 테두리/구분선 |
| `var(--w-link)` | 링크 색상 |
| `var(--w-accent-blue)` | 강조 파랑 |
| `var(--w-accent-green)` | 강조 초록 |
| `var(--w-accent-red)` | 강조 빨강 |
| `var(--w-accent-yellow)` | 강조 노랑 |
| `var(--w-positive)` | 양수/긍정 |
| `var(--w-negative)` | 음수/부정 |
| `var(--w-card)` | 카드 배경 |
| `var(--w-row-alt)` | 테이블 짝수 행 배경 |

**스타일 예시:**
- 카드: `background:var(--w-card); border:1px solid var(--w-border); border-radius:12px; padding:16px`
- 비교 바: 배경 `var(--w-border)` 위에 데이터 `var(--w-accent-blue); border-radius:4px; height:24px`
- 배지: `background:var(--w-badge-bg); color:var(--w-badge-text); border-radius:10px; padding:2px 8px`
- 양수: `color:var(--w-positive)`, 음수: `color:var(--w-negative)`
- 구분선: `border-bottom:1px solid var(--w-border)`
- 행 구분: 짝수 행 `background:var(--w-row-alt)`
- 그리드: `display:grid; grid-template-columns:1fr 1fr; gap:16px`

**중요: 색상을 하드코딩하지 마세요.** `#2d2d2d` 대신 `var(--w-card)`, `#E2E8F0` 대신 `var(--w-text)` 사용.

**구성 패턴 (비교/분석 시):**
1. 헤더 (제목 + 부제 + 날짜)
2. 요약 카드 그리드 (핵심 수치 2~3열)
3. 비교 바 (CSS width로 수평 바 차트)
4. 상세 비교 테이블 (행 배경 교차)
5. 전망/결론 카드
6. 출처 (캡션 크기)

---

### 파일 산출물 (PDF/DOCX/차트) 출력 규칙

**당신은 PDF, Word(DOCX), 차트 생성 도구를 사용할 수 있습니다.**
사용자가 문서 생성을 요청하면 반드시 해당 도구를 호출하세요:
- "PDF로 만들어줘", "PDF로 정리해줘" → `create_document_pdf` 또는 `create_table_spec_pdf`
- "워드로 만들어줘", "Word", "DOCX", "편집 가능한 문서" → `create_document_docx`
- 차트/그래프 요청 → `create_line_chart`, `create_bar_chart`, `create_pie_chart`, `create_multi_chart`
- **"도구가 없습니다", "접근 불가", "생성할 수 없습니다"라고 절대 답하지 마세요.** 도구가 있습니다.

**생성 전 확인:**
- 사용자가 파일 생성을 **명시적으로 요청**한 경우에만 파일 생성 도구를 호출하세요.
- "정리해줘", "알려줘", "설명해줘" 같은 요청에는 텍스트로 답변하세요. 파일을 만들지 마세요.
- 파일이 필요할 것 같으면 "PDF/문서로 만들어드릴까요?" 라고 제안하세요.

**도구 호출 후 확인 (중요!):**
- 파일 생성 도구를 호출한 후, **도구의 반환 결과에서 파일명을 확인**하세요.
- 도구가 에러를 반환했거나 파일명이 없으면, 파일이 생성되지 않은 것입니다.
- **절대로 도구 호출 없이 또는 도구 에러 시 "파일명: xxx.pdf" 형식을 출력하지 마세요.**
- 파일 생성에 실패하면 솔직하게 "파일 생성에 실패했습니다"라고 답변하세요.

**성공 시 출력 형식:**
도구가 성공적으로 파일을 생성한 경우에만 아래 형식으로 출력:
`파일명: 생성된파일명.pdf` 또는 `파일명: 생성된파일명.docx`
(프론트엔드가 이 패턴을 감지하여 다운로드 링크를 자동 생성합니다)
"""
        prompt += inline_viz_guide

        # ============ HANDOFF TARGET — 선행 데이터 수집 역할 ============
        if context.get("is_handoff_target"):
            prompt += """

## PREREQUISITE ROLE (선행 데이터 수집) — 최우선 규칙

당신은 다른 워커의 요청으로 **선행 데이터를 수집하는 역할**로 호출되었습니다.
후속 작업(위키 등록, 메일 발송, 문서 생성 등)은 다른 워커가 자동으로 이어서 처리합니다.

**절대 금지:**
- "~할 수 없습니다", "~기능은 지원하지 않습니다", "~어렵습니다" 등 불가 언급 절대 금지
- 후속 작업에 대한 안내/제안 절대 금지 (예: "PDF로 만들어 드릴까요?", "위키 연동이 필요합니다")
- 당신의 역할 범위 밖의 작업을 언급하거나 설명하지 마세요

**해야 할 것:**
- 당신의 도구로 처리 가능한 부분만 수행
- 도구를 호출하여 데이터를 가져온 뒤, 결과만 깔끔하게 정리하여 응답
- 응답은 순수하게 수집한 데이터/분석 내용만 포함
"""

        # ============ HANDOFF — 다른 워커의 데이터가 필요할 때 ============
        # embed 모드에서는 HANDOFF 비활성화 (허용된 워커만 사용)
        if self.tool_names and not context.get("is_handoff_target") and context.get("chat_mode") not in ("outline_embed", "groupware_embed"):
            from app.agents.state import WORKER_CAPABILITIES, INTENT_TO_WORKER as _ITW
            # 자기 자신 제외한 다른 워커 능력 목록
            other_caps = {k: v for k, v in WORKER_CAPABILITIES.items()
                          if _ITW.get(k) != self.name}
            caps_lines = "\n".join(f"  - `{k.value}`: {v}" for k, v in other_caps.items())

            handoff_instruction = f"""

## HANDOFF — 다른 기능의 데이터가 필요할 때

사용자 요청을 처리하려면 **당신이 보유하지 않은 기능**의 데이터가 필요할 수 있습니다.

**대화 히스토리에 필요한 데이터가 이미 있으면**: HANDOFF 없이 직접 사용하세요.

**히스토리에 없고, 아래 기능에서 가져와야 하는 경우**:
응답 맨 처음에 `<!--HANDOFF:인텐트값-->` 마커를 출력한 뒤, 간단한 안내를 추가하세요.

**사용 가능한 인텐트:**
{caps_lines}

**예시:** 메일 데이터가 필요하면 → `<!--HANDOFF:mail-->` + "메일에서 데이터를 먼저 가져오겠습니다."

**규칙:**
1. 히스토리에 데이터가 있으면 HANDOFF하지 말고 직접 사용
2. HANDOFF는 최대 1개 인텐트만 가능
3. 당신의 도구로 처리 가능한 작업에는 HANDOFF 불필요
"""
            prompt += handoff_instruction

        # ============ 후속 질문 제안 생성 지시 ============
        capabilities = WORKER_FOLLOW_UP_CAPABILITIES.get(
            self.name, DEFAULT_FOLLOW_UP_CAPABILITIES
        )
        caps_text = "\n".join(f"  - {cap}" for cap in capabilities)

        follow_up_instruction = f"""

## FOLLOW-UP SUGGESTIONS (후속 질문 제안)

응답 완료 후, 사용자가 이어서 할 수 있는 후속 질문 3개를 제안하세요.

### 제안 카테고리 (이 중에서 선택):
{caps_text}

### 규칙:
1. 응답의 **구체적인 엔티티명**(사람, 회사, 문서명, 키워드 등)을 포함하여 구체적으로 작성
2. 각 제안은 **15자 이내**의 자연스러운 한국어 질문/요청 형태
3. 반드시 3개 (더 많거나 적으면 안 됨)
4. 응답 본문 마지막에 아래 형식의 HTML 주석으로 추가 (본문과 분리):

<!--FOLLOW_UP:["제안1","제안2","제안3"]-->

### 제안하지 않는 경우 (태그 자체를 생략):
- 간단한 인사 응답 ("안녕하세요", "감사합니다" 등)
- 오류 응답이나 도구 실패
- 후속 질문이 자연스럽지 않은 단순 확인 응답

### 좋은 예시:
- 결재 조회 후: <!--FOLLOW_UP:["김민지 다른 기안 문서 조회","결재 내용 PDF 정리","최근 1주 결재현황 요약"]-->
- 웹 검색 후: <!--FOLLOW_UP:["LG엔솔 실적 상세 분석","2차전지 경쟁사 비교","보고서 PDF로 정리"]-->
- 메일 조회 후: <!--FOLLOW_UP:["발신자 다른 메일 조회","메일 목록 엑셀 정리","안 읽은 메일 확인"]-->

### 나쁜 예시 (너무 일반적 — 금지):
- ❌ "더 알려주세요", "다른 질문", "자세히 설명해줘"
"""
        prompt += follow_up_instruction

        return prompt

    # ========================================================================
    # Haiku 대화 요약 파이프라인 (멀티턴 토큰 누적 방지)
    # ========================================================================

    async def _summarize_history_if_needed(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """히스토리가 임계값을 초과하면 Haiku로 요약

        조건: 메시지 6개 이상 AND 총 5,000자 이상
        결과: [이전 대화 요약] + 현재 메시지 (2개)로 압축
        """
        if len(messages) < SUMMARIZATION_MESSAGE_THRESHOLD:
            return messages

        total_chars = sum(
            len(msg.content) if isinstance(msg.content, str) else len(str(msg.content))
            for msg in messages
        )

        if total_chars < SUMMARIZATION_CHAR_THRESHOLD:
            return messages

        print(f"[{self.name}] History exceeds threshold: {len(messages)} messages, {total_chars:,} chars")
        print(f"[{self.name}] Summarizing with Haiku...")

        try:
            from langchain_aws import ChatBedrockConverse as _ChatBedrock

            haiku_config = get_worker_config(use_sonnet=False)
            haiku_llm = _ChatBedrock(
                model=haiku_config.model_id,
                temperature=0.3,
                max_tokens=1500,
                config=BEDROCK_CONFIG,
            )

            conversation_text = self._format_messages_for_summary(messages[:-1])
            current_message = messages[-1]

            summary_prompt = self.summarization_prompt.format(conversation=conversation_text)
            response = await haiku_llm.ainvoke([
                HumanMessage(content=summary_prompt),
            ])

            summary = response.content.strip()
            print(f"[{self.name}] Summary generated: {len(summary)} chars")

            return [
                HumanMessage(content=f"[이전 대화 요약]\n{summary}"),
                current_message,
            ]

        except Exception as e:
            print(f"[{self.name}] Summarization failed: {e}, using original messages")
            return messages

    def _format_messages_for_summary(self, messages: List[BaseMessage]) -> str:
        """메시지를 요약용 텍스트로 포맷팅 (구조화 데이터 보존)"""
        lines = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            # Assistant 메시지에 테이블이 있으면 더 큰 limit
            if role == "Assistant" and self._has_structured_data(content):
                max_len = 6000
            else:
                max_len = 2000

            if len(content) > max_len:
                content = content[:max_len] + "... [truncated]"
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    @staticmethod
    def _has_structured_data(content: str) -> bool:
        """테이블/구조화 데이터/선택지 포함 여부"""
        import re
        lines = content.split('\n')
        # 마크다운 테이블
        table_rows = sum(1 for line in lines
                         if line.strip().startswith('|') and line.strip().endswith('|'))
        if table_rows >= 3:
            return True
        # 옵션/선택지 패턴 (옵션 A, 방안 1, **안 ①** 등)
        option_patterns = sum(1 for line in lines if re.match(
            r'\s*(\*\*)?'           # optional bold
            r'(옵션|방안|안|대안|Option)\s*'
            r'[A-Z0-9①②③④⑤]',
            line.strip(), re.IGNORECASE
        ))
        if option_patterns >= 2:
            return True
        # 번호 매긴 목록 (1. / 1) / (1) 패턴이 3개 이상)
        numbered = sum(1 for line in lines if re.match(
            r'\s*(\d+[\.\)]\s|[\(（]\d+[\)）])', line.strip()
        ))
        return numbered >= 3

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: List[BaseTool],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        스트리밍 응답 생성

        Args:
            messages: 대화 메시지 리스트
            context: 요청 컨텍스트
            all_tools: MCP에서 로드된 전체 도구 리스트
            memory_context: 워크스페이스 메모리 (요약, 핵심 사실)
            user_memory_context: 사용자 전역 메모리 (key_facts만)

        Yields:
            astream_events 이벤트 딕셔너리
        """
        import time

        # Phase 0: 대화 히스토리가 길면 Haiku로 사전 요약
        if not self.skip_summarization:
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

        worker_internal_start = time.time()

        # 모델 생성 (Prompt Caching 활성화 + inference profile 폴백)
        model_start = time.time()
        config = self.get_model_config()
        region_mgr = get_region_fallback_manager()
        effective_model_id = region_mgr.get_model_id(config.model_id)
        llm_kwargs = dict(
            model=effective_model_id,
            temperature=0.7,
            max_tokens=config.max_tokens,
            disable_streaming=False,
            config=BEDROCK_CONFIG,
        )
        llm = CachedChatBedrockConverse(**llm_kwargs)
        model_time = int((time.time() - model_start) * 1000)
        print(f"[{self.name}] [TIMING] Model creation: {model_time}ms")

        # 도구 필터링
        filter_start = time.time()
        filtered_tools = self.filter_tools(all_tools)

        # 파일 존재 시 검색 도구 자동 추가 (모든 워커에서 파일 접근 가능)
        has_files = context.get("has_files", False)
        workspace_has_files = context.get("workspace_has_files", False)
        if has_files or workspace_has_files:
            _FILE_TOOLS = {"search_user_files", "search_workspace_docs"}
            existing_names = {t.name for t in filtered_tools}
            added = []
            for t in all_tools:
                if t.name in _FILE_TOOLS and t.name not in existing_names:
                    filtered_tools.append(t)
                    added.append(t.name)
            if added:
                print(f"[{self.name}] [FILE_TOOLS] 파일 검색 도구 자동 추가: {added}")

        filtered_tools = self.prepare_tools(filtered_tools, context)
        filter_time = int((time.time() - filter_start) * 1000)
        print(f"[{self.name}] Using tools: {[t.name for t in filtered_tools]}")
        print(f"[{self.name}] [TIMING] Tool filtering: {filter_time}ms")

        # 시스템 프롬프트 생성 (메모리 컨텍스트 포함)
        prompt_start = time.time()
        system_prompt = self.build_system_prompt(context, memory_context, user_memory_context)
        prompt_time = int((time.time() - prompt_start) * 1000)
        print(f"[{self.name}] [TIMING] System prompt build: {prompt_time}ms")
        if memory_context:
            print(f"[{self.name}] Workspace memory injected: {len(memory_context.get('summary', ''))} chars")
        if user_memory_context:
            print(f"[{self.name}] User memory injected: {len(user_memory_context.get('key_facts', []))} facts")

        # Agent 생성 (이전 tool result 압축 모드 지원)
        agent_start = time.time()
        if self.compact_previous_results:
            _sys_prompt = system_prompt
            _keep_n = self.compact_keep_recent_pairs
            _max_chars = COMPACT_SUMMARY_MAX_CHARS
            _worker_name = self.name

            def compact_state_modifier(state):
                compacted = _compact_tool_messages(
                    state["messages"], _keep_n, _max_chars
                )
                return [SystemMessage(content=_sys_prompt)] + compacted

            modifier = compact_state_modifier
            print(f"[{self.name}] [COMPACT] 이전 tool result 압축 모드 활성화 (keep_recent={_keep_n}, max_chars={_max_chars})")
        else:
            modifier = system_prompt

        tools_for_agent = filtered_tools if filtered_tools else []
        agent = create_react_agent(llm, tools_for_agent, state_modifier=modifier)
        agent_time = int((time.time() - agent_start) * 1000)
        print(f"[{self.name}] [TIMING] Agent creation: {agent_time}ms")

        # 디버깅: 도구 스키마 확인 (Bedrock에 올바르게 전달되는지)
        if filtered_tools:
            for t in filtered_tools:
                try:
                    schema = t.args_schema
                    if schema is None:
                        print(f"[{self.name}] [TOOL_SCHEMA] {t.name}: args_schema=None")
                    elif isinstance(schema, dict):
                        print(f"[{self.name}] [TOOL_SCHEMA] {t.name}: {schema}")
                    elif hasattr(schema, 'model_json_schema'):
                        print(f"[{self.name}] [TOOL_SCHEMA] {t.name}: {schema.model_json_schema()}")
                    else:
                        print(f"[{self.name}] [TOOL_SCHEMA] {t.name}: type={type(schema).__name__}")
                except Exception as e:
                    print(f"[{self.name}] [TOOL_SCHEMA] {t.name}: ERROR - {e}")

        # 스트리밍 실행 (throttling 시 inference profile 자동 전환)
        total_setup_time = int((time.time() - worker_internal_start) * 1000)
        print(f"[{self.name}] [TIMING] Total setup before stream: {total_setup_time}ms")
        print(f"[{self.name}] Starting stream with {config.display_name} ({effective_model_id})")

        # 타이밍 플래그
        llm_started = False
        first_token = False
        tool_started = False
        llm_call_count = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        stream_start = time.time()
        used_model_id = effective_model_id  # 실제 사용된 model ID (폴백 시 변경됨)

        try:
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
                config={"recursion_limit": self.max_agent_steps},
            ):
                event_kind = event.get("event", "")
                elapsed = int((time.time() - stream_start) * 1000)

                # LLM 호출 시작
                if event_kind == "on_chat_model_start" and not llm_started:
                    print(f"[{self.name}] [TIMING] LLM call started: {elapsed}ms")
                    llm_started = True

                # LLM 호출 완료 → tool_calls 확인 + 토큰 수집
                if event_kind == "on_chat_model_end":
                    llm_call_count += 1
                    output = event.get("data", {}).get("output", None)
                    # 토큰 사용량 수집
                    if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                        um = output.usage_metadata
                        step_in = um.get("input_tokens", 0)
                        step_out = um.get("output_tokens", 0)
                        total_input_tokens += step_in
                        total_output_tokens += step_out
                        # Prompt Caching 메트릭
                        cache_read = 0
                        cache_write = 0
                        details = um.get("input_token_details") or {}
                        if details:
                            cache_read = details.get("cache_read", 0)
                            cache_write = details.get("cache_creation", 0)
                        total_cache_read_tokens += cache_read
                        total_cache_write_tokens += cache_write
                        cache_info = f" cache_read={cache_read:,} cache_write={cache_write:,}" if (cache_read or cache_write) else ""
                        print(f"[{self.name}] [TOKEN #{llm_call_count}] in={step_in:,} out={step_out:,}{cache_info} (cumul: in={total_input_tokens:,} out={total_output_tokens:,})")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                        tc_summary = [{"name": tc.get("name"), "args_keys": list(tc.get("args", {}).keys())} for tc in output.tool_calls]
                        print(f"[{self.name}] [LLM_END #{llm_call_count}] tool_calls: {tc_summary}")
                    else:
                        # LLM이 도구를 호출하지 않은 경우 → 응답 내용 출력
                        resp_text = ""
                        if output and hasattr(output, "content"):
                            if isinstance(output.content, str):
                                resp_text = output.content[:200]
                            elif isinstance(output.content, list):
                                for item in output.content:
                                    if isinstance(item, dict) and "text" in item:
                                        resp_text += item["text"]
                                resp_text = resp_text[:200]
                        print(f"[{self.name}] [LLM_END #{llm_call_count}] NO tool_calls. Response: {resp_text}")

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

        except Exception as e:
            if not is_throttling_error(e):
                raise  # throttling이 아닌 에러는 그대로 전파

            # ── Throttling 감지 → inference profile prefix 전환 후 재시도 ──
            from app.core.region_fallback import swap_inference_prefix
            fallback_model_id = swap_inference_prefix(effective_model_id)

            if fallback_model_id == effective_model_id:
                # prefix 전환 불가 (알 수 없는 prefix) → 그대로 raise
                raise

            print(f"[{self.name}] [PROFILE_FALLBACK] Throttled on {effective_model_id}, "
                  f"retrying with {fallback_model_id}")

            # RegionFallbackManager에 폴백 상태 기록 (다음 요청부터 바로 전환)
            region_mgr.activate_fallback()

            # 폴백 모델로 LLM + Agent 재생성
            fallback_llm = CachedChatBedrockConverse(
                model=fallback_model_id,
                temperature=0.7,
                max_tokens=config.max_tokens,
                disable_streaming=False,
                config=BEDROCK_CONFIG,
            )
            agent = create_react_agent(fallback_llm, tools_for_agent, state_modifier=modifier)
            used_model_id = fallback_model_id

            # 타이밍 리셋
            llm_started = False
            first_token = False
            tool_started = False
            stream_start = time.time()

            # 재시도 스트리밍 (이번엔 실패하면 그대로 전파)
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
                config={"recursion_limit": self.max_agent_steps},
            ):
                event_kind = event.get("event", "")
                elapsed = int((time.time() - stream_start) * 1000)

                if event_kind == "on_chat_model_start" and not llm_started:
                    print(f"[{self.name}] [TIMING] LLM call started (fallback): {elapsed}ms")
                    llm_started = True

                if event_kind == "on_chat_model_end":
                    llm_call_count += 1
                    output = event.get("data", {}).get("output", None)
                    if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                        um = output.usage_metadata
                        step_in = um.get("input_tokens", 0)
                        step_out = um.get("output_tokens", 0)
                        total_input_tokens += step_in
                        total_output_tokens += step_out
                        details = um.get("input_token_details") or {}
                        cache_read = details.get("cache_read", 0) if details else 0
                        cache_write = details.get("cache_creation", 0) if details else 0
                        total_cache_read_tokens += cache_read
                        total_cache_write_tokens += cache_write
                        cache_info = f" cache_read={cache_read:,} cache_write={cache_write:,}" if (cache_read or cache_write) else ""
                        print(f"[{self.name}] [TOKEN #{llm_call_count}] in={step_in:,} out={step_out:,}{cache_info} (fallback)")

                if event_kind == "on_chat_model_stream" and not first_token:
                    print(f"[{self.name}] [TIMING] First LLM token (fallback): {elapsed}ms")
                    first_token = True

                if event_kind == "on_tool_start" and not tool_started:
                    tool_name = event.get("name", "unknown")
                    print(f"[{self.name}] [TIMING] Tool '{tool_name}' started (fallback): {elapsed}ms")
                    tool_started = True

                yield event

        # 스트리밍 완료 후 토큰 사용량 이벤트 전달
        if total_input_tokens > 0 or total_output_tokens > 0:
            cache_summary = ""
            if total_cache_read_tokens or total_cache_write_tokens:
                cache_summary = f" cache_read={total_cache_read_tokens:,} cache_write={total_cache_write_tokens:,}"
            print(f"[{self.name}] [TOKEN_TOTAL] input={total_input_tokens:,} output={total_output_tokens:,}{cache_summary} llm_calls={llm_call_count}")
            yield {
                "event": "token_usage",
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cache_read_tokens": total_cache_read_tokens,
                "cache_write_tokens": total_cache_write_tokens,
                "llm_call_count": llm_call_count,
            }

            # token_usage_log 테이블에 기록
            try:
                from app.services.token_usage_service import get_token_usage_service
                import asyncio
                asyncio.create_task(get_token_usage_service().log(
                    caller=self.name,
                    model_id=used_model_id,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cache_read_tokens=total_cache_read_tokens,
                    cache_write_tokens=total_cache_write_tokens,
                    session_id=context.get("session_id") if context else None,
                    user_id=context.get("user_id") if context else None,
                ))
            except Exception:
                pass

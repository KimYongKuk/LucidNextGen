"""VisualizationWorker - PDF 생성 및 시각화 담당 Worker"""

import time
from typing import List, Dict, Any, AsyncIterator, Optional

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import BaseTool

from .base_worker import BaseWorker
from app.core.model_config import get_worker_config


# ============================================================================
# Haiku 요약 파이프라인 설정
# ============================================================================
SUMMARIZATION_MESSAGE_THRESHOLD = 6  # 최소 메시지 개수
SUMMARIZATION_CHAR_THRESHOLD = 5000  # 최소 문자 수

SUMMARIZATION_PROMPT = """다음 대화 내용을 PDF 문서 생성을 위해 요약해줘.

## 요약 지침
1. 핵심 데이터, 숫자, 통계는 정확히 보존
2. 주요 주제와 결론 포함
3. 테이블 데이터가 있으면 구조 유지
4. 사용자의 최종 요청 명확히 기록
5. 마크다운 형식으로 정리
6. 최대 800단어

## ⚠️ 중요 - 도구 호출 정보 반드시 보존:
- 차트 생성 여부와 차트 데이터(월별 매출 등)를 명시
- 차트가 display 모드로만 생성되었다면 "차트: display 모드 (파일 미저장)" 표기
- PDF 생성 요청이 있었다면 "PDF 생성 필요" 표기
- 이전에 생성된 PDF 파일명이 있다면 기록

## 대화 내용:
{conversation}

---
## 요약:"""


class VisualizationWorker(BaseWorker):
    """
    시각화/문서 생성 Worker (Sonnet)

    담당 도구:
    PDF 도구:
    - create_document_pdf: 마크다운/텍스트를 PDF로 변환
    - create_table_spec_pdf: 테이블 정의서 전용 PDF 생성
    - list_generated_pdfs: 생성된 PDF 목록 조회

    차트 도구:
    - create_line_chart: 라인/트렌드 차트 생성
    - create_bar_chart: 막대 차트 생성
    - create_pie_chart: 파이 차트 생성
    - create_multi_chart: 복합 차트 생성 (막대+라인, 누적, 영역)

    용도:
    - 이전 대화 내용을 PDF로 변환
    - 보고서, 문서 생성
    - 데이터 시각화 (차트, 그래프)

    Sonnet 사용 이유: 문서 구조화, 포맷팅 품질 향상
    """

    @property
    def name(self) -> str:
        return "VisualizationWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            # 파일 검색 도구 (데이터 접근용)
            "search_user_files",
            "search_workspace_docs",
            # PDF 도구
            "create_document_pdf",
            "create_table_spec_pdf",
            "list_generated_pdfs",
            # 차트 도구
            "create_line_chart",
            "create_bar_chart",
            "create_pie_chart",
            "create_multi_chart",
        ]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (문서 품질 향상)"""
        return True

    @property
    def system_prompt(self) -> str:
        return self._base_prompt

    @property
    def _base_prompt(self) -> str:
        return """You are a document designer and data visualization expert.

ROLE:
1. Transform conversations into well-structured PDF documents
2. Create data visualizations (charts/graphs)

TOOLS:
- PDF: create_document_pdf, create_table_spec_pdf, list_generated_pdfs
- Charts: create_line_chart (trends), create_bar_chart (comparison), create_pie_chart (ratios), create_multi_chart (combo/stacked/area)
- File Search: search_user_files(session_id="{session_id}"), search_workspace_docs(workspace_uuid="{workspace_uuid}")

CHART SELECTION:
- 시간 추이 → line | 카테고리 비교 → bar | 비율/점유율 → pie | 복합 지표 → multi(combo)

═══════════════════════════════════════════════════════════════
🚨 MUST-DO RULES (절대 규칙) - 위반 시 파일 생성 안 됨!
═══════════════════════════════════════════════════════════════

1. ⚠️ PDF/차트 수정 요청 = 도구 재호출 필수 (가장 중요!)
   - "수정해줘", "더 자세히", "내용 추가해줘", "차트 포함해줘"
     → 반드시 create_document_pdf 또는 차트 도구를 다시 호출해야 함
   - 텍스트로만 "수정 완료" / "파일명: xxx.pdf"라고 하면 안 됨!
   - 실제 도구를 호출하지 않으면 파일이 생성되지 않음!
   - 이전 대화 요약을 보고 있더라도, 수정 요청이면 무조건 도구 재호출!

2. ⚠️ 차트를 PDF에 포함할 때 (필수 2단계)
   Step 1: 차트를 output_mode="file"로 재생성 → file_path 받음
           (이전에 display 모드로 차트를 만들었어도 file로 다시 생성해야 함!)
   Step 2: PDF content에 ![제목](받은_file_path를_슬래시로_변환) 포함

   ※ 화면에 표시된 차트(display 모드)는 파일로 저장되지 않음
   ※ "아까 만든 차트"가 있어도 PDF용으로는 file 모드로 재생성 필수!

3. 차트 생성 시 JSON 노출 금지
   데이터 배열, config 등 기술적 내용을 응답에 포함하지 말 것
   Bad: "다음 데이터로 차트를 생성합니다: [{...}]"
   Good: "분기별 매출 추이를 차트로 보여드릴게요."

4. PDF 생성 후 파일명 형식
   반드시 포함: "파일명: {실제파일명}.pdf"

═══════════════════════════════════════════════════════════════

PDF WORKFLOW:
1. 사용자에게 먼저 짧게 응답 ("PDF 문서를 작성하겠습니다.")
2. 이전 대화 내용 검토 및 재구성
3. create_document_pdf 호출
4. 완료 후: "확인해보시고 수정할 부분 있으면 말씀해주세요."

DOCUMENT STRUCTURE EXAMPLE:
```
## 개요
2-3문장 요약

---

## 1. 주요 내용
### 1-1. 세부 항목
- 내용...

| 구분 | 설명 |
|------|------|
| A    | B    |

---

## 결론
핵심 요약
```

FORMATTING:
- ##/### 섹션 구분 (# 는 제목 전용, 자동 추가됨)
- 비교 데이터 → 테이블 | 나열 항목 → 불릿(-) | 코드 → ```
- **bold**, *italic* 사용 금지 (PDF 렌더러가 처리)
- 대화체 제거 ("음...", "글쎄요" 등)
- 내용을 재구성하고 개선할 것 (단순 복사 금지)

STYLE OPTIONS:
- technical: 기술 문서 (파란 헤더, 코드 블록)
- report: 비즈니스 보고서 (깔끔한 회색톤)
- simple: 간단한 메모

SECTION PER PAGE:
"섹션별로 나눠줘" 요청 시 → section_per_page=true 옵션 사용

FILE DATA ACCESS:
사용자가 "이 데이터", "파일" 등 언급 시 → search_user_files 또는 search_workspace_docs 먼저 호출

Answer in Korean unless asked otherwise."""

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
        """
        prompt = self._base_prompt

        # 세션 ID 주입
        session_id = context.get("session_id", "")
        if session_id:
            prompt = prompt.replace("{session_id}", session_id)
        else:
            prompt = prompt.replace("{session_id}", "NOT_AVAILABLE")

        # 워크스페이스 UUID 주입
        workspace_uuid = context.get("workspace_uuid", "")
        if workspace_uuid:
            prompt = prompt.replace("{workspace_uuid}", workspace_uuid)
        else:
            prompt = prompt.replace("{workspace_uuid}", "NOT_AVAILABLE")

        # 파일 컨텍스트 안내 추가 (중요!)
        has_files = context.get("has_files", False)
        workspace_has_files = context.get("workspace_has_files", False)

        file_context_notice = ""
        if has_files and session_id:
            file_context_notice = f"""
IMPORTANT - FILE CONTEXT:
User has uploaded files in this session. When user mentions "이 데이터", "데이터", "이걸", "파일" or similar vague references,
you MUST call search_user_files(session_id="{session_id}", query="...") FIRST to retrieve the data before creating any chart.
Do NOT ask user for data - search the files directly!
"""
        elif workspace_uuid and workspace_has_files:
            file_context_notice = f"""
IMPORTANT - WORKSPACE CONTEXT:
User is in a workspace with documents. When user mentions "이 데이터", "데이터", "이걸", "문서" or similar vague references,
you MUST call search_workspace_docs(workspace_uuid="{workspace_uuid}", query="...") FIRST to retrieve the data before creating any chart.
Do NOT ask user for data - search the documents directly!
"""

        if file_context_notice:
            prompt = file_context_notice + "\n" + prompt

        # 워크스페이스 instructions 주입 (맨 앞에 추가)
        workspace_instructions = context.get("workspace_instructions")
        if workspace_instructions:
            prompt = f"WORKSPACE INSTRUCTIONS:\n{workspace_instructions}\n\n{prompt}"

        # 날짜 정보는 BaseWorker.build_system_prompt에서 추가되지만,
        # 여기서 오버라이드하므로 직접 추가
        from datetime import datetime
        now = datetime.now()
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        weekday_kr = weekdays[now.weekday()]
        current_date = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
        prompt = f"Today is {current_date}.\n\n{prompt}"

        # 전역 사용자 메모리 주입
        if user_memory_context and user_memory_context.get("key_facts"):
            facts = user_memory_context["key_facts"]
            facts_text = "\n".join(f"  - {fact}" for fact in facts)
            prompt = f"## User Profile (사용자 개인 특성)\n\n이 사용자에 대해 알려진 정보:\n{facts_text}\n\n{prompt}"

        print(f"[VisualizationWorker] Context: session_id={bool(session_id)}, workspace_uuid={bool(workspace_uuid)}, has_files={has_files}")

        return prompt

    # ========================================================================
    # Haiku 요약 파이프라인
    # ========================================================================

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: List[BaseTool],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Haiku 사전 요약을 포함한 스트리밍 응답 생성

        긴 히스토리는 Haiku로 먼저 요약하여 Sonnet의 처리 시간을 단축
        """
        # Phase 0: 히스토리가 길면 Haiku로 사전 요약
        summarize_start = time.time()
        processed_messages = await self._summarize_history_if_needed(messages)

        if len(processed_messages) < len(messages):
            summarize_time = int((time.time() - summarize_start) * 1000)
            print(f"[{self.name}] [TIMING] Haiku summarization: {summarize_time}ms")
            print(f"[{self.name}] Messages reduced: {len(messages)} -> {len(processed_messages)}")

            # 요약 완료 이벤트 전송 (UI 피드백용)
            yield {
                "event": "summarization_complete",
                "original_count": len(messages),
                "summarized_count": len(processed_messages),
                "timing_ms": summarize_time,
            }

        # 부모 클래스의 stream_response 호출 (요약된 메시지 사용, 메모리 컨텍스트 전달)
        async for event in super().stream_response(processed_messages, context, all_tools, memory_context, user_memory_context):
            yield event

    async def _summarize_history_if_needed(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """
        히스토리가 임계값을 초과하면 Haiku로 요약

        Args:
            messages: 원본 메시지 리스트

        Returns:
            원본 메시지 (임계값 미만) 또는 요약된 메시지
        """
        # 메시지 개수 체크
        if len(messages) < SUMMARIZATION_MESSAGE_THRESHOLD:
            return messages

        # 총 문자 수 체크
        total_chars = sum(
            len(msg.content) if isinstance(msg.content, str) else len(str(msg.content))
            for msg in messages
        )

        if total_chars < SUMMARIZATION_CHAR_THRESHOLD:
            return messages

        print(f"[{self.name}] History exceeds threshold: {len(messages)} messages, {total_chars} chars")
        print(f"[{self.name}] Summarizing with Haiku...")

        try:
            # Haiku LLM 생성
            from .base_worker import BEDROCK_CONFIG
            haiku_config = get_worker_config(use_sonnet=False)  # Haiku
            haiku_llm = ChatBedrockConverse(
                model=haiku_config.model_id,
                temperature=0.3,
                max_tokens=1500,
                config=BEDROCK_CONFIG,
            )

            # 대화 텍스트 구성 (마지막 메시지 제외 - 현재 요청)
            conversation_text = self._format_messages_for_summary(messages[:-1])
            current_message = messages[-1]

            # 요약 요청
            summary_prompt = SUMMARIZATION_PROMPT.format(conversation=conversation_text)
            response = await haiku_llm.ainvoke([
                HumanMessage(content=summary_prompt),
            ])

            summary = response.content.strip()
            print(f"[{self.name}] Summary generated: {len(summary)} chars")

            # 요약 + 현재 요청으로 메시지 재구성
            return [
                HumanMessage(content=f"[이전 대화 요약]\n{summary}"),
                current_message,
            ]

        except Exception as e:
            print(f"[{self.name}] Summarization failed: {e}, using original messages")
            return messages

    def _format_messages_for_summary(self, messages: List[BaseMessage]) -> str:
        """메시지를 요약용 텍스트로 포맷팅"""
        lines = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            # 너무 긴 메시지는 잘라냄
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"

            lines.append(f"{role}: {content}")

        return "\n\n".join(lines)

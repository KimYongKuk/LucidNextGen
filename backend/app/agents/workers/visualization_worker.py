"""VisualizationWorker - PDF 생성 및 시각화 담당 Worker"""

import time
from typing import List, Dict, Any, AsyncIterator

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
        return """You are a professional document designer, PDF generation specialist, and data visualization expert.

Your role is to:
1. Transform conversation content into beautifully formatted PDF documents
2. Create insightful data visualizations (charts and graphs)

DATA ACCESS (for file-based visualization):
When user asks to visualize data from uploaded files:
1. First call search_user_files or search_workspace_docs to retrieve the data
2. Extract numerical values from the search results
3. Then create the appropriate chart with the extracted data

File Search Tools:
- search_user_files(session_id="{session_id}", query="..."): Search user's uploaded files
- search_workspace_docs(workspace_uuid="{workspace_uuid}", query="..."): Search workspace documents

Example workflow:
User: "업로드한 파일 데이터로 매출 차트 그려줘"
1. Call search_user_files to find sales data
2. Extract data: Q1=100억, Q2=150억, Q3=200억
3. Call create_bar_chart with the extracted data

AVAILABLE TOOLS:

PDF Tools:
- create_document_pdf: Convert markdown/text to PDF with styling options (technical, report, simple)
- create_table_spec_pdf: Create database table specification PDF (auto-formats DDL, constraints, etc.)
- list_generated_pdfs: List all generated PDF files

Chart Tools:
- create_line_chart: Create line/trend charts (time series, trends)
- create_bar_chart: Create bar charts (category comparison)
- create_pie_chart: Create pie charts (proportions, distributions)
- create_multi_chart: Create combo charts (bar+line, stacked, area)

CHART SELECTION GUIDE:
- Time-based trends (월별 추이, 연도별 변화) → create_line_chart
- Category comparison (부서별, 제품별 비교) → create_bar_chart
- Proportions/ratios (점유율, 비율 분포) → create_pie_chart
- Multi-metric analysis (매출+성장률) → create_multi_chart (type: combo)
- Cumulative data (누적 데이터) → create_multi_chart (type: stacked_bar)

CRITICAL - CHART + PDF WORKFLOW:
When user asks to create PDF with charts (e.g., "차트 포함해서 PDF로", "이 차트를 PDF에 넣어줘", "PDF로 만들어줘" after showing a chart):

IMPORTANT: Charts displayed on screen (display mode) are NOT saved as files!
You MUST RE-CREATE the chart with output_mode="file" to include it in PDF.

STEP-BY-STEP WORKFLOW:
1. Look at the conversation history to find the chart data that was previously used
2. RE-CREATE the chart with output_mode="file" and a unique filename
   - Extract the SAME data from the previous chart tool call in history
   - Call create_line_chart/bar_chart/pie_chart with output_mode="file", filename="chart_for_pdf"
   - The tool returns: {"file_path": "C:\\...\\chart_output\\chart_for_pdf.png", ...}
3. THEN create PDF using the FULL ABSOLUTE PATH from the tool response:
   - Use the exact file_path returned by the chart tool
   - Include: ![차트 제목](C:/Users/Administrator/Documents/LFChatbot_NextJS_FastAPI/backend/data/chart_output/chart_for_pdf.png)

CRITICAL - USE ABSOLUTE PATH:
When the chart tool returns file_path like "C:\\Users\\...\\chart_for_pdf.png",
you MUST use that FULL PATH (with forward slashes) in the markdown image syntax!
- Tool returns: "file_path": "C:\\Users\\Administrator\\...\\monthly_chart.png"
- Use in PDF: ![제목](C:/Users/Administrator/.../monthly_chart.png)

EXAMPLE - User previously created a chart, now wants PDF:
History shows: create_bar_chart was called with data=[{"month": "1월", "sales": 100}, ...]
User says: "이걸 PDF로 만들어줘"

Your actions:
1. FIRST call create_bar_chart again with:
   - SAME data from history
   - output_mode="file"
   - filename="monthly_sales_chart"
   - Tool returns: {"file_path": "C:\\Users\\Administrator\\Documents\\LFChatbot_NextJS_FastAPI\\backend\\data\\chart_output\\monthly_sales_chart.png"}
2. THEN call create_document_pdf with content using the ABSOLUTE PATH:
   ```
   ## 매출 분석 보고서

   ### 차트
   ![월별 매출 현황](C:/Users/Administrator/Documents/LFChatbot_NextJS_FastAPI/backend/data/chart_output/monthly_sales_chart.png)

   ### 분석 결과
   ...
   ```

CRITICAL RULES:
- NEVER skip step 1 (re-creating chart with file mode)
- ALWAYS use the FULL ABSOLUTE PATH returned by the chart tool
- Convert backslashes (\\) to forward slashes (/) in the path
- The chart file MUST exist before PDF creation

DATA FORMAT FOR CHARTS:
All chart tools accept data as JSON array. Extract numbers from conversation and format:
- "Q1: 100억, Q2: 150억, Q3: 200억" → [{"quarter": "Q1", "value": 100}, {"quarter": "Q2", "value": 150}, ...]
- "영업 50명, 개발 80명" → [{"dept": "영업", "count": 50}, {"dept": "개발", "count": 80}]

CRITICAL RULES FOR CHART TOOLS:
1. NEVER output JSON data or tool parameters as text to the user
2. NEVER show the data array, config, or any technical details in your response
3. Only provide a brief confirmation AFTER the chart is created
4. The chart will be displayed automatically in the UI - do not describe the data

Example for charts:
User: "Q1: 100억, Q2: 150억, Q3: 200억 라인 차트로 보여줘"
Your response: "네, 분기별 매출 추이를 라인 차트로 생성해드리겠습니다!"
Then call create_line_chart with the data (DO NOT output the JSON in your message).
After tool completes, briefly describe the trend: "분기별로 꾸준히 성장하는 추세를 보이고 있네요!"

CRITICAL - FOR PDF TOOLS, ALWAYS RESPOND TO USER FIRST:
Before calling PDF tools, send a brief message to the user explaining what you're about to do.

Example for PDF:
User: "이걸 PDF로 만들어줘"
Your response: "네, 말씀하신 내용을 바탕으로 PDF 문서를 작성하겠습니다. 잠시만 기다려주세요."
Then call the tool.

WORKFLOW:
1. When user says "이걸 PDF로 만들어줘" or similar:
   - FIRST: Respond to user with a brief acknowledgment (1-2 sentences)
   - Carefully review the previous conversation (message history)
   - Extract and reorganize the relevant content
   - Structure it professionally before calling the tool

2. For table specifications:
   - Use create_table_spec_pdf
   - Include version number if provided

3. Style selection guide:
   - technical: For technical docs, API specs, table definitions (blue headers, code blocks)
   - report: For business reports, formal documents (clean, professional)
   - simple: For memos, quick notes (minimal styling)

DOCUMENT STRUCTURE (MUST FOLLOW):
1. Title: Create a clear, descriptive title (DO NOT include # - it will be added automatically)
2. Summary Box: Start with a brief overview (2-3 sentences) highlighting key points
3. Main Sections: Use ## for major sections, ### for subsections
4. Conclusion: End with key takeaways or action items

FORMATTING RULES:
- Headings: Use ## and ### for sections (# is reserved for title)
- Tables: Use for any comparative data, lists with multiple attributes, or structured information
  | 항목 | 설명 |
  |------|------|
  | A    | B    |
- Lists: Use bullet points (-) for 3+ related items
- Code: Use ```language for any code, SQL, or commands
- Horizontal rules: Use --- between major sections for visual separation
- Paragraphs: Keep concise (3-5 sentences max per paragraph)
- NO markdown formatting like **bold** or *italic* in regular text (PDF renderer handles styling)

CONTENT TRANSFORMATION:
- Don't just copy-paste: Reorganize and improve the structure
- Add section headers where the original had none
- Convert long paragraphs into bullet points when appropriate
- Group related information together
- Remove conversational elements ("음...", "글쎄요", etc.)
- Ensure logical flow from introduction to conclusion

EXAMPLE STRUCTURE:
```
# [Title - provided separately]

## 개요
Brief summary of the document content...

---

## 1. 주요 내용
### 1-1. 첫 번째 항목
Content here...

### 1-2. 두 번째 항목
| 구분 | 내용 | 비고 |
|------|------|------|
| A | Description | Note |

---

## 2. 세부 사항
...

---

## 결론
Key takeaways and summary...
```

OUTPUT:
- Always confirm the PDF was created
- Provide the file path
- Mention the style used

POST-PDF CREATION GUIDANCE:
After successfully creating a PDF, ALWAYS end your response with this offer:
"확인해보시고 마음에 안 드는 부분이 있다면 말씀해주세요. 섹션별로 페이지를 나눠서 다시 생성해드릴 수도 있어요."

If user requests section-separated pages (e.g., "섹션별로 나눠줘", "페이지 구분해줘"):
- Re-create the PDF with section_per_page=true option
- This will place each ## section on a new page with the header at the top

Answer in Korean unless asked otherwise."""

    def build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        컨텍스트를 반영한 시스템 프롬프트 생성

        Args:
            context: 세션, 워크스페이스 등 컨텍스트 정보
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

        # 부모 클래스의 stream_response 호출 (요약된 메시지 사용)
        async for event in super().stream_response(processed_messages, context, all_tools):
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
            haiku_config = get_worker_config(use_sonnet=False)  # Haiku
            haiku_llm = ChatBedrockConverse(
                model=haiku_config.model_id,
                temperature=0.3,
                max_tokens=1500,
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

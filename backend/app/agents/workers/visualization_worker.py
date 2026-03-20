"""VisualizationWorker - PDF/DOCX 생성 및 시각화 담당 Worker"""

from typing import List, Dict, Any, Optional

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from .base_worker import BaseWorker


class VisualizationWorker(BaseWorker):
    """
    시각화/문서 생성 Worker (Sonnet)

    담당 도구:
    PDF 도구:
    - create_document_pdf: 마크다운/텍스트를 PDF로 변환
    - create_table_spec_pdf: 테이블 정의서 전용 PDF 생성
    - list_generated_pdfs: 생성된 PDF 목록 조회

    DOCX 도구:
    - create_document_docx: 마크다운/텍스트를 Word(DOCX)로 변환 (편집 가능)

    차트 도구:
    - create_line_chart: 라인/트렌드 차트 생성
    - create_bar_chart: 막대 차트 생성
    - create_pie_chart: 파이 차트 생성
    - create_multi_chart: 복합 차트 생성 (막대+라인, 누적, 영역)

    SVG 시각화 도구:
    - create_svg_visual: SVG 인포그래픽/다이어그램 생성 (플로우차트, 타임라인, 비교, 대시보드)

    용도:
    - 이전 대화 내용을 PDF/Word 문서로 변환
    - 보고서, 문서 생성
    - 데이터 시각화 (차트, 그래프)
    - 인포그래픽, 플로우차트, 다이어그램

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
            # DOCX 도구
            "create_document_docx",
            # 차트 도구
            "create_line_chart",
            "create_bar_chart",
            "create_pie_chart",
            "create_multi_chart",
            # SVG 시각화 도구
            "create_svg_visual",
            # 웹 검색 도구 (시장 현황, 트렌드 등 최신 정보 필요 시)
            "tavily_search",
        ]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (문서 품질 향상)"""
        return True

    @property
    def summarization_prompt(self) -> str:
        return """다음 대화 내용을 PDF/Word 문서 생성을 위해 요약해줘.

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

    @property
    def system_prompt(self) -> str:
        return self._base_prompt

    @property
    def _base_prompt(self) -> str:
        return """You are a document designer and data visualization expert.

ROLE:
1. Transform conversations into well-structured PDF or Word(DOCX) documents
2. Create data visualizations (charts/graphs)

TOOLS:
- PDF: create_document_pdf, create_table_spec_pdf, list_generated_pdfs
- DOCX: create_document_docx (편집 가능한 Word 문서)
- Charts: create_line_chart (trends), create_bar_chart (comparison), create_pie_chart (ratios), create_multi_chart (combo/stacked/area)
- SVG Visual: create_svg_visual (infographic, flowchart, timeline, comparison, diagram, dashboard, process)
- File Search: search_user_files(session_id="{session_id}"), search_workspace_docs(workspace_uuid="{workspace_uuid}")
- Web Search: tavily_search (최신 정보 조사용)

FORMAT SELECTION:
- 사용자가 "워드", "Word", "DOCX", "docx", "편집 가능한 문서" 요청 → create_document_docx
- 사용자가 "PDF", "pdf" 요청 → create_document_pdf
- 사용자가 "문서로 만들어줘", "보고서 정리해줘" 등 포맷 미지정 → create_document_pdf (기본값)
- 사용자가 "수정 가능하게" 또는 "편집할 수 있게" 요청 → create_document_docx

VISUALIZATION SELECTION (3가지 도구):
1. Charts (create_line/bar/pie/multi_chart) → 정량 데이터 (숫자, 추이, 비교)
   - 시간 추이 → line | 카테고리 비교 → bar | 비율/점유율 → pie | 복합 지표 → multi(combo)
2. Mermaid (마크다운 ```mermaid 코드 블록) → 구조화된 다이어그램
   - 플로우차트, 시퀀스 다이어그램, 간트 차트, ER 다이어그램, 상태 다이어그램
   - 텍스트 기반이라 안정적이고, 자동으로 레이아웃/스타일링됨
   - 예: ```mermaid\nflowchart TD\n  A[시작] --> B{조건}\n  B -->|예| C[처리]\n  B -->|아니오| D[종료]\n```
3. SVG Visual (create_svg_visual) → 자유도 높은 커스텀 시각화
   - 인포그래픽, KPI 대시보드, 비교 시각화, 타임라인
   - Mermaid로 표현하기 어려운 커스텀 레이아웃이 필요할 때만 사용

SELECTION PRIORITY: Charts > Mermaid > SVG (단순한 도구를 우선 사용)

SVG VISUAL GUIDELINES:
- ViewBox: 800x600 (landscape) or 600x800 (portrait)
- Font: 'Malgun Gothic', 'Noto Sans KR', sans-serif (Korean support)
- Colors: professional palette — primary #4A90D9, accent #50C878, warm #FF6B6B, bg #F8FAFC
- Design: rounded corners (rx="8"), clean spacing, clear typography hierarchy
- Title: 22-24px bold, Body: 14-16px, Caption: 11-12px
- Use: rect, circle, path, text, line, polygon — NO external images/fonts
- Include inline CSS <style> within <defs> for reusable classes
- All text must be directly in <text> elements (no foreignObject)

═══════════════════════════════════════════════════════════════
🚨 MUST-DO RULES (절대 규칙) - 위반 시 파일 생성 안 됨!
═══════════════════════════════════════════════════════════════

1. ⚠️ PDF/DOCX/차트 수정 요청 = 도구 재호출 필수 (가장 중요!)
   - "수정해줘", "더 자세히", "내용 추가해줘", "차트 포함해줘"
     → 반드시 create_document_pdf / create_document_docx 또는 차트 도구를 다시 호출해야 함
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

4. PDF/DOCX 생성 후 파일명 형식
   반드시 포함: "파일명: {실제파일명}.pdf" 또는 "파일명: {실제파일명}.docx"

═══════════════════════════════════════════════════════════════

PDF WORKFLOW:
1. 사용자에게 먼저 짧게 응답 ("PDF 문서를 작성하겠습니다.")
2. **최신 정보가 필요한 주제인지 판단** → 해당되면 tavily_search로 먼저 조사!
   (시장 현황/동향, 트렌드, 산업 분석, 통계 등 → 검색 후 결과를 PDF에 반영)
3. 이전 대화 내용 검토 및 재구성
4. create_document_pdf 호출
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

    # VisualizationWorker는 BaseWorker의 stream_response()를 그대로 사용
    # - Haiku 대화 요약: BaseWorker 기본 (summarization_prompt 오버라이드로 문서 생성 특화)
    # - ReAct loop 압축: 기본값 False (도구 호출이 적어 누적 문제 적음)

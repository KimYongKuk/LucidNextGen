"""PPTWorker - 사내 템플릿 기반 PPT 생성 담당 Worker"""

from typing import List, Dict, Any, AsyncIterator, Optional

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from .base_worker import BaseWorker


class PPTWorker(BaseWorker):
    """
    PPT 프레젠테이션 생성 Worker (Sonnet)

    담당 도구:
    PPT 도구:
    - create_presentation: 사내 템플릿 기반 PPT 생성
    - list_ppt_templates: 레이아웃 메타데이터 조회
    - list_generated_ppts: 생성된 PPT 목록

    차트 도구 (PPT 내 이미지 차트용):
    - create_line_chart, create_bar_chart, create_pie_chart, create_multi_chart

    파일 검색 도구:
    - search_user_files, search_workspace_docs

    Sonnet 사용 이유: 복잡한 슬라이드 구조 설계, 콘텐츠 품질 향상
    """

    @property
    def name(self) -> str:
        return "PPTWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            # PPT 도구
            "create_presentation",
            "list_ppt_templates",
            "list_generated_ppts",
            # 차트 도구 (이미지 차트 생성용)
            "create_line_chart",
            "create_bar_chart",
            "create_pie_chart",
            "create_multi_chart",
            # 파일 검색 도구
            "search_user_files",
            "search_workspace_docs",
            # 웹 검색 도구 (시장 현황, 트렌드 등 최신 정보 필요 시)
            "tavily_search",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def compact_previous_results(self) -> bool:
        """이전 단계 Tool 결과 압축 활성화 (다단계 도구 호출 토큰 누적 방지)"""
        return True

    @property
    def summarization_prompt(self) -> str:
        return """다음 대화 내용을 PPT 프레젠테이션 생성을 위해 요약해줘.

## 요약 지침
1. 핵심 데이터, 숫자, 통계는 정확히 보존
2. 주요 주제와 결론 포함
3. 테이블 데이터가 있으면 구조 유지
4. 사용자의 최종 요청 명확히 기록
5. 마크다운 형식으로 정리
6. 최대 800단어

## ⚠️ 중요 - PPT 관련 정보 보존:
- 사용자가 요청한 PPT 주제, 구성, 슬라이드 수
- 포함할 데이터 (표, 차트, 텍스트 등)
- 이전에 생성된 PPT 파일명이 있다면 기록
- 수정 요청 사항

## 대화 내용:
{conversation}

---
## 요약:"""

    @property
    def system_prompt(self) -> str:
        return self._base_prompt

    @property
    def _base_prompt(self) -> str:
        return """You are a corporate PPT presentation expert using company templates.

ROLE: 사내 .pptx 템플릿 기반 PPT 초안 생성 전문가.
사용자의 요청에 맞는 프레젠테이션을 자율적으로 구성하되, 템플릿의 디자인(색상, 폰트, 배경)을 상속합니다.

## 사용 가능한 템플릿 레이아웃
{template_metadata}

## TOOLS
- PPT: create_presentation (핵심), list_ppt_templates (메타데이터 조회), list_generated_ppts
- Charts (이미지용): create_line_chart, create_bar_chart, create_pie_chart, create_multi_chart
- File Search: search_user_files(session_id="{session_id}"), search_workspace_docs(workspace_uuid="{workspace_uuid}")
- Web Search: tavily_search (최신 정보 조사용)

## 워크플로우
1. 사용자 요청 분석 (주제, 구성, 슬라이드 수 파악)
2. **최신 정보가 필요한 주제인지 판단** → 해당되면 tavily_search로 먼저 조사!
   - 해당 주제: 시장 현황/동향, 트렌드, 산업 분석, 기술 전망, 경쟁사 분석, 통계/수치 데이터 등
   - 검색 팁: 핵심 키워드 2~3개로 검색. 필요시 여러 번 검색하여 데이터 수집
   - 검색 결과의 구체적 수치, 통계, 최신 사례를 PPT에 반영
3. 파일/데이터 참조가 필요하면 → search_user_files / search_workspace_docs 호출
5. 슬라이드 구성 설계:
   - 표지 (layout_index=0): 제목, 날짜, 작성자
   - 목차 (layout_index=1): items 배열 필수! 예: items: ["Ⅰ. 개요", "Ⅱ. 현황"] 또는 items: [{"major": "Ⅰ. 개요", "minor": ["배경", "목적"]}]
   - 간지 (layout_index=2): 섹션 구분 (대분류 3개 이상일 때)
   - 내용 (layout_index=3): 메인 콘텐츠 (텍스트, 테이블, 차트)
   - E.O.D (layout_index=4): 끝 페이지
6. create_presentation 호출
7. "파일명: {실제파일명}.pptx" 안내

## 내용 슬라이드 (layout_index=3) 구성
헤더 요소 (선택):
- doc_title: 좌측 상단 문서명 (7pt, 표지 제목과 동일)
- breadcrumb: 목차 경로 (9pt, Orange, 예: "Ⅱ. 현황 분석")
- title: 슬라이드 메인 제목 (25pt, Bold)
- subtitle: 부제 (15pt)

본문 구조 요소:
- section_title: 섹션 구분 제목 (12pt, Bold, Orange) — 본문 영역 내에서 textbox로 배치
  예: {type: "textbox", text: "■ 현황 분석", font_size: 12, bold: true, color: "accent2_orange"}

shapes 배열 (본문 영역 L=0.37, T=1.15, W=12.6, H=5.95):
- textbox: {type, left, top, width, height, text, font_size, bold, color, alignment}
- table: {type, left, top, width, height, table: {headers, rows, header_rows, col_widths, body_merges, alt_row_fill}}
- chart: {type, left, top, width, height, chart: {chart_type, categories, series, title}}
  차트 타입: line, column, bar, pie, area, scatter, doughnut 등
- image: {type, left, top, width, height, path}

## 테이블 스타일
- 헤더: 다크 네이비(182F54) 배경 + 흰색 텍스트 + Bold
- 본문: 교대행 배경(E7EAEE)
- 병합 헤더: header_rows로 정의 (colspan/rowspan 지원)

## ⚠️ 테이블 크기 규칙 (필수!)
- 테이블 width는 반드시 12.0~12.6 사용 (절대 작게 하지 말 것!)
- col_widths는 **비율(weight)**로 지정 (절대값 아님!)
  예: 2열 [항목, 내용] → col_widths: [1, 3] (1:3 비율)
  예: 3열 [구분, A, B] → col_widths: [1, 2, 2] (1:2:2 비율)
  예: 4열 균등 → col_widths: [1, 1, 1, 1]
- col_widths 생략 시 균등 분배됨
- 텍스트가 긴 열은 큰 비율 부여 (내용 열 > 라벨 열)

## 네이티브 차트 (편집 가능)
chart 필드를 사용하면 PPT 내에서 데이터 편집 가능한 차트가 생성됩니다.
복합 차트(콤보, 이중 Y축)는 지원되지 않으므로 → matplotlib 이미지로 대체:
  1. create_*_chart(output_mode="file") 호출 → file_path 받기
  2. shapes에 {type: "image", path: "받은_파일명"} 추가

═══════════════════════════════════════════════════════════════
🚨 MUST-DO RULES (절대 규칙)
═══════════════════════════════════════════════════════════════

1. PPT 생성/수정 = 반드시 create_presentation 도구 호출!
   텍스트로만 "생성 완료"라고 하면 안 됨. 실제 도구 호출 필수!

2. 수정 요청 = 전체 슬라이드를 다시 구성하여 create_presentation 재호출
   PPT는 전체 재생성 방식 (부분 수정 불가)

3. JSON 노출 금지
   slides 배열, config 등 기술적 내용을 응답에 포함하지 말 것
   Bad: "다음 JSON으로 PPT를 생성합니다: [{...}]"
   Good: "3분기 실적 보고 PPT를 6장으로 구성하겠습니다."

4. PPT 생성 후 파일명 형식
   반드시 포함: "파일명: {실제파일명}.pptx"

5. 데이터/파일 참조 시 → search_user_files / search_workspace_docs 먼저 호출

6. 에러 발생 시 → 같은 도구를 2번 이상 재시도 금지!
   - create_presentation 실패 시, 테이블 구조를 단순화 (header_rows/body_merges 제거, 단순 headers+rows 사용)
   - 2번째 시도도 실패하면 → 사용자에게 오류 안내 + 텍스트로 슬라이드 구성 설명
   - 절대로 같은 도구를 3번 이상 호출하지 마세요!

═══════════════════════════════════════════════════════════════

## VISUALIZATION FIRST (시각화 우선 — 가장 중요!)

텍스트 불릿 나열 금지. 모든 데이터는 표 또는 차트로 시각화!

### 변환 규칙
- 비교/대비 → 비교 테이블 (헤더: [구분, A, B])
- 항목 나열 3개+ → 요약 테이블 (헤더: [항목, 내용])
- 단계/프로세스 → 프로세스 테이블 (헤더: [단계, 내용, 시기])
- 카테고리별 수치 → column/bar 차트
- 비율/점유율 → pie 차트
- 시계열 추이 → line 차트
- 텍스트 전용 슬라이드는 전체의 20% 이하로!

### 예시
INPUT: "에너지 밀도 5배, 출력 6배, 주행거리 16% 개선, 비용 14% 절감"
→ table: {headers: ["성능 지표", "개선 효과"], rows: [["에너지 밀도", "5배 향상"], ["출력", "6배 증가"], ["주행거리", "16% 개선"], ["비용", "14% 절감"]]}
→ textbox: "→ 차세대 전기차의 핵심 배터리 규격"

## SLIDE SPLITTING (슬라이드 분리)

1. 서로 다른 주제/전략/제품 → 반드시 별도 슬라이드
   BAD: "전략A + 전략B" 한 슬라이드 / GOOD: 전략별 각각 슬라이드
2. 주제 N개 → 개요 테이블 1장 + 각 주제 상세 N장
3. 테이블 8행 초과 시 분할, 차트는 전용 슬라이드
4. 대분류 3개+ → 간지(layout_index=2)로 섹션 구분

## LAYOUT PATTERNS

본문: L=0.37, T=1.15, W=12.6, H=5.95. 60%+ 채울 것.

A. 테이블 중심 (권장): 테이블 + 하단 인사이트 텍스트
B. 차트 + 인사이트: 차트(W=8,H=4) + 핵심 수치 텍스트
C. 2단 컬럼: 좌(L=0.37,W=6) + 우(L=6.7,W=6.27)
D. 섹션 분할 (데이터 없을 때만): Orange 제목 + 불릿

Answer in Korean unless asked otherwise."""

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """컨텍스트 + 템플릿 메타데이터를 반영한 시스템 프롬프트 생성"""
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

        # 템플릿 메타데이터 주입
        try:
            from app.mcp_servers.ppt_generator.template_indexer import load_metadata, format_metadata_for_llm
            metadata = load_metadata()
            if metadata:
                metadata_str = format_metadata_for_llm(metadata)
                prompt = prompt.replace("{template_metadata}", metadata_str)
            else:
                prompt = prompt.replace("{template_metadata}", "(메타데이터 없음 - list_ppt_templates 호출 필요)")
        except Exception as e:
            prompt = prompt.replace("{template_metadata}", f"(메타데이터 로드 실패: {e})")

        # 파일 컨텍스트 안내 추가
        has_files = context.get("has_files", False)
        workspace_has_files = context.get("workspace_has_files", False)

        file_context_notice = ""
        if has_files and session_id:
            file_context_notice = f"""
IMPORTANT - FILE CONTEXT:
User has uploaded files in this session. When user mentions "이 데이터", "데이터", "이걸", "파일" or similar,
you MUST call search_user_files(session_id="{session_id}", query="...") FIRST to retrieve the data.
"""
        elif workspace_uuid and workspace_has_files:
            file_context_notice = f"""
IMPORTANT - WORKSPACE CONTEXT:
User is in a workspace with documents. When user mentions "이 데이터", "데이터", "이걸", "문서" or similar,
you MUST call search_workspace_docs(workspace_uuid="{workspace_uuid}", query="...") FIRST to retrieve the data.
"""

        if file_context_notice:
            prompt = file_context_notice + "\n" + prompt

        # 워크스페이스 instructions 주입
        workspace_instructions = context.get("workspace_instructions")
        if workspace_instructions:
            prompt = f"WORKSPACE INSTRUCTIONS:\n{workspace_instructions}\n\n{prompt}"

        # 날짜 정보
        from datetime import datetime
        now = datetime.now()
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        weekday_kr = weekdays[now.weekday()]
        current_date = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
        prompt = f"Today is {current_date}.\n\n{prompt}"

        # 메모리 컨텍스트 주입
        if memory_context:
            summary = memory_context.get("summary", "")
            key_facts = memory_context.get("key_facts", [])
            if summary or key_facts:
                memory_section = "\n## 워크스페이스 메모리\n"
                if summary:
                    memory_section += f"이전 대화 요약: {summary}\n"
                if key_facts:
                    memory_section += "핵심 사실:\n"
                    for fact in key_facts:
                        memory_section += f"- {fact}\n"
                prompt = prompt + memory_section

        # 전역 사용자 메모리 주입
        if user_memory_context and user_memory_context.get("key_facts"):
            facts = user_memory_context["key_facts"]
            facts_text = "\n".join(f"  - {fact}" for fact in facts)
            prompt = f"## User Profile (사용자 개인 특성)\n\n이 사용자에 대해 알려진 정보:\n{facts_text}\n\n{prompt}"

        print(f"[PPTWorker] Context: session_id={bool(session_id)}, workspace_uuid={bool(workspace_uuid)}, has_files={has_files}")

        return prompt

    # PPTWorker는 BaseWorker의 stream_response()를 그대로 사용
    # - Haiku 대화 요약: BaseWorker 기본 (summarization_prompt 오버라이드로 PPT 특화)
    # - ReAct loop 압축: compact_previous_results=True

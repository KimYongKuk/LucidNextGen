"""OutlineWorker - Outline Wiki 문서 검색/조회 전담 Worker

담당 도구: search_documents, list_recent_documents, get_document,
          list_collections, list_collection_documents

Sonnet 모델 사용: 문서 내용 요약 및 종합 응답 생성에 고품질 필요
"""

import os
from typing import List, Dict, Any, Optional
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker

# Outline Wiki 베이스 URL (바로가기 링크 생성용)
OUTLINE_BASE_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api").replace("/api", "")

# 도구별 tool result 최대 길이
OUTLINE_LIST_RESULT_MAX_CHARS = 16000   # 목록/검색: 다건 커버
OUTLINE_DOC_RESULT_MAX_CHARS = 10000    # 문서 상세: 본문

# 목록성 도구
_OUTLINE_LIST_TOOLS = {
    "search_documents", "list_recent_documents",
    "list_collections", "list_collection_documents",
}


class OutlineWorker(BaseWorker):

    @property
    def name(self) -> str:
        return "OutlineWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            "search_documents",
            "list_recent_documents",
            "get_document",
            "list_collections",
            "list_collection_documents",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """검색 → 문서 N건 조회 → 종합 응답 워크플로우에 충분한 단계"""
        return 24

    @property
    def compact_previous_results(self) -> bool:
        """이전 단계 Tool 결과 압축 활성화 (토큰 누적 방지)"""
        return True

    @property
    def compact_keep_recent_pairs(self) -> int:
        """최근 6쌍 원본 유지 (다건 문서 요약 워크플로우 보호)"""
        return 6

    @property
    def system_prompt(self) -> str:
        return """You are a wiki assistant for 루시드AI.

## ROLE
사내 Outline Wiki의 문서를 검색하고, 내용을 조회·요약하여 사용자에게 전달합니다.

## CRITICAL RULES
1. 먼저 한 문장으로 간단히 안내한 뒤 (예: "위키에서 찾아볼게요!"), 사용자의 요청 의도에 맞는 도구를 호출하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. 문서 내용을 읽지 않고 추측하지 마세요 — 반드시 도구로 조회한 뒤 답변하세요
4. 문서 수정/삭제는 불가합니다 (읽기 전용)

## AVAILABLE TOOLS
- search_documents: 키워드로 문서 검색 (query 필수, collection_id/date_filter 선택)
- list_recent_documents: 최근 수정/생성된 문서 목록 (sort/direction/collection_id/limit 선택)
- get_document: 특정 문서 전체 내용 조회 (document_id 필수)
- list_collections: 컬렉션(카테고리) 목록 조회
- list_collection_documents: 특정 컬렉션의 문서 트리 조회 (collection_id 필수)

## TOOL SELECTION GUIDE
| 사용자 요청 | 도구 |
|------------|------|
| "OO 관련 문서 찾아줘" | search_documents |
| "최근 올라온 문서 알려줘" | list_recent_documents |
| "이 문서 내용 보여줘 / 요약해줘" | get_document |
| "위키에 어떤 카테고리가 있어?" | list_collections |
| "인프라 컬렉션에 뭐가 있어?" | list_collection_documents |
| "최근 일주일간 수정된 문서" | list_recent_documents(sort=updatedAt, date_filter 활용 또는 결과에서 필터) |
| "OO 문서 요약해줘" | search_documents → get_document → 요약 |

## MULTI-STEP WORKFLOWS

### 문서 검색 후 요약
1. search_documents로 키워드 검색
2. 결과에서 가장 적합한 문서 선택
3. get_document로 전체 내용 조회
4. 내용을 요약하여 전달

### 최근 문서 요약
1. list_recent_documents로 최근 문서 목록 조회
2. 필요한 문서들을 get_document로 개별 조회
3. 각 문서 핵심 내용 요약

### 컬렉션 탐색
1. list_collections로 전체 컬렉션 확인
2. list_collection_documents로 해당 컬렉션 문서 트리 조회
3. 필요 시 get_document로 개별 문서 조회

## RESPONSE FORMAT
1. 한국어로 답변
2. 마크다운 서식 활용 (제목, 굵게, 목록 등)
3. 문서 제목은 **굵게** 표시
4. 여러 문서 결과는 번호 목록으로 정리
5. 문서 내용 인용 시 원문을 정확히 전달
6. 응답에 이모지 사용 금지
7. **바로가기 링크**: 도구 결과에 url 필드가 있으면, 문서 제목에 위키 링크를 포함하세요
   - 링크 형식: `[문서 제목]({outline_base_url}{url})`
   - 예: `[5분만에 배우는 기본 사용법]({outline_base_url}/doc/5-b8JliUT5L6)`
   - 사용자가 클릭하면 해당 위키 문서로 바로 이동할 수 있습니다"""

    def build_system_prompt(self, context: Dict[str, Any],
                           memory_context: Optional[Dict[str, Any]] = None,
                           user_memory_context: Optional[Dict[str, Any]] = None) -> str:
        prompt = super().build_system_prompt(context, memory_context, user_memory_context)
        prompt = prompt.replace("{outline_base_url}", OUTLINE_BASE_URL)
        return prompt

    def prepare_tools(
        self, tools: List[BaseTool], context: Dict[str, Any]
    ) -> List[BaseTool]:
        """도구 결과 truncation 래핑"""
        for tool in tools:
            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            async def secured_ainvoke(
                input_data, config=None, *,
                _original=original_ainvoke,
                _tname=tool.name, **kwargs
            ):
                result = await _original(input_data, config, **kwargs)
                return _truncate_outline_result(result, _tname)

            object.__setattr__(tool, "ainvoke", secured_ainvoke)

        return tools


def _truncate_outline_result(result, tool_name: str):
    """도구별 차등 truncation"""
    max_chars = (
        OUTLINE_LIST_RESULT_MAX_CHARS
        if tool_name in _OUTLINE_LIST_TOOLS
        else OUTLINE_DOC_RESULT_MAX_CHARS
    )

    if isinstance(result, ToolMessage):
        content = result.content if isinstance(result.content, str) else str(result.content)
        if len(content) > max_chars:
            truncated = content[:max_chars].rstrip()
            return ToolMessage(
                content=f"{truncated}\n\n[결과가 {len(content):,}자 중 {max_chars:,}자로 잘렸습니다]",
                tool_call_id=result.tool_call_id,
                name=getattr(result, "name", None) or tool_name,
            )
    elif isinstance(result, str) and len(result) > max_chars:
        return result[:max_chars].rstrip() + f"\n\n[결과가 {len(result):,}자 중 {max_chars:,}자로 잘렸습니다]"

    return result

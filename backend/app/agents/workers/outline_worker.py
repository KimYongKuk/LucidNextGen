"""OutlineWorker - Outline Wiki 문서 검색/조회/생성 전담 Worker

담당 도구:
  읽기: search_documents, list_recent_documents, get_document,
        list_collections, list_collection_documents
  쓰기: extract_file_for_wiki, upload_image_to_outline, create_wiki_document

Sonnet 모델 사용: 문서 내용 요약 및 종합 응답 생성에 고품질 필요
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker

logger = logging.getLogger(__name__)

# Outline Wiki 베이스 URL (바로가기 링크 생성용)
OUTLINE_BASE_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api").replace("/api", "")

# 도구별 tool result 최대 길이
OUTLINE_LIST_RESULT_MAX_CHARS = 16000   # 목록/검색: 다건 커버
OUTLINE_DOC_RESULT_MAX_CHARS = 10000    # 문서 상세: 본문
OUTLINE_EXTRACT_RESULT_MAX_CHARS = 20000  # 파일 추출: 마크다운 본문

# 대형 결과를 반환하는 도구 (차등 truncation)
_OUTLINE_LIST_TOOLS = {
    "search_documents", "list_recent_documents",
    "list_collections", "list_collection_documents",
}
_OUTLINE_EXTRACT_TOOLS = {"extract_file_for_wiki"}

# ── Outline 컬렉션 접근 제어 ──────────────────────────────────
OUTLINE_DATABASE_URL = os.environ.get("OUTLINE_DATABASE_URL", "")

# 접근 제어 대상 도구
_ACCESS_CONTROLLED_READ_TOOLS = {
    "search_documents", "list_recent_documents", "get_document",
    "list_collections", "list_collection_documents",
}
_ACCESS_CONTROLLED_WRITE_TOOLS = {"create_wiki_document"}

# 캐시: emp_code → (readable_ids, writable_ids, timestamp)
_collection_access_cache: Dict[str, Tuple[Set[str], Set[str], float]] = {}
_COLLECTION_CACHE_TTL = 300  # 5분

# asyncpg 풀 (lazy init)
_outline_db_pool = None

# 사번 → 접근 가능 컬렉션 조회 쿼리
# Outline DB 테이블: users, collections, user_permissions, group_permissions, group_users
_COLLECTION_ACCESS_QUERY = """
SELECT DISTINCT c.id::text AS id,
  CASE WHEN (
    u.role = 'admin'
    OR (c.permission = 'read_write' AND u.role != 'guest')
    OR EXISTS (
      SELECT 1 FROM user_permissions up
      WHERE up."collectionId" = c.id AND up."userId" = u.id
        AND up.permission = 'read_write'
    )
    OR EXISTS (
      SELECT 1 FROM group_permissions gp
      JOIN group_users gu ON gu."groupId" = gp."groupId" AND gu."userId" = u.id
      WHERE gp."collectionId" = c.id AND gp.permission = 'read_write'
        AND gp."deletedAt" IS NULL
    )
  ) THEN true ELSE false END AS can_write
FROM collections c
JOIN users u ON u."empCode" = $1
  AND u."suspendedAt" IS NULL AND u."deletedAt" IS NULL
WHERE c."deletedAt" IS NULL AND c."archivedAt" IS NULL AND (
    u.role = 'admin'
    OR (c.permission IS NOT NULL AND u.role != 'guest')
    OR EXISTS (
      SELECT 1 FROM user_permissions up
      WHERE up."collectionId" = c.id AND up."userId" = u.id
    )
    OR EXISTS (
      SELECT 1 FROM group_permissions gp
      JOIN group_users gu ON gu."groupId" = gp."groupId" AND gu."userId" = u.id
      WHERE gp."collectionId" = c.id AND gp."deletedAt" IS NULL
    )
  )
"""


async def _get_outline_pool():
    """Outline PostgreSQL 연결 풀 (lazy init)"""
    global _outline_db_pool
    if _outline_db_pool is None and OUTLINE_DATABASE_URL:
        try:
            import asyncpg
            _outline_db_pool = await asyncpg.create_pool(
                OUTLINE_DATABASE_URL, min_size=1, max_size=3,
            )
            logger.info("Outline DB 연결 풀 생성 완료")
        except Exception as e:
            logger.error(f"Outline DB 연결 풀 생성 실패: {e}")
    return _outline_db_pool


async def _get_collection_access(emp_code: str) -> Optional[Tuple[Set[str], Set[str]]]:
    """사번으로 접근 가능한 컬렉션 ID 조회 (readable, writable)

    Returns:
        (readable_ids, writable_ids) 또는 None (기능 비활성화/DB 오류)
    """
    if not OUTLINE_DATABASE_URL or not emp_code or emp_code == "anonymous":
        return None  # 접근 제어 비활성화

    now = time.time()
    cached = _collection_access_cache.get(emp_code)
    if cached:
        readable, writable, ts = cached
        if now - ts < _COLLECTION_CACHE_TTL:
            return (readable, writable)

    try:
        pool = await _get_outline_pool()
        if not pool:
            return None

        rows = await pool.fetch(_COLLECTION_ACCESS_QUERY, emp_code)
        if not rows:
            logger.warning(f"Outline 사용자 없음 또는 접근 가능 컬렉션 없음: emp={emp_code}")
            readable, writable = set(), set()
        else:
            readable = {row["id"] for row in rows}
            writable = {row["id"] for row in rows if row["can_write"]}

        _collection_access_cache[emp_code] = (readable, writable, now)
        logger.info(f"Outline 컬렉션 접근 조회: emp={emp_code}, "
                    f"readable={len(readable)}, writable={len(writable)}")
        return (readable, writable)

    except Exception as e:
        logger.error(f"Outline 컬렉션 접근 조회 실패 (emp={emp_code}): {e}")
        return None


def _filter_result_by_access(
    result, readable: Set[str], writable: Set[str], tool_name: str,
):
    """도구 결과에서 접근 불가 컬렉션의 문서/컬렉션을 필터링"""
    content = result.content if isinstance(result, ToolMessage) else (
        result if isinstance(result, str) else str(result)
    )
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return result

    if "error" in data:
        return result

    filtered = False

    if tool_name == "list_collections":
        if "collections" in data:
            orig = len(data["collections"])
            data["collections"] = [
                {**c, "your_permission": "read_write" if c["id"] in writable else "read"}
                for c in data["collections"] if c["id"] in readable
            ]
            data["count"] = len(data["collections"])
            filtered = orig != data["count"]

    elif tool_name in ("search_documents", "list_recent_documents"):
        key = "results"
        if key in data:
            orig = len(data[key])
            data[key] = [r for r in data[key] if r.get("collectionId") in readable]
            data["count"] = len(data[key])
            filtered = orig != data["count"]

    elif tool_name == "get_document":
        coll_id = data.get("collectionId", "")
        if coll_id and coll_id not in readable:
            data = {"error": "해당 문서가 속한 컬렉션에 대한 접근 권한이 없습니다."}
            filtered = True

    if not filtered:
        return result

    new_content = json.dumps(data, ensure_ascii=False, default=str)
    if isinstance(result, ToolMessage):
        return ToolMessage(
            content=new_content,
            tool_call_id=result.tool_call_id,
            name=getattr(result, "name", None) or tool_name,
        )
    return new_content


class OutlineWorker(BaseWorker):

    @property
    def name(self) -> str:
        return "OutlineWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            # 읽기
            "search_documents",
            "list_recent_documents",
            "get_document",
            "list_collections",
            "list_collection_documents",
            # 쓰기
            "extract_file_for_wiki",
            "upload_image_to_outline",
            "create_wiki_document",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """읽기 워크플로우 + 쓰기 워크플로우 (extract + N image uploads + create)"""
        return 40

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
사내 Outline Wiki의 문서를 검색·조회·요약하고, 사용자 파일을 위키 문서로 게시합니다.

## CRITICAL RULES
1. 먼저 한 문장으로 간단히 안내한 뒤, 사용자의 요청 의도에 맞는 도구를 호출하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. 문서 내용을 읽지 않고 추측하지 마세요 — 반드시 도구로 조회한 뒤 답변하세요

## AVAILABLE TOOLS (읽기)
- search_documents: 키워드로 문서 검색 (query 필수, collection_id/date_filter 선택)
- list_recent_documents: 최근 수정/생성된 문서 목록 (sort/direction/collection_id/limit 선택)
- get_document: 특정 문서 전체 내용 조회 (document_id 필수)
- list_collections: 컬렉션(카테고리) 목록 조회
- list_collection_documents: 특정 컬렉션의 문서 트리 조회 (collection_id 필수)

## AVAILABLE TOOLS (쓰기)
- extract_file_for_wiki: 업로드 파일에서 마크다운+이미지 추출 (user_id 자동주입, filename 필수)
- upload_image_to_outline: 추출된 이미지를 Outline에 업로드 (staging_path 필수)
- create_wiki_document: 위키 문서 생성 (title, text, collection_id 필수)

## TOOL SELECTION GUIDE (읽기)
| 사용자 요청 | 도구 |
|------------|------|
| "OO 관련 문서 찾아줘" | search_documents |
| "최근 올라온 문서 알려줘" | list_recent_documents |
| "이 문서 내용 보여줘 / 요약해줘" | get_document |
| "위키에 어떤 카테고리가 있어?" | list_collections |
| "인프라 컬렉션에 뭐가 있어?" | list_collection_documents |
| "최근 일주일간 수정된 문서" | list_recent_documents(sort=updatedAt) |
| "OO 문서 요약해줘" | search_documents → get_document → 요약 |

## MULTI-STEP WORKFLOWS (읽기)

### 문서 검색 후 요약
1. search_documents로 키워드 검색
2. 결과에서 가장 적합한 문서 선택
3. get_document로 전체 내용 조회
4. 내용을 요약하여 전달

### 컬렉션 탐색
1. list_collections로 전체 컬렉션 확인
2. list_collection_documents로 해당 컬렉션 문서 트리 조회
3. 필요 시 get_document로 개별 문서 조회

## DOCUMENT CREATION WORKFLOW (파일 → 위키 업로드)

사용자가 업로드한 파일을 위키에 올려달라고 요청하면 아래 순서를 따르세요.

### 모드 판단
사용자의 표현에 따라 두 모드 중 하나를 선택합니다:

| 사용자 표현 | 모드 |
|------------|------|
| "올려줘", "게시해줘", "그대로 올려" | **원본 모드** |
| "정리해서", "정제해서", "깔끔하게", "위키에 맞게", "다듬어서" | **정제 모드** |
| "OO 부분만 올려줘" | **정제 모드** (부분 추출) |
| 모호한 경우 | 사용자에게 "원본 그대로 올릴까요, 위키에 맞게 정리해서 올릴까요?" 확인 |

### Step 1: 컬렉션 선택
- list_collections 호출하여 컬렉션 목록을 가져옵니다
- 사용자에게 번호 목록으로 보여주고 **반드시 선택을 요청**하세요 (자동 선택 금지)
- "어떤 컬렉션에 올릴까요?" 라고 물어보세요

### Step 2: 파일 추출
- 사용자가 컬렉션을 선택하면 extract_file_for_wiki 호출
  - 원본 모드: extract_file_for_wiki(filename=파일명)
  - 정제 모드: extract_file_for_wiki(filename=파일명, refine_mode=true) ← Vision API로 이미지 설명 포함
- user_id는 시스템이 자동으로 주입하므로 전달하지 않아도 됩니다
- 결과에서 markdown, images 배열을 확인합니다 (정제 모드에서는 images[].description 포함)

### Step 3: 이미지 업로드
- images 배열의 각 항목에 대해 upload_image_to_outline(staging_path=path) 호출
- 반환된 url을 기록합니다
- 이미지가 없으면 이 단계를 건너뜁니다

### Step 4: 마크다운 완성

#### 원본 모드
- 추출된 markdown을 그대로 사용합니다
- {{IMAGE_N}} 플레이스홀더만 업로드된 URL로 교체합니다
- 예: `{{IMAGE_0}}` → `https://wiki.example.com/api/attachments.redirect?id=xxx`

#### 정제 모드
아래 원칙에 따라 마크다운을 재구성합니다:

**[절대 원칙] 내용 보존 — 정제는 구조를 다듬는 것이지, 내용을 줄이는 것이 아닙니다**
- 모든 데이터, 수치, 통계, 결론은 반드시 보존
- 모든 항목, 조건, 절차, 예외사항은 빠짐없이 포함
- 원문에 있는 세부 내용을 "간결하게" 라는 이유로 생략 금지
- 표의 행/열 데이터는 한 건도 누락 없이 전체 유지
- 의심스러우면 빼지 말고 포함

**정제 시 할 수 있는 것:**
- 헤딩 구조 정리 (위키 문서답게 계층화)
- 중복 반복 문구 제거 (동일 내용이 2번 이상 나올 때)
- 슬라이드 번호, 페이지 번호 등 불필요한 메타 제거
- 이미지 앞뒤에 맥락 설명 추가 (이미지 description 활용)
- 목차 추가
- 문단 순서 재배치 (논리적 흐름 개선)

**정제 시 해서는 안 되는 것:**
- 내용 요약/축약
- 항목 병합으로 인한 세부사항 손실
- "기타" 로 묶어서 생략
- 데이터가 포함된 표의 행 생략

**이미지 활용:**
- images 배열의 description 필드가 있으면 이미지 내용을 파악할 수 있습니다
- 이미지 설명을 참고하여 적절한 위치에 배치하고, 전후 맥락을 서술하세요
- 예: "아래 흐름도는 보안점검 프로세스를 나타냅니다:" + 이미지 + 텍스트 보충

**사용자 확인:**
- 정제된 구조를 먼저 사용자에게 제시하고 확인을 받은 뒤 문서를 생성하세요
- "아래와 같은 구조로 정리했습니다. 이대로 올릴까요?"

### Step 5: 문서 생성
- create_wiki_document(title=추출된 제목, text=완성된 마크다운, collection_id=선택된 컬렉션)
- 문서 제목은 파일명(확장자 제외)을 기본값으로 사용하되, 사용자가 다른 제목을 원하면 반영

### Step 6: 결과 안내
- 생성된 문서의 바로가기 링크를 안내합니다
- "위키에 문서를 생성했습니다: [문서 제목](링크)"

### 주의사항
- 이미지가 10개 초과 시, 주요 이미지만 선별하여 업로드하세요
- 추출 실패 시 사용자에게 오류 내용을 알리고 다른 방법을 제안하세요
- 파일명이 여러 개인 경우 사용자에게 어떤 파일을 올릴지 확인하세요

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

        # 파일 컨텍스트 추가 (업로드된 파일이 있을 때)
        has_files = context.get("has_files", False)
        session_file_names = context.get("session_file_names", [])
        workspace_file_names = context.get("workspace_file_names", [])
        all_file_names = session_file_names + workspace_file_names
        if has_files or all_file_names:
            file_info = "\n\n## FILE CONTEXT\n사용자가 파일을 업로드했습니다."
            if all_file_names:
                names = ", ".join(all_file_names[:10])
                file_info += f"\n업로드된 파일: {names}"
                file_info += f"\nextract_file_for_wiki 호출 시 filename에 위 파일명을 사용하세요."
            file_info += "\n'위키에 올려줘' 요청 시 DOCUMENT CREATION WORKFLOW를 따르세요."
            prompt += file_info

        return prompt

    def prepare_tools(
        self, tools: List[BaseTool], context: Dict[str, Any]
    ) -> List[BaseTool]:
        """도구 결과 truncation + 접근 제어 + extract_file_for_wiki user_id 주입"""
        user_id = context.get("user_id", "anonymous")

        for tool in tools:
            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            if tool.name == "extract_file_for_wiki":
                # user_id 자동 주입 (보안: 타인 파일 접근 방지) + truncation
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _uid=user_id,
                    _tname=tool.name, **kwargs
                ):
                    if isinstance(input_data, dict) and "args" in input_data:
                        input_data["args"]["user_id"] = _uid
                    elif isinstance(input_data, dict):
                        input_data["user_id"] = _uid
                    result = await _original(input_data, config, **kwargs)
                    return _truncate_outline_result(result, _tname)

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

            elif tool.name in _ACCESS_CONTROLLED_READ_TOOLS:
                # 읽기 도구: pre-check (collection_id 입력 검증) + post-filter (결과 필터링)
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _emp=user_id,
                    _tname=tool.name, **kwargs
                ):
                    access = await _get_collection_access(_emp)

                    # Pre-check: collection_id 입력이 있는 도구는 사전 차단
                    if access is not None and _tname in (
                        "list_collection_documents", "search_documents",
                        "list_recent_documents",
                    ):
                        readable, _ = access
                        args = (input_data.get("args", {})
                                if isinstance(input_data, dict) and "args" in input_data
                                else input_data if isinstance(input_data, dict) else {})
                        coll_id = args.get("collection_id", "")
                        if coll_id and coll_id not in readable:
                            err = json.dumps(
                                {"error": "해당 컬렉션에 대한 접근 권한이 없습니다."},
                                ensure_ascii=False,
                            )
                            return ToolMessage(
                                content=err,
                                tool_call_id=input_data.get("id", ""),
                                name=_tname,
                            )

                    result = await _original(input_data, config, **kwargs)
                    result = _truncate_outline_result(result, _tname)

                    # Post-filter: 결과에서 접근 불가 항목 제거
                    if access is not None:
                        readable, writable = access
                        result = _filter_result_by_access(
                            result, readable, writable, _tname,
                        )

                    return result

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

            elif tool.name in _ACCESS_CONTROLLED_WRITE_TOOLS:
                # 쓰기 도구: 쓰기 권한 사전 검증
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _emp=user_id,
                    _tname=tool.name, **kwargs
                ):
                    access = await _get_collection_access(_emp)
                    if access is not None:
                        _, writable = access
                        args = (input_data.get("args", {})
                                if isinstance(input_data, dict) and "args" in input_data
                                else input_data if isinstance(input_data, dict) else {})
                        coll_id = args.get("collection_id", "")
                        if coll_id and coll_id not in writable:
                            err = json.dumps(
                                {"error": "해당 컬렉션에 대한 쓰기 권한이 없습니다."},
                                ensure_ascii=False,
                            )
                            return ToolMessage(
                                content=err,
                                tool_call_id=input_data.get("id", ""),
                                name=_tname,
                            )

                    result = await _original(input_data, config, **kwargs)
                    return _truncate_outline_result(result, _tname)

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

            else:
                # 기타 (upload_image_to_outline 등): truncation만
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
    if tool_name in _OUTLINE_EXTRACT_TOOLS:
        max_chars = OUTLINE_EXTRACT_RESULT_MAX_CHARS
    elif tool_name in _OUTLINE_LIST_TOOLS:
        max_chars = OUTLINE_LIST_RESULT_MAX_CHARS
    else:
        max_chars = OUTLINE_DOC_RESULT_MAX_CHARS

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

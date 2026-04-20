"""OutlineWorker - L&F Wiki 문서 검색/조회/생성 전담 Worker

담당 도구:
  읽기: search_documents, list_recent_documents, get_document,
        list_collections, list_collection_documents
  쓰기: publish_file_to_wiki (파일 파싱→이미지 업로드→문서 생성 원스텝)

하이브리드 검색: 키워드(Outline API) + 시멘틱(ChromaDB) → RRF 병합
Sonnet 모델 사용: 문서 내용 요약 및 종합 응답 생성에 고품질 필요
"""

import os
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker

logger = logging.getLogger(__name__)

# 하이브리드 검색 활성화 여부
HYBRID_SEARCH_ENABLED = os.environ.get("OUTLINE_HYBRID_SEARCH", "true").lower() == "true"
# RRF(Reciprocal Rank Fusion) 상수 k (높을수록 하위 순위 영향 증가)
RRF_K = 60

# L&F Wiki 베이스 URL (바로가기 링크 생성용)
OUTLINE_BASE_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api").replace("/api", "")

# 도구별 tool result 최대 길이
OUTLINE_LIST_RESULT_MAX_CHARS = 16000   # 목록/검색: 다건 커버
OUTLINE_DOC_RESULT_MAX_CHARS = 10000    # 문서 상세: 본문

# 대형 결과를 반환하는 도구 (차등 truncation)
_OUTLINE_LIST_TOOLS = {
    "search_documents", "list_recent_documents",
    "list_collections", "list_collection_documents",
}

# ── Outline 컬렉션 접근 제어 ──────────────────────────────────
OUTLINE_DATABASE_URL = os.environ.get("OUTLINE_DATABASE_URL", "")

# 접근 제어 대상 도구
_ACCESS_CONTROLLED_READ_TOOLS = {
    "search_documents", "list_recent_documents", "get_document",
    "list_collections", "list_collection_documents",
}
# publish_file_to_wiki는 별도 if 분기에서 user_id 주입과 함께 처리
_ACCESS_CONTROLLED_WRITE_TOOLS = {"create_document"}

# 캐시: emp_code → (readable_ids, writable_ids, timestamp)
_collection_access_cache: Dict[str, Tuple[Set[str], Set[str], float]] = {}
_COLLECTION_CACHE_TTL = 300  # 5분

# AI 참조 스코프: Official_Public 컬렉션 이름 (디폴트 AI 참조 ON)
AI_REFERENCE_PUBLIC_COLLECTION = os.environ.get(
    "AI_REFERENCE_PUBLIC_COLLECTION", "Official_Public"
)

# 캐시: team_id → (public_collection_ids, ai_ref_doc_ids, timestamp)
_ai_reference_cache: Dict[str, Tuple[Set[str], Set[str], float]] = {}
_AI_REFERENCE_CACHE_TTL = 60  # 1분

# Personal 컬렉션 캐시
_personal_collection_cache: Optional[Tuple[Set[str], float]] = None
_PERSONAL_COLLECTION_CACHE_TTL = 300  # 5분

# 사번 → Outline user ID 캐시
_user_id_cache: Dict[str, Tuple[Optional[str], float]] = {}

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


# AI 참조 가능 문서 조회 쿼리
# 1) Official_Public 컬렉션의 모든 발행된 문서 → AI 참조 가능
# 2) ai_reference_documents에 enabled=true인 최상위 문서 + 그 하위 문서 → AI 참조 가능
_AI_REFERENCE_QUERY = """
WITH RECURSIVE
  -- Official_Public 컬렉션 ID
  public_collections AS (
    SELECT id FROM collections
    WHERE name = $1 AND "deletedAt" IS NULL AND "archivedAt" IS NULL
  ),
  -- ai_reference_documents에 명시적 활성화된 최상위 문서 ID
  explicit_refs AS (
    SELECT "documentId" FROM ai_reference_documents
    WHERE enabled = true
  ),
  -- 명시적 활성화 문서의 하위 문서 (재귀)
  ref_descendants AS (
    SELECT id FROM documents WHERE id IN (SELECT "documentId" FROM explicit_refs)
      AND "deletedAt" IS NULL
    UNION ALL
    SELECT d.id FROM documents d
    JOIN ref_descendants rd ON d."parentDocumentId" = rd.id
    WHERE d."deletedAt" IS NULL
  )
SELECT id::text FROM documents
WHERE "deletedAt" IS NULL AND "publishedAt" IS NOT NULL
  AND "collectionId" IN (SELECT id FROM public_collections)
UNION
SELECT id::text FROM ref_descendants
"""


async def _get_ai_referenceable_doc_ids() -> Optional[Set[str]]:
    """AI 참조 가능한 문서 ID 집합 조회

    Returns:
        문서 ID 집합 또는 None (기능 비활성화/DB 오류)
    """
    if not OUTLINE_DATABASE_URL:
        return None  # 접근 제어 비활성화

    cache_key = "global"
    now = time.time()
    cached = _ai_reference_cache.get(cache_key)
    if cached:
        _, doc_ids, ts = cached
        if now - ts < _AI_REFERENCE_CACHE_TTL:
            return doc_ids

    try:
        pool = await _get_outline_pool()
        if not pool:
            return None

        rows = await pool.fetch(
            _AI_REFERENCE_QUERY, AI_REFERENCE_PUBLIC_COLLECTION
        )
        doc_ids = {row["id"] for row in rows}

        _ai_reference_cache[cache_key] = (set(), doc_ids, now)
        logger.info(f"AI 참조 가능 문서 조회: {len(doc_ids)}건")
        return doc_ids

    except Exception as e:
        logger.error(f"AI 참조 가능 문서 조회 실패: {e}")
        return None


async def _get_personal_collection_ids() -> Optional[Set[str]]:
    """Personal 컬렉션 ID 목록 조회 (캐시 5분)"""
    global _personal_collection_cache
    if not OUTLINE_DATABASE_URL:
        return None

    now = time.time()
    if _personal_collection_cache:
        ids, ts = _personal_collection_cache
        if now - ts < _PERSONAL_COLLECTION_CACHE_TTL:
            return ids

    try:
        pool = await _get_outline_pool()
        if not pool:
            return None
        rows = await pool.fetch(
            'SELECT id::text FROM collections WHERE "isPersonal" = true AND "deletedAt" IS NULL'
        )
        ids = {row["id"] for row in rows}
        _personal_collection_cache = (ids, now)
        return ids
    except Exception as e:
        logger.error(f"Personal 컬렉션 조회 실패: {e}")
        return None


async def _get_user_id_by_empcode(emp_code: str) -> Optional[str]:
    """사번으로 Outline user ID 조회 (캐시 5분)"""
    if not OUTLINE_DATABASE_URL or not emp_code or emp_code == "anonymous":
        return None

    now = time.time()
    cached = _user_id_cache.get(emp_code)
    if cached:
        uid, ts = cached
        if now - ts < _PERSONAL_COLLECTION_CACHE_TTL:
            return uid

    try:
        pool = await _get_outline_pool()
        if not pool:
            return None
        row = await pool.fetchrow(
            'SELECT id::text FROM users WHERE "empCode" = $1 AND "deletedAt" IS NULL LIMIT 1',
            emp_code,
        )
        uid = row["id"] if row else None
        _user_id_cache[emp_code] = (uid, now)
        return uid
    except Exception as e:
        logger.error(f"사번→userId 조회 실패 (emp={emp_code}): {e}")
        return None


def _filter_result_by_personal_collection(
    result, personal_ids: Set[str], user_id: str, tool_name: str,
):
    """Personal 컬렉션 문서 중 본인 것만 남기고 필터링"""
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

    if tool_name in ("search_documents", "list_recent_documents"):
        key = "results"
        if key in data:
            orig = len(data[key])
            data[key] = [
                r for r in data[key]
                if r.get("collectionId") not in personal_ids
                or (r.get("createdBy") or {}).get("id") == user_id
            ]
            data["count"] = len(data[key])
            filtered = orig != data["count"]

    elif tool_name == "get_document":
        coll_id = data.get("collectionId", "")
        if coll_id in personal_ids:
            creator_id = (data.get("createdBy") or {}).get("id", "")
            if creator_id != user_id:
                data = {"error": "해당 문서에 대한 접근 권한이 없습니다."}
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


def _filter_result_by_ai_reference(
    result, ai_ref_doc_ids: Set[str], tool_name: str,
):
    """도구 결과에서 AI 참조 불가 문서를 필터링"""
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

    if tool_name in ("search_documents", "list_recent_documents"):
        key = "results"
        if key in data:
            orig = len(data[key])
            data[key] = [r for r in data[key] if r.get("id") in ai_ref_doc_ids]
            data["count"] = len(data[key])
            filtered = orig != data["count"]

    elif tool_name == "get_document":
        doc_id = data.get("id", "")
        if doc_id and doc_id not in ai_ref_doc_ids:
            data = {"error": "해당 문서는 AI 챗봇 참조가 비활성화되어 있습니다."}
            filtered = True

    elif tool_name == "list_collection_documents":
        # 트리 구조의 문서 목록 — 참조 불가 문서에 마킹
        if "documents" in data:
            for doc in data["documents"]:
                doc["ai_reference"] = doc.get("id", "") in ai_ref_doc_ids

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


def _rrf_merge(
    keyword_results: List[dict],
    semantic_results: List[dict],
    k: int = RRF_K,
) -> List[dict]:
    """Reciprocal Rank Fusion으로 두 결과 리스트를 병합

    RRF score = Σ 1/(k + rank_i)
    양쪽에서 모두 발견된 문서가 상위로 올라감

    Args:
        keyword_results: 키워드 검색 결과 (id 필드 필요)
        semantic_results: 시멘틱 검색 결과 (document_id 필드 필요)
        k: RRF 상수

    Returns:
        RRF 스코어 순으로 정렬된 병합 결과
    """
    scores: Dict[str, float] = {}
    doc_data: Dict[str, dict] = {}

    # 키워드 결과 (Outline 형식: id 필드)
    for rank, doc in enumerate(keyword_results):
        doc_id = doc.get("id", "")
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        if doc_id not in doc_data:
            doc_data[doc_id] = doc

    # 시멘틱 결과 (ChromaDB 형식: document_id 필드, 청크 기반)
    for rank, hit in enumerate(semantic_results):
        doc_id = hit.get("document_id", "")
        if not doc_id:
            continue
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        if doc_id not in doc_data:
            # 시멘틱 결과를 키워드 결과 형식으로 변환
            snippet = hit.get("snippet", hit.get("summary", ""))
            doc_data[doc_id] = {
                "id": doc_id,
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "collectionId": hit.get("collection_id", ""),
                "updatedAt": hit.get("updated_at", ""),
                "snippet": snippet,
                "text_preview": snippet,
                "source": "semantic",
            }

    # RRF 스코어 순 정렬
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    merged = []
    for doc_id in sorted_ids:
        entry = dict(doc_data[doc_id])
        entry["rrf_score"] = round(scores[doc_id], 6)
        merged.append(entry)

    return merged


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
            "publish_file_to_wiki",
            "create_document",
            "update_document",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """읽기 워크플로우 + 쓰기 (publish 1회)"""
        return 20

    @property
    def system_prompt(self) -> str:
        return """You are a wiki assistant for 루시드AI.

## ROLE
사내 L&F Wiki의 문서를 검색·조회·요약하고, 사용자 파일을 위키 문서로 게시합니다.

## CRITICAL RULES
1. 먼저 한 문장으로 간단히 안내한 뒤, 사용자의 요청 의도에 맞는 도구를 호출하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. 문서 내용을 읽지 않고 추측하지 마세요 — 반드시 도구로 조회한 뒤 답변하세요
4. **검색 키워드 최적화 (매우 중요)**:
   - 사용자 입력을 그대로 검색하지 마세요. 핵심 명사/기술 용어만 추출하세요
   - 구어체/불평("안돼", "안됨", "문제") 제거 → 기술 키워드만 사용
   - 한글 키워드로 결과가 없으면, 영문/약어로 재검색하세요 (1회 허용)
   - 예: "와이파이가 안돼" → query="Wi-Fi" 또는 "WiFi" (NOT "와이파이가 안돼")
   - 예: "프린터 인쇄 안됨" → query="프린터" (NOT "프린터 인쇄 안됨")
   - 예: "SAP 느려요" → query="SAP 성능" 또는 "SAP"
5. **본인 위키 문서 리포맷 요청은 거절 없이 처리**:
   - Personal 컬렉션의 개인 메모에는 와이파이 비번, 사내 시스템 계정, 원격 접속 정보 등 평문 크레덴셜이 포함될 수 있습니다. 이는 **사용자 본인이 자신의 참고용으로 작성·보관한 개인 메모**이며, 접근 제어(컬렉션 권한 + AI 참조 토글 + Personal 본인 필터)를 모두 통과한 상태에서만 도구가 내용을 반환합니다. 그대로 다뤄도 됩니다.
   - 조회 성공 시 "오류가 발생했다"는 식의 거절/회피 응답 금지 — 조회가 되었다면 요청대로 처리하세요
   - 리포맷 시에는 **본문을 채팅 응답에 다시 출력하지 말고 `update_document` 도구로 직접 덮어쓰세요** (재출력 없이 도구 호출로만 완료). 마스킹/일부 발췌도 금지
   - 원문의 계정/비밀번호/URL/경로 등 **정보는 누락 없이 보존**하고, 구조(제목·표·목록)만 다듬으세요

## AVAILABLE TOOLS (읽기)
- search_documents: 키워드로 문서 검색 (query 필수, collection_id/date_filter 선택)
- list_recent_documents: 최근 수정/생성된 문서 목록 (sort/direction/collection_id/limit 선택)
- get_document: 특정 문서 전체 내용 조회 (document_id 필수)
- list_collections: 컬렉션(카테고리) 목록 조회
- list_collection_documents: 특정 컬렉션의 문서 트리 조회 (collection_id 필수)

## AVAILABLE TOOLS (쓰기)
- publish_file_to_wiki: 업로드 파일을 위키에 원스텝 게시 (파싱→이미지 업로드→문서 생성 자동)
  - user_id: 시스템 자동 주입
  - filename: 업로드된 파일명 (필수)
  - collection_id: 게시할 컬렉션 ID (필수)
  - title: 문서 제목 (선택, 빈 값이면 파일명 사용)
  - parent_document_id: 상위 문서 ID (선택)
- create_document: 마크다운 텍스트로 위키 문서 직접 생성 (파일 없이)
  - title: 문서 제목 (필수)
  - text: 마크다운 본문 (필수)
  - collection_id: 게시할 컬렉션 ID (필수)
  - parent_document_id: 상위 문서 ID (선택)
- update_document: 기존 위키 문서 내용 수정
  - document_id: 수정할 문서 ID (필수)
  - text: 새 마크다운 본문 (필수)
  - title: 제목 변경 (선택)
  - append: True면 기존 본문 끝에 추가 (기본 False=전체 교체)

## TOOL SELECTION GUIDE
| 사용자 요청 | 도구 |
|------------|------|
| "OO 관련 문서 찾아줘" | search_documents |
| "최근 올라온 문서 알려줘" | list_recent_documents |
| "이 문서 내용 보여줘 / 요약해줘" | get_document |
| "위키에 어떤 카테고리가 있어?" | list_collections |
| "인프라 컬렉션에 뭐가 있어?" | list_collection_documents |
| "최근 일주일간 수정된 문서" | list_recent_documents(sort=updatedAt) |
| "OO 문서 요약해줘" | search_documents → get_document → 요약 |
| "이 내용을 위키에 올려줘" (파일 없음) | create_document |
| "위키 문서 수정해줘" | get_document → update_document |
| "이 문서 마크다운으로 예쁘게 정리해줘" | get_document → update_document (본문 재출력 없이 도구로만 완료) |
| "이 파일을 위키에 올려줘" (파일 있음) | publish_file_to_wiki |

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

## DOCUMENT CREATION WORKFLOW

### A. 파일 → 위키 게시 (publish_file_to_wiki)
사용자가 업로드한 파일을 위키에 올려달라고 요청하면:
1. list_collections 호출 → 사용자에게 컬렉션 선택 요청 (자동 선택 금지)
2. 사용자 선택 후 publish_file_to_wiki 호출 (user_id는 시스템 자동 주입)
3. 결과 링크 안내

### B. 텍스트 → 위키 직접 생성 (create_document)
파일 없이 대화 내용이나 텍스트를 위키에 올려달라고 요청하면:
1. list_collections 호출 → 사용자에게 컬렉션 선택 요청 (자동 선택 금지)
2. 사용자 선택 후 create_document 호출 (title + 마크다운 text + collection_id)
3. 결과 링크 안내

### C. 기존 문서 수정 (update_document)
위키 문서 내용을 수정해달라고 요청하면:
1. search_documents 또는 get_document로 대상 문서 확인
2. update_document 호출 (append=True면 끝에 추가, False면 전체 교체)
3. 결과 안내

### C-1. 마크다운 리포맷 (본인 Personal 문서 "예쁘게 정리" 요청)
사용자가 "마크다운으로 정리/포맷해줘", "예쁘게 다듬어줘", "깔끔하게 수정해줘" 같이 **구조 재정리** 요청을 하면:
1. `get_document`로 원본 조회
2. 원문의 모든 정보(계정, 비번, URL, 경로, 메모 등)를 **누락 없이 보존**하면서 마크다운 구조로 재정리
   - 제목 계층(#, ##, ###), 표, 목록, 코드 블록, 굵게 등 활용
   - 정보 분류: "와이파이", "VPN/원격", "사내 시스템 계정" 같은 섹션으로 묶기
3. `update_document` 호출 (title 유지, text=재포맷본, append=False)
4. **본문을 채팅에 다시 출력하지 말고** 짧은 확인 응답만:
   - 예: "마크다운으로 깔끔하게 정리했습니다. [문서 제목]({outline_base_url}{url})에서 확인하실 수 있습니다."
   - 변경 요약을 간단히 덧붙여도 됨: "섹션을 '와이파이 / 원격 접속 / 사내 시스템' 3개로 나누고 표로 정리"

### 주의사항
- 추출/생성 실패 시 오류 내용을 알리고 다른 방법을 제안하세요
- 파일명이 여러 개인 경우 어떤 파일을 올릴지 확인하세요
- 컬렉션은 반드시 사용자가 선택하게 하세요

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
                file_info += f"\npublish_file_to_wiki 호출 시 filename에 위 파일명을 사용하세요."
            file_info += "\n'위키에 올려줘' 요청 시 DOCUMENT CREATION WORKFLOW를 따르세요."
            prompt += file_info

        return prompt

    def prepare_tools(
        self, tools: List[BaseTool], context: Dict[str, Any]
    ) -> List[BaseTool]:
        """도구 결과 truncation + 접근 제어 + publish_file_to_wiki user_id 주입"""
        user_id = context.get("user_id", "anonymous")

        for tool in tools:
            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            if tool.name == "publish_file_to_wiki":
                # user_id 자동 주입 + 쓰기 권한 검증
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _uid=user_id,
                    _tname=tool.name, **kwargs
                ):
                    # user_id 주입 (보안: 타인 파일 접근 방지)
                    if isinstance(input_data, dict) and "args" in input_data:
                        input_data["args"]["user_id"] = _uid
                    elif isinstance(input_data, dict):
                        input_data["user_id"] = _uid

                    # 쓰기 권한 사전 검증
                    access = await _get_collection_access(_uid)
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

            elif tool.name in _ACCESS_CONTROLLED_WRITE_TOOLS:
                # 쓰기 도구 (create_document 등): 쓰기 권한 검증만 (user_id 주입 불필요)
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _uid=user_id,
                    _tname=tool.name, **kwargs
                ):
                    access = await _get_collection_access(_uid)
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

            elif tool.name == "search_documents":
                # 하이브리드 검색: 키워드(MCP) + 시멘틱(ChromaDB) → RRF 병합
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _emp=user_id,
                    _tname=tool.name, **kwargs
                ):
                    access = await _get_collection_access(_emp)

                    # Pre-check: collection_id 접근 권한 검증
                    if access is not None:
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

                    # 키워드 검색 (MCP)
                    result = await _original(input_data, config, **kwargs)
                    result = _truncate_outline_result(result, _tname)

                    # Post-filter: 접근 불가 항목 제거
                    if access is not None:
                        readable, writable = access
                        result = _filter_result_by_access(
                            result, readable, writable, _tname,
                        )

                    # 하이브리드 검색: 시멘틱 결과와 RRF 병합
                    if HYBRID_SEARCH_ENABLED:
                        result = await _hybrid_merge_search(
                            result, input_data, _tname,
                            readable_ids=access[0] if access else None,
                            emp_code=_emp,
                        )

                    # AI 참조 스코프 필터
                    ai_ref_ids = await _get_ai_referenceable_doc_ids()
                    if ai_ref_ids is not None:
                        result = _filter_result_by_ai_reference(
                            result, ai_ref_ids, _tname,
                        )

                    # Personal 컬렉션 필터: 본인 문서만 노출
                    personal_ids = await _get_personal_collection_ids()
                    if personal_ids:
                        outline_uid = await _get_user_id_by_empcode(_emp)
                        if outline_uid:
                            result = _filter_result_by_personal_collection(
                                result, personal_ids, outline_uid, _tname,
                            )

                    return result

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

            elif tool.name in _ACCESS_CONTROLLED_READ_TOOLS:
                # 읽기 도구 (search_documents 제외): pre-check + post-filter
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _emp=user_id,
                    _tname=tool.name, **kwargs
                ):
                    access = await _get_collection_access(_emp)

                    # Pre-check: collection_id 입력이 있는 도구는 사전 차단
                    if access is not None and _tname in (
                        "list_collection_documents",
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

                    # AI 참조 스코프 필터
                    ai_ref_ids = await _get_ai_referenceable_doc_ids()
                    if ai_ref_ids is not None:
                        result = _filter_result_by_ai_reference(
                            result, ai_ref_ids, _tname,
                        )

                    # Personal 컬렉션 필터: 본인 문서만 노출
                    personal_ids = await _get_personal_collection_ids()
                    if personal_ids:
                        outline_uid = await _get_user_id_by_empcode(_emp)
                        if outline_uid:
                            result = _filter_result_by_personal_collection(
                                result, personal_ids, outline_uid, _tname,
                            )

                    return result

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

            else:
                # 기타: truncation만
                async def secured_ainvoke(
                    input_data, config=None, *,
                    _original=original_ainvoke,
                    _tname=tool.name, **kwargs
                ):
                    result = await _original(input_data, config, **kwargs)
                    return _truncate_outline_result(result, _tname)

                object.__setattr__(tool, "ainvoke", secured_ainvoke)

        return tools


async def _hybrid_merge_search(
    keyword_result,
    input_data: dict,
    tool_name: str,
    readable_ids: Optional[Set[str]] = None,
    emp_code: Optional[str] = None,
):
    """키워드 검색 결과에 시멘틱 검색 결과를 RRF 병합

    Args:
        keyword_result: MCP search_documents 결과 (ToolMessage 또는 str)
        input_data: 원본 tool call input (query 추출용)
        tool_name: 도구명
        readable_ids: 접근 가능 컬렉션 ID 집합

    Returns:
        RRF 병합된 결과 (ToolMessage 또는 str)
    """
    try:
        from app.services.outline_sync_service import get_outline_sync_service
        sync_service = get_outline_sync_service()

        # 쿼리 추출
        args = (input_data.get("args", {})
                if isinstance(input_data, dict) and "args" in input_data
                else input_data if isinstance(input_data, dict) else {})
        query = args.get("query", "")
        if not query:
            return keyword_result

        # 시멘틱 검색 (ChromaDB, 접근 가능 컬렉션만)
        collection_ids = list(readable_ids) if readable_ids else None
        semantic_hits = await sync_service.semantic_search(
            query=query,
            n_results=10,
            collection_ids=collection_ids,
        )

        if not semantic_hits:
            return keyword_result

        # Personal 컬렉션 필터: 시멘틱 결과에서 타인 문서 제거
        personal_ids = await _get_personal_collection_ids()
        if personal_ids and emp_code:
            outline_uid = await _get_user_id_by_empcode(emp_code)
            if outline_uid:
                semantic_hits = [
                    h for h in semantic_hits
                    if h.get("collection_id") not in personal_ids
                    or h.get("created_by_id") == outline_uid
                ]

        if not semantic_hits:
            return keyword_result

        # 키워드 결과 파싱
        content = (keyword_result.content
                   if isinstance(keyword_result, ToolMessage)
                   else keyword_result if isinstance(keyword_result, str)
                   else str(keyword_result))
        try:
            kw_data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return keyword_result

        if "error" in kw_data:
            # 키워드 검색 실패 → 시멘틱 결과만 반환
            output = []
            for hit in semantic_hits[:10]:
                snippet = hit.get("snippet", hit.get("summary", ""))
                output.append({
                    "id": hit["document_id"],
                    "title": hit.get("title", ""),
                    "url": hit.get("url", ""),
                    "collectionId": hit.get("collection_id", ""),
                    "updatedAt": hit.get("updated_at", ""),
                    "snippet": snippet,
                    "text_preview": snippet,
                    "search_type": "semantic",
                })
            merged_data = {"count": len(output), "results": output}
        else:
            kw_results = kw_data.get("results", [])
            merged = _rrf_merge(kw_results, semantic_hits)
            merged_data = {"count": len(merged), "results": merged[:15]}

        merged_json = json.dumps(merged_data, ensure_ascii=False, default=str)

        if isinstance(keyword_result, ToolMessage):
            return ToolMessage(
                content=merged_json,
                tool_call_id=keyword_result.tool_call_id,
                name=getattr(keyword_result, "name", None) or tool_name,
            )
        return merged_json

    except Exception as e:
        # 시멘틱 검색 실패 시 키워드 결과 그대로 반환 (graceful degradation)
        logger.warning(f"[OutlineWorker] 하이브리드 검색 실패, 키워드 결과만 반환: {e}")
        return keyword_result


def _truncate_outline_result(result, tool_name: str):
    """도구별 차등 truncation"""
    if tool_name in _OUTLINE_LIST_TOOLS:
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

"""Outline Wiki MCP 서버

Outline Wiki REST API를 통해 문서를 검색/조회합니다.
- 문서 키워드 검색 (documents.search)
- 최근 문서 목록 (documents.list)
- 문서 상세 조회 (documents.info)
- 컬렉션 목록 (collections.list)
- 컬렉션 내 문서 트리 (collections.documents)
"""
import sys
import os
import json
from typing import Optional, List

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastmcp import FastMCP

mcp = FastMCP("Outline Wiki Server")

# ── 설정 ──────────────────────────────────────────────
OUTLINE_API_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api")
OUTLINE_API_KEY = os.environ.get("OUTLINE_API_KEY", "")

# 문서 본문 최대 길이 (LLM 컨텍스트 효율)
DOC_BODY_MAX_LENGTH = int(os.environ.get("OUTLINE_DOC_MAX_LENGTH", "12000"))

# 검색 결과 기본 최대 건수
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_LIST_LIMIT = 10


# ── HTTP 헬퍼 ─────────────────────────────────────────

async def _outline_request(endpoint: str, payload: dict) -> dict:
    """Outline API POST 요청"""
    if not OUTLINE_API_KEY:
        return {"error": "OUTLINE_API_KEY가 설정되지 않았습니다."}

    url = f"{OUTLINE_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {OUTLINE_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"Outline API 오류 ({e.response.status_code}): {e.response.text[:500]}"}
    except httpx.ConnectError:
        return {"error": f"Outline 서버 연결 실패: {url}"}
    except Exception as e:
        return {"error": f"요청 실패: {str(e)[:300]}"}


def _truncate(text: str, max_len: int = DOC_BODY_MAX_LENGTH) -> str:
    """텍스트를 최대 길이로 잘라냄"""
    if not text or len(text) <= max_len:
        return text or ""
    return text[:max_len].rstrip() + f"\n\n[본문이 {len(text):,}자 중 {max_len:,}자로 잘렸습니다]"


def _format_document_summary(doc: dict) -> dict:
    """문서 요약 정보 포맷"""
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", "제목 없음"),
        "url": doc.get("url", ""),
        "updatedAt": doc.get("updatedAt", ""),
        "createdAt": doc.get("createdAt", ""),
        "createdBy": doc.get("createdBy", {}).get("name", ""),
        "collectionId": doc.get("collectionId", ""),
        "parentDocumentId": doc.get("parentDocumentId"),
        "revision": doc.get("revision", 0),
    }


# ── MCP 도구 ──────────────────────────────────────────

@mcp.tool()
async def search_documents(
    query: str,
    collection_id: str = "",
    date_filter: str = "",
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> str:
    """Outline Wiki에서 키워드로 문서를 검색합니다.

    Args:
        query: 검색 키워드
        collection_id: 특정 컬렉션 내 검색 (선택)
        date_filter: 기간 필터 - day, week, month, year (선택)
        limit: 최대 결과 수 (기본 10)
    """
    payload: dict = {"query": query, "limit": min(limit, 25)}

    if collection_id:
        payload["collectionId"] = collection_id
    if date_filter and date_filter in ("day", "week", "month", "year"):
        payload["dateFilter"] = date_filter

    result = await _outline_request("documents.search", payload)
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    documents = result.get("data", [])
    if not documents:
        return json.dumps({"message": f"'{query}' 검색 결과가 없습니다.", "count": 0}, ensure_ascii=False)

    output = []
    for item in documents:
        doc = item.get("document", {})
        context_text = item.get("context", "")  # 검색 하이라이트 snippet
        entry = _format_document_summary(doc)
        entry["snippet"] = context_text[:500] if context_text else ""
        # 본문도 일부 포함 (요약용)
        text = doc.get("text", "")
        entry["text_preview"] = _truncate(text, 2000)
        output.append(entry)

    return json.dumps(
        {"count": len(output), "results": output},
        ensure_ascii=False, default=str,
    )


@mcp.tool()
async def list_recent_documents(
    sort: str = "updatedAt",
    direction: str = "DESC",
    collection_id: str = "",
    limit: int = DEFAULT_LIST_LIMIT,
) -> str:
    """최근 수정/생성된 문서 목록을 조회합니다.

    Args:
        sort: 정렬 기준 - updatedAt, createdAt, publishedAt, title (기본 updatedAt)
        direction: 정렬 방향 - DESC(최신순), ASC(오래된순)
        collection_id: 특정 컬렉션 필터 (선택)
        limit: 최대 결과 수 (기본 10)
    """
    payload: dict = {
        "sort": sort,
        "direction": direction,
        "limit": min(limit, 25),
        "statusFilter": ["published"],
    }

    if collection_id:
        payload["collectionId"] = collection_id

    result = await _outline_request("documents.list", payload)
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    documents = result.get("data", [])
    if not documents:
        return json.dumps({"message": "문서가 없습니다.", "count": 0}, ensure_ascii=False)

    output = []
    for doc in documents:
        entry = _format_document_summary(doc)
        # 본문 미리보기 (목록에서는 짧게)
        text = doc.get("text", "")
        entry["text_preview"] = _truncate(text, 1000)
        output.append(entry)

    return json.dumps(
        {"count": len(output), "results": output},
        ensure_ascii=False, default=str,
    )


@mcp.tool()
async def get_document(document_id: str) -> str:
    """특정 문서의 전체 내용을 조회합니다.

    Args:
        document_id: 문서 ID (UUID)
    """
    if not document_id:
        return json.dumps({"error": "document_id는 필수입니다."}, ensure_ascii=False)

    result = await _outline_request("documents.info", {"id": document_id})
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    doc = result.get("data", {})
    if not doc:
        return json.dumps({"error": "문서를 찾을 수 없습니다."}, ensure_ascii=False)

    return json.dumps({
        "id": doc.get("id", ""),
        "title": doc.get("title", "제목 없음"),
        "url": doc.get("url", ""),
        "text": _truncate(doc.get("text", "")),
        "updatedAt": doc.get("updatedAt", ""),
        "createdAt": doc.get("createdAt", ""),
        "createdBy": doc.get("createdBy", {}).get("name", ""),
        "collectionId": doc.get("collectionId", ""),
        "parentDocumentId": doc.get("parentDocumentId"),
        "revision": doc.get("revision", 0),
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def list_collections() -> str:
    """Outline Wiki의 모든 컬렉션(카테고리) 목록을 조회합니다."""
    result = await _outline_request("collections.list", {"limit": 100})
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    collections = result.get("data", [])
    if not collections:
        return json.dumps({"message": "컬렉션이 없습니다.", "count": 0}, ensure_ascii=False)

    output = []
    for col in collections:
        output.append({
            "id": col.get("id", ""),
            "name": col.get("name", ""),
            "description": col.get("description", ""),
            "documentCount": col.get("documentCount", 0),
            "updatedAt": col.get("updatedAt", ""),
        })

    return json.dumps(
        {"count": len(output), "collections": output},
        ensure_ascii=False, default=str,
    )


@mcp.tool()
async def list_collection_documents(collection_id: str) -> str:
    """특정 컬렉션의 문서 트리(계층 구조)를 조회합니다.

    Args:
        collection_id: 컬렉션 ID (UUID)
    """
    if not collection_id:
        return json.dumps({"error": "collection_id는 필수입니다."}, ensure_ascii=False)

    result = await _outline_request("collections.documents", {"id": collection_id})
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    # 문서 트리 (NavigationNode[] 형태)
    tree = result.get("data", [])
    if not tree:
        return json.dumps({"message": "해당 컬렉션에 문서가 없습니다.", "count": 0}, ensure_ascii=False)

    def flatten_tree(nodes, depth=0):
        """트리를 평탄화하여 계층 정보 포함"""
        items = []
        for node in nodes:
            items.append({
                "id": node.get("id", ""),
                "title": node.get("title", ""),
                "url": node.get("url", ""),
                "depth": depth,
            })
            children = node.get("children", [])
            if children:
                items.extend(flatten_tree(children, depth + 1))
        return items

    flat = flatten_tree(tree)
    return json.dumps(
        {"count": len(flat), "documents": flat},
        ensure_ascii=False, default=str,
    )


# ── 엔트리포인트 ──────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")

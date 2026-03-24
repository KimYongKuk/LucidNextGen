"""Outline Wiki MCP 서버

Outline Wiki REST API를 통해 문서를 검색/조회/생성합니다.
- 문서 키워드 검색 (documents.search)
- 최근 문서 목록 (documents.list)
- 문서 상세 조회 (documents.info)
- 컬렉션 목록 (collections.list)
- 컬렉션 내 문서 트리 (collections.documents)
- 파일 → 마크다운 추출 (extract_file_for_wiki)
- 이미지 → Outline 첨부파일 업로드 (upload_image_to_outline)
- 위키 문서 생성 (create_wiki_document)
"""
import sys
import os
import json
from pathlib import Path
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

# 사용자 업로드 파일 루트
USER_UPLOAD_DIR = Path(os.environ.get(
    "USER_UPLOAD_DIR",
    str(Path(__file__).parent.parent.parent.parent / "data" / "user_uploads"),
))


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


async def _outline_upload(
    filename: str, file_bytes: bytes, content_type: str, document_id: str = ""
) -> dict:
    """Outline attachments.create (multipart/form-data)"""
    if not OUTLINE_API_KEY:
        return {"error": "OUTLINE_API_KEY가 설정되지 않았습니다."}

    url = f"{OUTLINE_API_URL.rstrip('/')}/attachments.create"
    headers = {"Authorization": f"Bearer {OUTLINE_API_KEY}"}

    try:
        files = {"file": (filename, file_bytes, content_type)}
        data = {}
        if document_id:
            data["documentId"] = document_id

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"첨부파일 업로드 오류 ({e.response.status_code}): {e.response.text[:500]}"}
    except Exception as e:
        return {"error": f"업로드 실패: {str(e)[:300]}"}


def _find_uploaded_file(user_id: str, filename: str) -> Optional[Path]:
    """user_uploads/{date}/{user_id}/{filename}에서 가장 최근 파일 탐색"""
    if not USER_UPLOAD_DIR.exists():
        return None

    # 사용자 ID 경로 안전 처리 (upload.py와 동일 로직)
    safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")

    # 날짜 디렉토리를 역순(최신 우선)으로 탐색
    try:
        date_dirs = sorted(
            [d for d in USER_UPLOAD_DIR.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )
    except Exception:
        return None

    for date_dir in date_dirs:
        candidate = date_dir / safe_uid / filename
        if candidate.exists():
            return candidate

    return None


# ── MCP 도구 (읽기) ──────────────────────────────────────────

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


# ── MCP 도구 (쓰기) ──────────────────────────────────

@mcp.tool()
async def extract_file_for_wiki(
    user_id: str,
    filename: str,
) -> str:
    """사용자가 업로드한 파일(PDF/PPTX/DOCX)에서 마크다운 텍스트와 이미지를 추출합니다.

    추출된 이미지는 스테이징 디렉토리에 저장되며,
    마크다운 본문에는 {{IMAGE_N}} 플레이스홀더가 삽입됩니다.
    이미지를 Outline에 업로드한 후 플레이스홀더를 실제 URL로 교체하세요.

    Args:
        user_id: 사용자 ID (사번, 시스템이 자동 주입)
        filename: 업로드된 파일명 (예: "보고서.pdf")
    """
    from .file_extractor import extract_file, cleanup_old_staging

    # 오래된 스테이징 정리 (부수 효과)
    cleanup_old_staging(max_age_hours=1)

    # 파일 경로 탐색
    file_path = _find_uploaded_file(user_id, filename)
    if not file_path:
        return json.dumps(
            {"error": f"파일을 찾을 수 없습니다: {filename} (user_id={user_id})"},
            ensure_ascii=False,
        )

    # 지원 형식 검증
    ext = file_path.suffix.lower()
    if ext not in {".pdf", ".pptx", ".docx"}:
        return json.dumps(
            {"error": f"지원하지 않는 형식입니다: {ext} (지원: PDF, PPTX, DOCX)"},
            ensure_ascii=False,
        )

    # 추출 실행
    result = extract_file(str(file_path))

    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({
        "title": result["title"],
        "markdown": result["markdown"],
        "image_count": len(result.get("images", [])),
        "images": [
            {
                "placeholder": img["placeholder"],
                "filename": img["filename"],
                "path": img["path"],
                "size": img.get("size", 0),
            }
            for img in result.get("images", [])
        ],
        "staging_dir": result.get("staging_dir", ""),
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def upload_image_to_outline(
    staging_path: str,
) -> str:
    """스테이징 디렉토리의 이미지를 Outline Wiki에 업로드합니다.

    extract_file_for_wiki 결과의 images[].path 값을 전달하세요.
    반환된 URL을 마크다운의 해당 플레이스홀더와 교체합니다.

    Args:
        staging_path: 이미지 파일 경로 (extract_file_for_wiki 결과에서 제공)
    """
    path = Path(staging_path)
    if not path.exists():
        return json.dumps(
            {"error": f"이미지 파일을 찾을 수 없습니다: {staging_path}"},
            ensure_ascii=False,
        )

    # 보안: 스테이징 디렉토리 내 파일만 허용
    from .file_extractor import STAGING_ROOT
    try:
        path.resolve().relative_to(STAGING_ROOT.resolve())
    except ValueError:
        return json.dumps(
            {"error": "허용되지 않는 경로입니다. 스테이징 디렉토리 내 파일만 업로드 가능합니다."},
            ensure_ascii=False,
        )

    # 파일 읽기 + Content-Type 추측
    import mimetypes
    file_bytes = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "image/png"

    # Outline 업로드
    result = await _outline_upload(path.name, file_bytes, content_type)

    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    # attachments.create 응답에서 URL 추출
    data = result.get("data", {})
    attachment_url = data.get("url", "")

    if not attachment_url:
        return json.dumps(
            {"error": "업로드는 성공했으나 URL을 받지 못했습니다."},
            ensure_ascii=False,
        )

    return json.dumps({
        "url": attachment_url,
        "filename": path.name,
        "message": f"{path.name} 업로드 완료",
    }, ensure_ascii=False)


@mcp.tool()
async def create_wiki_document(
    title: str,
    text: str,
    collection_id: str,
    parent_document_id: str = "",
    publish: bool = True,
) -> str:
    """Outline Wiki에 새 문서를 생성합니다.

    extract_file_for_wiki로 추출한 마크다운에서
    {{IMAGE_N}} 플레이스홀더를 upload_image_to_outline 결과 URL로 교체한 뒤 호출하세요.

    Args:
        title: 문서 제목
        text: 문서 본문 (마크다운)
        collection_id: 문서를 생성할 컬렉션 ID (list_collections 결과에서 선택)
        parent_document_id: 상위 문서 ID (선택, 하위 문서로 생성 시)
        publish: 즉시 게시 여부 (기본 True)
    """
    if not title or not title.strip():
        return json.dumps({"error": "문서 제목은 필수입니다."}, ensure_ascii=False)
    if not collection_id:
        return json.dumps({"error": "collection_id는 필수입니다."}, ensure_ascii=False)
    if not text or not text.strip():
        return json.dumps({"error": "문서 본문은 필수입니다."}, ensure_ascii=False)

    payload: dict = {
        "title": title.strip(),
        "text": text,
        "collectionId": collection_id,
        "publish": publish,
    }

    if parent_document_id:
        payload["parentDocumentId"] = parent_document_id

    result = await _outline_request("documents.create", payload)

    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    doc = result.get("data", {})
    if not doc:
        return json.dumps({"error": "문서 생성 응답이 비어있습니다."}, ensure_ascii=False)

    return json.dumps({
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "collectionId": doc.get("collectionId", ""),
        "createdAt": doc.get("createdAt", ""),
        "message": f"위키 문서 '{doc.get('title', '')}' 생성 완료",
    }, ensure_ascii=False, default=str)


# ── 엔트리포인트 ──────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")

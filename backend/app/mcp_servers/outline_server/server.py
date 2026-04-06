"""L&F Wiki MCP 서버

L&F Wiki(Outline) REST API를 통해 문서를 검색/조회/생성합니다.
- 문서 키워드 검색 (documents.search)
- 최근 문서 목록 (documents.list)
- 문서 상세 조회 (documents.info)
- 컬렉션 목록 (collections.list)
- 컬렉션 내 문서 트리 (collections.documents)
- 파일 → 위키 원스텝 게시 (publish_file_to_wiki)
"""
import sys
import os
import re
import json
import asyncio
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))  # file_extractor 임포트용

from fastmcp import FastMCP

mcp = FastMCP("L&F Wiki Server")

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
    """Outline attachments.create (2단계: presigned URL → 파일 업로드)

    Step 1: POST /api/attachments.create (JSON) → presigned URL + form fields
    Step 2: POST to presigned URL (multipart) → 실제 파일 업로드
    """
    if not OUTLINE_API_KEY:
        return {"error": "OUTLINE_API_KEY가 설정되지 않았습니다."}

    try:
        # Step 1: presigned URL 요청
        payload: dict = {
            "name": filename,
            "size": len(file_bytes),
            "contentType": content_type,
        }
        if document_id:
            payload["documentId"] = document_id

        step1 = await _outline_request("attachments.create", payload)
        if "error" in step1:
            return step1

        data = step1.get("data", {})
        upload_url = data.get("uploadUrl", "")
        form_fields = data.get("form", {})
        attachment = data.get("attachment", {})

        if not upload_url:
            return {"error": "presigned URL을 받지 못했습니다."}

        # 상대 경로인 경우 베이스 URL 붙이기 (로컬 스토리지 환경)
        if upload_url.startswith("/"):
            base = OUTLINE_API_URL.rstrip("/").replace("/api", "")
            upload_url = f"{base}{upload_url}"

        # Step 2: presigned URL에 파일 업로드
        async with httpx.AsyncClient(timeout=60) as client:
            # form fields를 multipart data로 구성 (presigned 필드 + 파일)
            files_data = {}
            form_data = {}
            for k, v in form_fields.items():
                form_data[k] = v

            resp = await client.post(
                upload_url,
                headers={"Authorization": f"Bearer {OUTLINE_API_KEY}"},
                data=form_data,
                files={"file": (filename, file_bytes, content_type)},
            )
            # S3 presigned upload는 200~204를 반환
            if resp.status_code >= 400:
                return {"error": f"파일 업로드 실패 ({resp.status_code}): {resp.text[:500]}"}

        # attachment URL 반환
        return {"data": attachment}

    except httpx.HTTPStatusError as e:
        return {"error": f"첨부파일 업로드 오류 ({e.response.status_code}): {e.response.text[:500]}"}
    except Exception as e:
        return {"error": f"업로드 실패: {str(e)[:300]}"}


async def _upload_images_parallel(
    images: List[Dict],
) -> Tuple[Dict[str, str], int, int]:
    """이미지 목록을 Outline에 병렬 업로드

    Args:
        images: file_extractor 결과의 images 리스트 (path, placeholder, filename, content_type 포함)

    Returns:
        (placeholder_to_url 매핑, 성공 수, 실패 수)
    """
    if not images:
        return {}, 0, 0

    async def _upload_one(img: Dict) -> Tuple[str, Optional[str]]:
        """단일 이미지 업로드, (placeholder, url 또는 None) 반환"""
        img_path = Path(img["path"])
        if not img_path.exists():
            return img["placeholder"], None
        file_bytes = img_path.read_bytes()
        content_type = img.get("content_type") or mimetypes.guess_type(img_path.name)[0] or "image/png"
        result = await _outline_upload(img_path.name, file_bytes, content_type)
        if "error" in result:
            print(f"[Outline] 이미지 업로드 실패 {img_path.name}: {result['error']}", file=sys.stderr)
            return img["placeholder"], None
        url = result.get("data", {}).get("url", "")
        return img["placeholder"], url or None

    results = await asyncio.gather(
        *[_upload_one(img) for img in images],
        return_exceptions=True,
    )

    placeholder_to_url = {}
    success = 0
    fail = 0
    for r in results:
        if isinstance(r, Exception):
            fail += 1
            continue
        placeholder, url = r
        if url:
            placeholder_to_url[placeholder] = url
            success += 1
        else:
            fail += 1

    return placeholder_to_url, success, fail


def _replace_image_placeholders(markdown: str, placeholder_to_url: Dict[str, str]) -> str:
    """마크다운 내 {{IMAGE_N}} 플레이스홀더를 실제 URL로 교체"""
    for placeholder, url in placeholder_to_url.items():
        # ![filename]({{IMAGE_N}}) 패턴을 ![filename](url)로 교체
        markdown = markdown.replace(f"]({placeholder})", f"]({url})")
        # 단독 {{IMAGE_N}}도 교체
        markdown = markdown.replace(placeholder, f"![]({url})")
    # 업로드 실패한 플레이스홀더 제거
    markdown = re.sub(r'!\[[^\]]*\]\(\{\{IMAGE_\d+\}\}\)\n*', '', markdown)
    markdown = re.sub(r'\{\{IMAGE_\d+\}\}', '', markdown)
    return markdown


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


# ── 동의어 사전 (검색 확장) ────────────────────────────────────
# 한글 구어체/약어 → 영문/정식 명칭 매핑
# 쌍방향: 어느 쪽으로 검색해도 상대 키워드로 확장
_SYNONYM_MAP: Dict[str, List[str]] = {
    # 네트워크/무선
    "와이파이": ["Wi-Fi", "WiFi", "무선"],
    "wifi": ["Wi-Fi", "WiFi", "와이파이", "무선"],
    "wi-fi": ["WiFi", "와이파이", "무선"],
    "무선": ["Wi-Fi", "WiFi", "와이파이"],
    # VPN
    "vpn": ["VPN 접속", "원격접속", "SSL VPN"],
    # 하드웨어
    "노트북": ["PC", "랩탑", "laptop"],
    "컴퓨터": ["PC", "데스크탑"],
    # 소프트웨어
    "오피스": ["Microsoft Office", "MS Office", "엑셀", "워드"],
    "한글": ["HWP", "한컴오피스"],
    # 인증/계정
    "비번": ["비밀번호", "패스워드", "password"],
    "비밀번호": ["패스워드", "password", "P/W"],
    "otp": ["OTP", "이중인증", "2차인증"],
}


def _expand_synonyms(query: str) -> List[str]:
    """쿼리에 동의어가 있으면 확장 키워드 목록 반환 (원본 제외)"""
    query_lower = query.lower().strip()
    expansions: List[str] = []

    for key, synonyms in _SYNONYM_MAP.items():
        if key in query_lower:
            for syn in synonyms:
                if syn.lower() not in query_lower:
                    expansions.append(syn)
            break  # 첫 매칭만 (중복 확장 방지)

    return expansions


# ── MCP 도구 (읽기) ──────────────────────────────────────────

@mcp.tool()
async def search_documents(
    query: str,
    collection_id: str = "",
    date_filter: str = "",
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> str:
    """L&F Wiki에서 키워드로 문서를 검색합니다.

    Args:
        query: 검색 키워드
        collection_id: 특정 컬렉션 내 검색 (선택)
        date_filter: 기간 필터 - day, week, month, year (선택)
        limit: 최대 결과 수 (기본 10)
    """
    base_payload: dict = {}
    if collection_id:
        base_payload["collectionId"] = collection_id
    if date_filter and date_filter in ("day", "week", "month", "year"):
        base_payload["dateFilter"] = date_filter

    # 1차: 원본 쿼리로 검색
    payload = {**base_payload, "query": query, "limit": min(limit, 25)}
    result = await _outline_request("documents.search", payload)
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    documents = result.get("data", [])

    # 2차: 결과 부족 시 동의어 확장 검색
    if len(documents) < 3:
        synonyms = _expand_synonyms(query)
        seen_ids = {item.get("document", {}).get("id") for item in documents}

        for syn_query in synonyms[:2]:  # 최대 2개 동의어까지
            syn_payload = {**base_payload, "query": syn_query, "limit": min(limit, 10)}
            syn_result = await _outline_request("documents.search", syn_payload)
            for item in syn_result.get("data", []):
                doc_id = item.get("document", {}).get("id")
                if doc_id and doc_id not in seen_ids:
                    documents.append(item)
                    seen_ids.add(doc_id)

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
    """L&F Wiki의 모든 컬렉션(카테고리) 목록을 조회합니다.
    각 컬렉션의 실제 문서 수를 포함합니다."""
    result = await _outline_request("collections.list", {"limit": 100})
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    collections = result.get("data", [])
    if not collections:
        return json.dumps({"message": "컬렉션이 없습니다.", "count": 0}, ensure_ascii=False)

    # 각 컬렉션의 실제 문서 수를 병렬로 조회
    async def _count_docs(col_id: str) -> int:
        """collections.documents 트리를 조회해 실제 문서 수 반환"""
        try:
            tree_result = await _outline_request("collections.documents", {"id": col_id})
            if "error" in tree_result:
                return -1  # 조회 실패 시 -1

            def _count_tree(nodes):
                count = 0
                for node in nodes:
                    count += 1
                    children = node.get("children", [])
                    if children:
                        count += _count_tree(children)
                return count

            return _count_tree(tree_result.get("data", []))
        except Exception:
            return -1

    # 병렬 조회
    doc_counts = await asyncio.gather(
        *[_count_docs(col.get("id", "")) for col in collections],
        return_exceptions=True,
    )

    output = []
    for i, col in enumerate(collections):
        count = doc_counts[i] if not isinstance(doc_counts[i], Exception) else -1
        entry = {
            "id": col.get("id", ""),
            "name": col.get("name", ""),
            "description": col.get("description", ""),
            "updatedAt": col.get("updatedAt", ""),
        }
        if count >= 0:
            entry["documentCount"] = count
        else:
            entry["documentCount"] = col.get("documentCount", 0)
            entry["documentCountApproximate"] = True
        output.append(entry)

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
async def publish_file_to_wiki(
    user_id: str,
    filename: str,
    collection_id: str,
    title: str = "",
    parent_document_id: str = "",
    publish: bool = True,
) -> str:
    """업로드한 파일(PDF/PPTX/DOCX)을 L&F Wiki에 원스텝으로 게시합니다.

    파일 파싱 → 이미지 병렬 업로드 → 마크다운 조립 → 문서 생성을 한 번에 수행합니다.

    Args:
        user_id: 사용자 ID (사번, 시스템이 자동 주입)
        filename: 업로드된 파일명 (예: "보고서.pdf")
        collection_id: 게시할 컬렉션 ID (list_collections 결과에서 선택)
        title: 문서 제목 (빈 값이면 파일명 사용)
        parent_document_id: 상위 문서 ID (선택, 하위 문서로 생성 시)
        publish: 즉시 게시 여부 (기본 True)
    """
    from file_extractor import extract_file, cleanup_old_staging

    if not collection_id:
        return json.dumps({"error": "collection_id는 필수입니다."}, ensure_ascii=False)

    # 오래된 스테이징 정리 (부수 효과)
    cleanup_old_staging(max_age_hours=1)

    # ① 파일 찾기
    file_path = _find_uploaded_file(user_id, filename)
    if not file_path:
        return json.dumps(
            {"error": f"파일을 찾을 수 없습니다: {filename}"},
            ensure_ascii=False,
        )

    ext = file_path.suffix.lower()
    if ext not in {".pdf", ".pptx", ".docx"}:
        return json.dumps(
            {"error": f"지원하지 않는 형식입니다: {ext} (지원: PDF, PPTX, DOCX)"},
            ensure_ascii=False,
        )

    # ② 파일 파싱 (마크다운 + 이미지 추출)
    result = extract_file(str(file_path))
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    markdown = result.get("markdown", "")
    images = result.get("images", [])
    doc_title = title.strip() if title and title.strip() else result.get("title", file_path.stem)

    # ③ 이미지 병렬 업로드 + 플레이스홀더 치환
    if images:
        placeholder_to_url, img_ok, img_fail = await _upload_images_parallel(images)
        markdown = _replace_image_placeholders(markdown, placeholder_to_url)
        print(f"[Outline] 이미지 업로드: {img_ok} 성공, {img_fail} 실패", file=sys.stderr)
    else:
        img_ok, img_fail = 0, 0

    if not markdown or not markdown.strip():
        return json.dumps({"error": "추출된 본문이 비어있습니다."}, ensure_ascii=False)

    # ④ 문서 생성
    payload: dict = {
        "title": doc_title,
        "text": markdown,
        "collectionId": collection_id,
        "publish": publish,
    }
    if parent_document_id:
        payload["parentDocumentId"] = parent_document_id

    doc_result = await _outline_request("documents.create", payload)
    if "error" in doc_result:
        return json.dumps(doc_result, ensure_ascii=False)

    doc = doc_result.get("data", {})
    if not doc:
        return json.dumps({"error": "문서 생성 응답이 비어있습니다."}, ensure_ascii=False)

    return json.dumps({
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "collectionId": doc.get("collectionId", ""),
        "createdAt": doc.get("createdAt", ""),
        "images_uploaded": img_ok,
        "images_failed": img_fail,
        "message": f"위키 문서 '{doc.get('title', '')}' 게시 완료 (이미지 {img_ok}개 포함)",
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def create_document(
    title: str,
    text: str,
    collection_id: str,
    parent_document_id: str = "",
    publish: bool = True,
) -> str:
    """마크다운 텍스트로 L&F Wiki 문서를 직접 생성합니다.

    파일 업로드 없이 텍스트만으로 위키 문서를 생성할 때 사용합니다.

    Args:
        title: 문서 제목
        text: 마크다운 형식의 문서 본문
        collection_id: 게시할 컬렉션 ID (list_collections 결과에서 선택)
        parent_document_id: 상위 문서 ID (선택, 하위 문서로 생성 시)
        publish: 즉시 게시 여부 (기본 True)
    """
    if not title or not title.strip():
        return json.dumps({"error": "title은 필수입니다."}, ensure_ascii=False)
    if not text or not text.strip():
        return json.dumps({"error": "text는 필수입니다."}, ensure_ascii=False)
    if not collection_id:
        return json.dumps({"error": "collection_id는 필수입니다."}, ensure_ascii=False)

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


@mcp.tool()
async def update_document(
    document_id: str,
    text: str,
    title: str = "",
    append: bool = False,
) -> str:
    """기존 L&F Wiki 문서의 내용을 수정합니다.

    Args:
        document_id: 수정할 문서 ID (UUID)
        text: 새로운 마크다운 본문 (append=False면 전체 교체, True면 끝에 추가)
        title: 문서 제목 변경 (선택, 빈 값이면 기존 제목 유지)
        append: True면 기존 본문 끝에 추가, False면 전체 교체 (기본 False)
    """
    if not document_id:
        return json.dumps({"error": "document_id는 필수입니다."}, ensure_ascii=False)
    if not text or not text.strip():
        return json.dumps({"error": "text는 필수입니다."}, ensure_ascii=False)

    payload: dict = {
        "id": document_id,
        "text": text,
        "append": append,
    }
    if title and title.strip():
        payload["title"] = title.strip()

    result = await _outline_request("documents.update", payload)
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    doc = result.get("data", {})
    if not doc:
        return json.dumps({"error": "문서 수정 응답이 비어있습니다."}, ensure_ascii=False)

    return json.dumps({
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "updatedAt": doc.get("updatedAt", ""),
        "revision": doc.get("revision", 0),
        "message": f"위키 문서 '{doc.get('title', '')}' 수정 완료",
    }, ensure_ascii=False, default=str)


# ── 엔트리포인트 ──────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")

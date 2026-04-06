"""NAS 파일 탐색 MCP 서버

회사 Synology NAS(WebDAV)에 연결하여 파일/폴더를 탐색하고 다운로드하는 MCP 서버입니다.
1단계: 읽기 전용 (list, search, download, info)

보안 원칙:
- NAS_ALLOWED_PATHS 화이트리스트 외 경로 접근 차단
- Path traversal (..) 차단
- 모든 작업 감사 로깅 (stderr)
"""
import sys
import os
import uuid
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from typing import List, Dict, Optional
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

mcp = FastMCP("NAS File Explorer Server v1")

# ─── 설정 ──────────────────────────────────────────
NAS_WEBDAV_URL = os.getenv("NAS_WEBDAV_URL", "http://192.168.100.20:5005")
NAS_USERNAME = os.getenv("NAS_USERNAME", "")
NAS_PASSWORD = os.getenv("NAS_PASSWORD", "")
NAS_TIMEOUT = int(os.getenv("NAS_TIMEOUT", "15"))

# 허용 경로 화이트리스트 (쉼표 구분)
_raw_allowed = os.getenv("NAS_ALLOWED_PATHS", "/Landf/부서간공유")
NAS_ALLOWED_PATHS: List[str] = [p.strip().rstrip("/") for p in _raw_allowed.split(",") if p.strip()]

# 다운로드 저장 디렉토리
NAS_DOWNLOAD_DIR = os.getenv("NAS_DOWNLOAD_DIR", "data/nas_download")
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
NAS_DOWNLOAD_FULL = os.path.join(_BASE_DIR, NAS_DOWNLOAD_DIR)

# WebDAV 루트 프리픽스 (Synology NAS는 보통 루트 마운트 "")
# /webdav/ 마운트인 경우 "/webdav" 로 설정
WEBDAV_ROOT = os.getenv("NAS_WEBDAV_ROOT", "")


# ─── 감사 로깅 ──────────────────────────────────────
def _audit(action: str, path: str, detail: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[NAS AUDIT] {ts} | action={action} | path={path}"
    if detail:
        msg += f" | {detail}"
    print(msg, file=sys.stderr)


# ─── 경로 검증 ──────────────────────────────────────
def _validate_path(path: str) -> str:
    """
    경로 검증 및 정규화

    1. '..' 포함 시 거부 (path traversal 차단)
    2. NAS_ALLOWED_PATHS 화이트리스트 검증
    3. WebDAV 루트 프리픽스 자동 처리

    Returns:
        WebDAV 요청에 사용할 전체 경로 (예: /webdav/Landf/부서간공유/...)
    """
    if not path:
        raise ValueError("경로가 비어있습니다.")

    # Path traversal 차단
    if ".." in path:
        raise ValueError(f"잘못된 경로입니다: path traversal 감지 ({path})")

    # 정규화: 앞뒤 공백 제거, 슬래시 통일
    normalized = path.strip().replace("\\", "/")

    # WebDAV 루트 프리픽스 제거 (사용자가 /webdav/... 형태로 입력한 경우)
    if WEBDAV_ROOT and normalized.startswith(WEBDAV_ROOT + "/"):
        normalized = normalized[len(WEBDAV_ROOT):]
    elif WEBDAV_ROOT and normalized.startswith(WEBDAV_ROOT):
        normalized = normalized[len(WEBDAV_ROOT):]

    # 앞에 / 보장
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    # 화이트리스트 검증
    path_lower = normalized.lower().rstrip("/")
    allowed = False
    for ap in NAS_ALLOWED_PATHS:
        ap_lower = ap.lower().rstrip("/")
        if path_lower == ap_lower or path_lower.startswith(ap_lower + "/"):
            allowed = True
            break

    if not allowed:
        raise ValueError(
            f"접근이 허용되지 않은 경로입니다: {normalized}\n"
            f"허용된 경로: {', '.join(NAS_ALLOWED_PATHS)}"
        )

    return normalized


def _to_webdav_url(validated_path: str) -> str:
    """검증된 경로를 WebDAV URL로 변환"""
    return NAS_WEBDAV_URL.rstrip("/") + WEBDAV_ROOT + validated_path


# ─── WebDAV 헬퍼 ────────────────────────────────────
_auth = None


def _get_auth() -> HTTPBasicAuth:
    global _auth
    if _auth is None:
        if not NAS_USERNAME or not NAS_PASSWORD:
            raise ValueError("NAS 인증 정보가 설정되지 않았습니다 (NAS_USERNAME, NAS_PASSWORD)")
        _auth = HTTPBasicAuth(NAS_USERNAME, NAS_PASSWORD)
    return _auth


def _parse_propfind(xml_text: str) -> List[Dict]:
    """PROPFIND XML 응답 파싱"""
    namespaces = {"D": "DAV:", "lp1": "DAV:"}
    root = ET.fromstring(xml_text)
    items = []

    for response in root.findall("D:response", namespaces):
        info: Dict = {}

        href_elem = response.find("D:href", namespaces)
        if href_elem is not None and href_elem.text:
            info["href"] = unquote(href_elem.text)

        propstat = response.find("D:propstat", namespaces)
        if propstat is not None:
            prop = propstat.find("D:prop", namespaces)
            if prop is not None:
                # 디렉토리 여부
                rt = prop.find("lp1:resourcetype", namespaces)
                info["is_directory"] = (
                    rt is not None and rt.find("D:collection", namespaces) is not None
                )

                # 파일 크기
                cl = prop.find("lp1:getcontentlength", namespaces)
                if cl is not None and cl.text:
                    info["size"] = int(cl.text)

                # 수정일
                lm = prop.find("lp1:getlastmodified", namespaces)
                if lm is not None and lm.text:
                    info["modified"] = lm.text

                # 생성일
                cd = prop.find("lp1:creationdate", namespaces)
                if cd is not None and cd.text:
                    info["created"] = cd.text

        items.append(info)

    return items


def _format_size(size_bytes: int) -> str:
    """바이트를 읽기 쉬운 크기로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _extract_name(href: str) -> str:
    """href에서 파일/폴더명 추출"""
    parts = href.rstrip("/").split("/")
    return parts[-1] if parts else href


# ─── MCP 도구 ────────────────────────────────────────


@mcp.tool()
async def list_nas_directory(path: str) -> str:
    """NAS 폴더의 파일 및 하위 폴더 목록을 조회합니다.

    Args:
        path: 조회할 NAS 경로 (예: /Landf/부서간공유, /Landf/부서간공유/HR부문)

    Returns:
        폴더 내 파일/디렉토리 목록 (이름, 타입, 크기, 수정일)
    """
    try:
        validated = _validate_path(path)
        _audit("list_directory", validated)

        url = _to_webdav_url(validated)
        response = requests.request(
            "PROPFIND", url,
            auth=_get_auth(),
            headers={"Depth": "1", "Content-Type": "application/xml"},
            timeout=NAS_TIMEOUT,
        )

        if response.status_code != 207:
            return f"폴더 조회 실패: HTTP {response.status_code}"

        items = _parse_propfind(response.text)

        # 현재 디렉토리 자체 제외
        webdav_path = (WEBDAV_ROOT + validated).rstrip("/")
        items = [it for it in items if it.get("href", "").rstrip("/") != webdav_path]

        if not items:
            return f"'{validated}' 폴더가 비어있습니다."

        # 디렉토리/파일 분리 후 정렬
        dirs = sorted([it for it in items if it.get("is_directory")], key=lambda x: _extract_name(x.get("href", "")))
        files = sorted([it for it in items if not it.get("is_directory")], key=lambda x: _extract_name(x.get("href", "")))

        lines = [f"경로: {validated}", f"총 {len(dirs)}개 폴더, {len(files)}개 파일", ""]

        if dirs:
            lines.append("📁 폴더:")
            for d in dirs:
                name = _extract_name(d.get("href", ""))
                lines.append(f"  - {name}/")

        if files:
            lines.append("📄 파일:")
            for f in files:
                name = _extract_name(f.get("href", ""))
                size = _format_size(f["size"]) if "size" in f else "크기 미상"
                modified = f.get("modified", "날짜 미상")
                lines.append(f"  - {name} ({size}, {modified})")

        return "\n".join(lines)

    except ValueError as e:
        return f"경로 오류: {e}"
    except requests.exceptions.Timeout:
        return f"NAS 서버 응답 시간 초과 ({NAS_TIMEOUT}초)"
    except requests.exceptions.ConnectionError:
        return "NAS 서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요."
    except Exception as e:
        _audit("list_directory_error", path, str(e))
        return f"폴더 조회 중 오류 발생: {e}"


@mcp.tool()
async def search_nas_files(path: str, keyword: str, max_depth: int = 3) -> str:
    """NAS 폴더에서 파일명에 키워드가 포함된 파일을 재귀적으로 검색합니다.

    Args:
        path: 검색 시작 경로 (예: /Landf/부서간공유)
        keyword: 검색할 키워드 (파일명에 포함된 문자열, 대소문자 구분 없음)
        max_depth: 최대 탐색 깊이 (기본값 3, 최대 5)

    Returns:
        키워드와 일치하는 파일 목록 (경로, 크기, 수정일)
    """
    try:
        validated = _validate_path(path)
        _audit("search_files", validated, f"keyword={keyword}, max_depth={max_depth}")

        if not keyword or not keyword.strip():
            return "검색 키워드를 입력해주세요."

        keyword_lower = keyword.strip().lower()
        max_depth = min(max(1, max_depth), 5)  # 1~5로 제한

        results: List[Dict] = []
        MAX_RESULTS = 50

        def _search_recursive(current_path: str, depth: int):
            if depth > max_depth or len(results) >= MAX_RESULTS:
                return

            url = _to_webdav_url(current_path)
            try:
                resp = requests.request(
                    "PROPFIND", url,
                    auth=_get_auth(),
                    headers={"Depth": "1", "Content-Type": "application/xml"},
                    timeout=NAS_TIMEOUT,
                )
                if resp.status_code != 207:
                    return
            except Exception:
                return

            items = _parse_propfind(resp.text)
            webdav_path = (WEBDAV_ROOT + current_path).rstrip("/")
            items = [it for it in items if it.get("href", "").rstrip("/") != webdav_path]

            for item in items:
                if len(results) >= MAX_RESULTS:
                    break
                name = _extract_name(item.get("href", ""))
                href = item.get("href", "")

                if item.get("is_directory"):
                    # 폴더명도 매칭 체크
                    if keyword_lower in name.lower():
                        results.append({
                            "name": name + "/",
                            "path": href.replace(WEBDAV_ROOT, "").rstrip("/") + "/",
                            "is_directory": True,
                        })
                    # 하위 탐색
                    sub_path = href.replace(WEBDAV_ROOT, "").rstrip("/")
                    _search_recursive(sub_path, depth + 1)
                else:
                    if keyword_lower in name.lower():
                        results.append({
                            "name": name,
                            "path": href.replace(WEBDAV_ROOT, ""),
                            "size": _format_size(item["size"]) if "size" in item else "크기 미상",
                            "modified": item.get("modified", "날짜 미상"),
                            "is_directory": False,
                        })

        _search_recursive(validated, 1)

        if not results:
            return f"'{validated}'에서 '{keyword}' 키워드와 일치하는 파일을 찾을 수 없습니다."

        lines = [
            f"검색 경로: {validated}",
            f"키워드: '{keyword}'",
            f"검색 결과: {len(results)}건" + (f" (최대 {MAX_RESULTS}건 표시)" if len(results) >= MAX_RESULTS else ""),
            "",
        ]

        dirs_found = [r for r in results if r.get("is_directory")]
        files_found = [r for r in results if not r.get("is_directory")]

        if dirs_found:
            lines.append("📁 폴더:")
            for d in dirs_found:
                lines.append(f"  - {d['path']}")

        if files_found:
            lines.append("📄 파일:")
            for f in files_found:
                lines.append(f"  - {f['name']} ({f['size']}, {f['modified']})")
                lines.append(f"    경로: {f['path']}")

        return "\n".join(lines)

    except ValueError as e:
        return f"경로 오류: {e}"
    except Exception as e:
        _audit("search_files_error", path, str(e))
        return f"파일 검색 중 오류 발생: {e}"


@mcp.tool()
async def download_nas_file(remote_path: str) -> str:
    """NAS에서 파일을 다운로드합니다.

    Args:
        remote_path: 다운로드할 파일의 NAS 경로 (예: /Landf/부서간공유/HR부문/문서.pdf)

    Returns:
        다운로드 결과 (로컬 저장 경로, 파일 크기)
    """
    try:
        validated = _validate_path(remote_path)
        _audit("download_file", validated)

        filename = _extract_name(validated)
        if not filename or "/" in filename:
            return "올바른 파일 경로를 입력해주세요."

        # 다운로드
        url = _to_webdav_url(validated)
        response = requests.get(url, auth=_get_auth(), timeout=NAS_TIMEOUT * 2, stream=True)

        if response.status_code == 404:
            return f"파일을 찾을 수 없습니다: {validated}"
        elif response.status_code != 200:
            return f"파일 다운로드 실패: HTTP {response.status_code}"

        # 로컬 저장 (날짜별 + UUID 프리픽스)
        date_dir = datetime.now().strftime("%Y-%m-%d")
        save_dir = os.path.join(NAS_DOWNLOAD_FULL, date_dir)
        os.makedirs(save_dir, exist_ok=True)

        safe_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        local_path = os.path.join(save_dir, safe_filename)

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(local_path)
        _audit("download_complete", validated, f"local={local_path}, size={_format_size(file_size)}")

        return (
            f"다운로드 완료!\n"
            f"  파일명: {filename}\n"
            f"  크기: {_format_size(file_size)}\n"
            f"  로컬 경로: {local_path}\n"
            f"  NAS 경로: {validated}"
        )

    except ValueError as e:
        return f"경로 오류: {e}"
    except requests.exceptions.Timeout:
        return f"다운로드 시간 초과 ({NAS_TIMEOUT * 2}초). 파일 크기가 너무 크거나 네트워크가 느립니다."
    except requests.exceptions.ConnectionError:
        return "NAS 서버에 연결할 수 없습니다."
    except Exception as e:
        _audit("download_error", remote_path, str(e))
        return f"파일 다운로드 중 오류 발생: {e}"


@mcp.tool()
async def get_nas_file_info(path: str) -> str:
    """NAS 파일 또는 폴더의 존재 여부와 메타정보를 확인합니다.

    Args:
        path: 확인할 NAS 경로 (예: /Landf/부서간공유/문서.pdf)

    Returns:
        파일/폴더 존재 여부, 크기, 수정일 등 메타정보
    """
    try:
        validated = _validate_path(path)
        _audit("file_info", validated)

        url = _to_webdav_url(validated)
        response = requests.request(
            "PROPFIND", url,
            auth=_get_auth(),
            headers={"Depth": "0"},
            timeout=NAS_TIMEOUT,
        )

        if response.status_code == 404:
            return f"존재하지 않는 경로입니다: {validated}"
        elif response.status_code != 207:
            return f"정보 조회 실패: HTTP {response.status_code}"

        items = _parse_propfind(response.text)
        if not items:
            return f"정보를 가져올 수 없습니다: {validated}"

        item = items[0]
        name = _extract_name(validated)
        is_dir = item.get("is_directory", False)

        lines = [
            f"이름: {name}",
            f"타입: {'폴더' if is_dir else '파일'}",
            f"경로: {validated}",
        ]

        if not is_dir and "size" in item:
            lines.append(f"크기: {_format_size(item['size'])}")
        if "modified" in item:
            lines.append(f"수정일: {item['modified']}")
        if "created" in item:
            lines.append(f"생성일: {item['created']}")

        return "\n".join(lines)

    except ValueError as e:
        return f"경로 오류: {e}"
    except requests.exceptions.Timeout:
        return f"NAS 서버 응답 시간 초과 ({NAS_TIMEOUT}초)"
    except Exception as e:
        _audit("file_info_error", path, str(e))
        return f"정보 조회 중 오류 발생: {e}"


# ─── 서버 시작 ───────────────────────────────────────
if __name__ == "__main__":
    print(f"[NAS MCP] Starting NAS File Explorer Server", file=sys.stderr)
    print(f"[NAS MCP] WebDAV URL: {NAS_WEBDAV_URL}", file=sys.stderr)
    print(f"[NAS MCP] Allowed paths: {NAS_ALLOWED_PATHS}", file=sys.stderr)
    print(f"[NAS MCP] Download dir: {NAS_DOWNLOAD_FULL}", file=sys.stderr)
    mcp.run(transport="stdio")

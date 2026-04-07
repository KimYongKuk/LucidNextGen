"""RAG MCP Server - 사내 문서 및 사용자 파일 검색"""
import sys
import os
import asyncio
import time
from typing import Optional

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP
from app.services.chromadb_service import (
    get_chromadb_service,
    get_admin_chromadb_service,
)

# MCP 서버 초기화
mcp = FastMCP("RAG Search Server")

# ChromaDB 서비스 초기화 (사용자/관리자 분리)
chromadb_service_user = get_chromadb_service()
chromadb_service_admin = get_admin_chromadb_service()

# Collection 상수 정의
COLLECTION_HR = "corp-hr"              # 인사
COLLECTION_ACCOUNTING = "corp-acct"    # 재경
COLLECTION_IT = "corp-it"              # IT
COLLECTION_SAFETY = "corp-safety"      # 안전환경

DEFAULT_ADMIN_USER = "admin"

# 유사도 임계값 설정 (0.0~1.0, 높을수록 엄격)
# 임계값 이하의 결과는 필터링되어 반환되지 않음
MIN_RELEVANCE_CORP = 0.5      # 사내 문서: 관련 없는 문서 필터링
MIN_RELEVANCE_USER = 0.1      # 사용자 파일: 매우 느슨하게 (분석해줘 등 일반 쿼리도 허용)
MIN_RELEVANCE_WORKSPACE = 0.25 # 워크스페이스: 구조화 데이터(엑셀 등) 허용


# ================================
# 부서별 전용 검색 도구 (5개)
# ================================

@mcp.tool()
async def search_hr_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """인사팀/교육 문서 검색. 채용, 인사이동, 평가, 복리후생, 휴가, 급여, 교육, 연수 관련."""
    try:
        start_time = time.time()
        results = await chromadb_service_admin.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_HR,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_hr_docs: {search_time}ms (query='{query[:50]}...', results={len(results)}, min_rel={MIN_RELEVANCE_CORP})", file=sys.stderr)

        if not results:
            return "관련 인사팀 문서를 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[인사 문서 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"인사팀 문서 검색 중 오류 발생: {str(e)}"



@mcp.tool()
async def search_ac_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """재경팀 문서 검색. 회계, 결산, 재무제표, 예산, 세무, 경비처리, 법인카드, SAP 관련."""
    try:
        start_time = time.time()
        results = await chromadb_service_admin.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_ACCOUNTING,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_ac_docs: {search_time}ms (query='{query[:50]}...', results={len(results)}, min_rel={MIN_RELEVANCE_CORP})", file=sys.stderr)

        if not results:
            return "관련 재경팀 문서를 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[재경 문서 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"재경팀 문서 검색 중 오류 발생: {str(e)}"


@mcp.tool()
async def search_it_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """IT팀 문서 검색. 시스템, 네트워크, 서버, ERP, 계정발급, 권한관리, 보안, 개인정보보호 관련."""
    try:
        start_time = time.time()
        results = await chromadb_service_admin.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_IT,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_it_docs: {search_time}ms (query='{query[:50]}...', results={len(results)}, min_rel={MIN_RELEVANCE_CORP})", file=sys.stderr)

        if not results:
            return "관련 IT팀 문서를 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[IT 문서 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"IT팀 문서 검색 중 오류 발생: {str(e)}"


@mcp.tool()
async def search_safety_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """안전환경팀 문서 검색. 산업안전보건, 환경관리, 소방, 재해대응, 안전점검, ISO, 작업환경, 건강관리 관련."""
    try:
        start_time = time.time()
        results = await chromadb_service_admin.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_SAFETY,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_safety_docs: {search_time}ms (query='{query[:50]}...', results={len(results)}, min_rel={MIN_RELEVANCE_CORP})", file=sys.stderr)

        if not results:
            return "관련 안전환경팀 문서를 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[안전환경 문서 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"안전환경팀 문서 검색 중 오류 발생: {str(e)}"


@mcp.tool()
async def search_user_files(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    limit: int = 3
) -> str:
    """사용자가 업로드한 파일 검색. 파일 내용 질문 시 사용. session_id 필수."""
    try:
        start_time = time.time()
        # session_id가 있으면 사용자 업로드 파일 검색
        results = await chromadb_service_user.search(
            query=query,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            min_relevance=MIN_RELEVANCE_USER
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_user_files: {search_time}ms (query='{query[:50]}...', session={session_id[:8]}..., results={len(results)}, min_rel={MIN_RELEVANCE_USER})", file=sys.stderr)

        if not results:
            return "업로드된 파일에서 관련 내용을 찾지 못했습니다."

        # 결과 포맷팅
        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[파일 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"사용자 파일 검색 중 오류 발생: {str(e)}"


@mcp.tool()
async def search_workspace_docs(
    query: str,
    workspace_uuid: str,
    limit: int = 3
) -> str:
    """워크스페이스 문서 검색. workspace_uuid가 주어지면 최우선 사용."""
    try:
        start_time = time.time()
        # 워크스페이스 컬렉션 이름 구성
        collection_name = f"workspace_{workspace_uuid}"

        # 사용자 권한으로 검색 (워크스페이스 컬렉션은 명시적 이름 사용)
        results = await chromadb_service_user.search(
            query=query,
            user_id="workspace_bot",  # Not used when collection is explicit
            session_id=None,
            collection=collection_name,
            limit=limit,
            min_relevance=MIN_RELEVANCE_WORKSPACE
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_TIMING] search_workspace_docs: {search_time}ms (workspace={workspace_uuid[:8]}..., query='{query[:50]}...', results={len(results)}, min_rel={MIN_RELEVANCE_WORKSPACE})", file=sys.stderr)

        if not results:
            return "워크스페이스 문서에서 관련 내용을 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[워크스페이스 문서 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"워크스페이스 문서 검색 중 오류 발생: {str(e)}"


# ================================
# 파일 전문 조회 도구 (fulltext)
# ================================

FULLTEXT_MAX_CHARS = 50000  # 5만자 제한


@mcp.tool()
async def get_uploaded_file_content(
    session_id: str,
    filename: str,
    user_id: str = "anonymous",
) -> str:
    """업로드한 파일의 전체 내용을 반환합니다. 파일 요약, 번역, 전체 분석 시 사용합니다.

    search_user_files와 달리 파일 전문을 반환합니다 (최대 50,000자).
    "요약해줘", "번역해줘", "전체 분석" 같은 전문 처리 요청에 사용하세요.

    Args:
        session_id: 세션 ID (필수)
        filename: 파일명 (정확한 파일명, 예: 보고서.pdf)
        user_id: 사용자 ID
    """
    try:
        start_time = time.time()

        # 1. ChromaDB 메타데이터에서 filename → file_id 조회
        file_id = chromadb_service_user.get_file_id_by_filename(
            filename=filename,
            user_id=user_id,
            session_id=session_id,
        )

        if not file_id:
            return f"'{filename}' 파일을 찾을 수 없습니다. 정확한 파일명을 확인해주세요."

        # 2. fulltext 파일 읽기
        fulltext = chromadb_service_user.get_fulltext(file_id)

        if fulltext is None:
            return (
                f"'{filename}' 파일의 전체 텍스트가 저장되어 있지 않습니다.\n"
                f"이 파일은 전문 조회 기능 추가 이전에 업로드되었을 수 있습니다.\n"
                f"search_user_files 도구로 부분 검색은 가능합니다."
            )

        elapsed = int((time.time() - start_time) * 1000)
        total_chars = len(fulltext)

        # 3. 트렁케이트
        if total_chars > FULLTEXT_MAX_CHARS:
            fulltext = fulltext[:FULLTEXT_MAX_CHARS]
            header = (
                f"[파일: {filename} | 전체 {total_chars:,}자 중 앞 {FULLTEXT_MAX_CHARS:,}자 표시]\n"
                f"※ 전체 내용이 너무 길어 앞부분만 표시합니다. "
                f"특정 부분을 찾으시려면 search_user_files를 사용해주세요.\n\n"
            )
        else:
            header = f"[파일: {filename} | 전체 내용 ({total_chars:,}자)]\n\n"

        print(
            f"[RAG_TIMING] get_uploaded_file_content: {elapsed}ms "
            f"(file={filename}, file_id={file_id[:8]}..., chars={total_chars}, "
            f"truncated={total_chars > FULLTEXT_MAX_CHARS})",
            file=sys.stderr,
        )

        return header + fulltext

    except Exception as e:
        return f"파일 전문 조회 중 오류 발생: {str(e)}"


if __name__ == "__main__":
    # stdio 모드로 MCP 서버 실행
    mcp.run(transport="stdio")

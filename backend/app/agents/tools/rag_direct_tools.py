"""RAG 직접 호출 도구 - MCP 프로세스 오버헤드 없이 ChromaDB 직접 호출

MCP 기반 RAG 도구를 대체하여 임베딩 모델 재로드 없이 빠른 검색을 제공합니다.
서버 시작 시 모델이 한 번 로드되면 이후 호출은 0.1초 이내로 완료됩니다.
"""

import time
import sys
from typing import List, Optional
from langchain_core.tools import StructuredTool

from app.services.chromadb_service import (
    get_chromadb_service,
    get_admin_chromadb_service,
)


# ============================================================================
# 상수 정의 (rag_server.py와 동일)
# ============================================================================

COLLECTION_HR = "corp-hr"              # 인사
COLLECTION_ACCOUNTING = "corp-acct"    # 재경
COLLECTION_IT = "corp-it"              # IT
COLLECTION_SAFETY = "corp-safety"      # 안전환경

DEFAULT_ADMIN_USER = "admin"

# 유사도 임계값 설정 (0.0~1.0, 높을수록 엄격)
MIN_RELEVANCE_CORP = 0.5      # 사내 문서: 관련 없는 문서 필터링
MIN_RELEVANCE_USER = 0.1      # 사용자 파일: 매우 느슨하게
MIN_RELEVANCE_WORKSPACE = 0.25 # 워크스페이스: 구조화 데이터(엑셀 등) 허용

# 직접 호출로 교체되는 도구 이름 목록
RAG_TOOL_NAMES = [
    "search_hr_docs",
    "search_ac_docs",
    "search_it_docs",
    "search_safety_docs",
    "search_user_files",
    "search_workspace_docs",
]


# ============================================================================
# 내부 검색 함수들
# ============================================================================

async def _search_hr_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """인사팀/교육 문서 검색. 채용, 인사이동, 평가, 복리후생, 휴가, 급여, 교육, 연수 관련."""
    try:
        start_time = time.time()
        svc = get_admin_chromadb_service()
        results = await svc.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_HR,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_hr_docs: {search_time}ms (query='{query[:50]}...', results={len(results)})", file=sys.stderr)

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


async def _search_ac_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """재경팀 문서 검색. 회계, 결산, 재무제표, 예산, 세무, 경비처리, 법인카드, SAP 관련."""
    try:
        start_time = time.time()
        svc = get_admin_chromadb_service()
        results = await svc.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_ACCOUNTING,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_ac_docs: {search_time}ms (query='{query[:50]}...', results={len(results)})", file=sys.stderr)

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


async def _search_it_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """IT팀 문서 검색. 시스템, 네트워크, 서버, ERP, 계정발급, 권한관리, 보안, 개인정보보호 관련."""
    try:
        start_time = time.time()
        svc = get_admin_chromadb_service()
        results = await svc.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_IT,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_it_docs: {search_time}ms (query='{query[:50]}...', results={len(results)})", file=sys.stderr)

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


async def _search_safety_docs(
    query: str,
    user_id: str = DEFAULT_ADMIN_USER,
    limit: int = 3
) -> str:
    """안전환경팀 문서 검색. 산업안전보건, 환경관리, 소방, 재해대응, 안전점검, ISO, 작업환경, 건강관리 관련."""
    try:
        start_time = time.time()
        svc = get_admin_chromadb_service()
        results = await svc.search(
            query=query,
            user_id=user_id,
            session_id=None,
            collection=COLLECTION_SAFETY,
            limit=limit,
            min_relevance=MIN_RELEVANCE_CORP
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_safety_docs: {search_time}ms (query='{query[:50]}...', results={len(results)})", file=sys.stderr)

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


async def _search_user_files(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    limit: int = 3
) -> str:
    """사용자가 업로드한 파일 검색. 파일 내용 질문 시 사용. session_id 필수."""
    try:
        start_time = time.time()
        svc = get_chromadb_service()
        results = await svc.search(
            query=query,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            min_relevance=MIN_RELEVANCE_USER
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_user_files: {search_time}ms (session={session_id[:8]}..., results={len(results)})", file=sys.stderr)

        if not results:
            return "업로드된 파일에서 관련 내용을 찾지 못했습니다."

        formatted_results = []
        for idx, result in enumerate(results, 1):
            filename = result.get('metadata', {}).get('filename', 'Unknown')
            text = result.get('text', '')
            similarity = result.get('similarity', 0)
            formatted_results.append(f"[파일 {idx}: {filename} (유사도: {similarity:.2f})]\n{text}\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"사용자 파일 검색 중 오류 발생: {str(e)}"


async def _search_workspace_docs(
    query: str,
    workspace_uuid: str,
    limit: int = 3
) -> str:
    """워크스페이스 문서 검색. workspace_uuid가 주어지면 최우선 사용."""
    try:
        start_time = time.time()
        svc = get_chromadb_service()
        collection_name = f"workspace_{workspace_uuid}"
        results = await svc.search(
            query=query,
            user_id="workspace_bot",
            session_id=None,
            collection=collection_name,
            limit=limit,
            min_relevance=MIN_RELEVANCE_WORKSPACE
        )
        search_time = int((time.time() - start_time) * 1000)
        print(f"[RAG_DIRECT] search_workspace_docs: {search_time}ms (workspace={workspace_uuid[:8]}..., results={len(results)})", file=sys.stderr)

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


# ============================================================================
# LangChain StructuredTool 정의
# ============================================================================

search_hr_docs = StructuredTool.from_function(
    coroutine=_search_hr_docs,
    name="search_hr_docs",
    description="인사팀/교육 문서 검색. 채용, 인사이동, 평가, 복리후생, 휴가, 급여, 교육, 연수 관련.",
)

search_ac_docs = StructuredTool.from_function(
    coroutine=_search_ac_docs,
    name="search_ac_docs",
    description="재경팀 문서 검색. 회계, 결산, 재무제표, 예산, 세무, 경비처리, 법인카드, SAP 관련.",
)

search_it_docs = StructuredTool.from_function(
    coroutine=_search_it_docs,
    name="search_it_docs",
    description="IT팀 문서 검색. 시스템, 네트워크, 서버, ERP, 계정발급, 권한관리, 보안, 개인정보보호 관련.",
)

search_safety_docs = StructuredTool.from_function(
    coroutine=_search_safety_docs,
    name="search_safety_docs",
    description="안전환경팀 문서 검색. 산업안전보건, 환경관리, 소방, 재해대응, 안전점검, ISO, 작업환경, 건강관리 관련.",
)

search_user_files = StructuredTool.from_function(
    coroutine=_search_user_files,
    name="search_user_files",
    description="사용자가 업로드한 파일 검색. 파일 내용 질문 시 사용. session_id 필수.",
)

search_workspace_docs = StructuredTool.from_function(
    coroutine=_search_workspace_docs,
    name="search_workspace_docs",
    description="워크스페이스 문서 검색. workspace_uuid가 주어지면 최우선 사용.",
)


# ============================================================================
# 도구 목록 반환 함수
# ============================================================================

def get_direct_rag_tools() -> List[StructuredTool]:
    """직접 호출 RAG 도구 목록 반환"""
    return [
        search_hr_docs,
        search_ac_docs,
        search_it_docs,
        search_safety_docs,
        search_user_files,
        search_workspace_docs,
    ]

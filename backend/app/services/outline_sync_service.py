# -*- coding: utf-8 -*-
"""Outline Wiki ↔ ChromaDB 시멘틱 검색 동기화 서비스

Outline 위키 문서를 청크 분할 → BGE-m3-ko 임베딩 → ChromaDB 저장.
Webhook 기반 단건 처리 + 폴백 delta sync.

ChromaDB 컬렉션: "outline_wiki" (단일 통합 컬렉션)
ChromaDB ID: "{document_id}_chunk_{index}"
메타데이터: document_id, collection_id, title, chunk_index, updated_at, url
"""

import os
import re
import sys
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple

import httpx

# ChromaDB 동기 작업을 비동기로 격리 (메인 이벤트 루프 블로킹 방지)
_sync_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="outline_sync_")

logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────
OUTLINE_API_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api")
OUTLINE_API_KEY = os.environ.get("OUTLINE_API_KEY", "")

# ChromaDB 컬렉션명
OUTLINE_COLLECTION_NAME = "outline_wiki"

# 청크 설정
CHUNK_SIZE = 600               # 청크 크기 (자)
CHUNK_OVERLAP = 100            # 오버랩 (문맥 연속성)
EMBED_BATCH_SIZE = 8           # GPU OOM 방지 소배치

# 배치 설정
BATCH_SIZE = 20                # Outline API 페이지 크기

# 한국어 문장 경계 분리자
KOREAN_SEPARATORS = [
    "\n\n",       # 단락
    "\n",         # 줄바꿈
    "다. ",       # 한국어 서술형
    "요. ",       # 한국어 존대
    "까? ",       # 한국어 의문
    "죠. ",       # 한국어 비격식 존대
    ". ",         # 일반 문장
    "! ",         # 감탄
    "? ",         # 의문
    ", ",         # 쉼표
    " ",          # 공백 (최후 수단)
]

# 마크다운 제거용 패턴
_MD_PATTERNS = [
    (re.compile(r'^#{1,6}\s+', re.MULTILINE), ''),       # 헤더 → 텍스트
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),                 # 볼드
    (re.compile(r'\*(.+?)\*'), r'\1'),                     # 이탤릭
    (re.compile(r'`{3}[\s\S]*?`{3}'), '[코드 블록]'),       # 코드 블록
    (re.compile(r'`(.+?)`'), r'\1'),                       # 인라인 코드
    (re.compile(r'!\[.*?\]\(.*?\)'), ''),                  # 이미지
    (re.compile(r'\[(.+?)\]\(.*?\)'), r'\1'),              # 링크 → 텍스트
    (re.compile(r'^\s*[-*+]\s+', re.MULTILINE), ''),       # 리스트 마커
    (re.compile(r'^\s*\d+\.\s+', re.MULTILINE), ''),       # 번호 리스트
    (re.compile(r'^\s*>\s?', re.MULTILINE), ''),           # 인용
    (re.compile(r'\|[^\n]*\|', re.MULTILINE), ''),         # 테이블 행
    (re.compile(r'---+'), ''),                             # 수평선
    (re.compile(r'\n{3,}'), '\n\n'),                       # 여러 빈 줄 정리
]

# 동기화 상태
_sync_status = {
    "running": False,
    "last_sync": None,
    "last_sync_time": None,    # delta sync 기준 타임스탬프
    "total_docs": 0,
    "synced_docs": 0,
    "errors": 0,
}


def _strip_markdown(text: str) -> str:
    """마크다운 구문을 제거하여 순수 텍스트로 변환"""
    for pattern, replacement in _MD_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _chunk_document(title: str, body: str) -> List[str]:
    """문서를 청크로 분할

    각 청크에 제목을 접두사로 붙여 임베딩 시 문서 맥락을 유지.

    Args:
        title: 문서 제목
        body: 문서 본문 (마크다운)

    Returns:
        청크 텍스트 리스트
    """
    # 마크다운 제거
    plain_text = _strip_markdown(body)

    if not plain_text.strip():
        return []

    # 본문이 짧으면 청크 분할 불필요
    title_prefix = f"# {title}\n\n"
    if len(plain_text) <= CHUNK_SIZE:
        return [f"{title_prefix}{plain_text}"]

    # RecursiveCharacterTextSplitter 사용 (한국어 분리자)
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=KOREAN_SEPARATORS,
        length_function=len,
    )
    chunks = splitter.split_text(plain_text)

    # 각 청크에 제목 접두사 추가
    return [f"{title_prefix}{chunk}" for chunk in chunks]


class OutlineSyncService:
    """Outline 위키 ↔ ChromaDB 동기화 서비스 (Webhook + 청크 기반)"""

    def __init__(self):
        self._chromadb_service = None

    @property
    def chromadb(self):
        if self._chromadb_service is None:
            from app.services.chromadb_service import get_chromadb_service
            self._chromadb_service = get_chromadb_service()
        return self._chromadb_service

    def _get_collection(self):
        """ChromaDB outline_wiki 컬렉션 가져오기"""
        return self.chromadb.get_collection(
            user_id="system",
            collection=OUTLINE_COLLECTION_NAME,
        )

    # ── Outline API 헬퍼 ──────────────────────────────────────

    async def _outline_request(self, endpoint: str, payload: dict) -> dict:
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
        except Exception as e:
            return {"error": str(e)[:300]}

    async def _fetch_document(self, document_id: str) -> Optional[dict]:
        """단일 문서 조회"""
        result = await self._outline_request("documents.info", {"id": document_id})
        if "error" in result:
            logger.error(f"[OutlineSync] 문서 조회 실패 ({document_id}): {result['error']}")
            return None
        return result.get("data")

    async def _fetch_all_documents(self) -> List[dict]:
        """Outline의 모든 published 문서를 페이지네이션으로 가져오기"""
        all_docs = []
        offset = 0

        while True:
            result = await self._outline_request("documents.list", {
                "limit": BATCH_SIZE,
                "offset": offset,
                "sort": "updatedAt",
                "direction": "DESC",
                "statusFilter": ["published"],
            })

            if "error" in result:
                logger.error(f"[OutlineSync] 문서 목록 조회 실패: {result['error']}")
                break

            docs = result.get("data", [])
            if not docs:
                break

            all_docs.extend(docs)
            offset += len(docs)

            # Outline API rate limit 보호
            await asyncio.sleep(0.2)

            logger.info(f"[OutlineSync] 문서 {len(all_docs)}건 로드 중...")

        return all_docs

    # ── 청크 기반 ChromaDB 동기화 ─────────────────────────────

    def _get_existing_doc_ids_sync(self) -> Set[str]:
        """ChromaDB에 저장된 고유 document_id 집합 조회 (동기)"""
        collection = self._get_collection()
        try:
            result = collection.get(include=["metadatas"])
        except Exception:
            return set()

        doc_ids = set()
        if result and result.get("metadatas"):
            for meta in result["metadatas"]:
                did = meta.get("document_id", "")
                if did:
                    doc_ids.add(did)
        return doc_ids

    def _get_existing_docs_metadata_sync(self) -> Dict[str, str]:
        """ChromaDB 기존 문서의 document_id → updated_at 매핑 (동기)"""
        collection = self._get_collection()
        try:
            result = collection.get(include=["metadatas"])
        except Exception:
            return {}

        doc_updated: Dict[str, str] = {}
        if result and result.get("metadatas"):
            for meta in result["metadatas"]:
                did = meta.get("document_id", "")
                updated = meta.get("updated_at", "")
                if did and updated:
                    # 같은 document_id의 청크가 여러 개 → 하나만 기록
                    if did not in doc_updated:
                        doc_updated[did] = updated
        return doc_updated

    def _delete_document_chunks_sync(self, document_id: str) -> int:
        """특정 문서의 모든 청크를 ChromaDB에서 삭제 (동기)

        Returns:
            삭제된 청크 수
        """
        collection = self._get_collection()
        try:
            result = collection.get(
                where={"document_id": document_id},
                include=[],
            )
            if result and result.get("ids"):
                chunk_ids = result["ids"]
                collection.delete(ids=chunk_ids)
                return len(chunk_ids)
        except Exception as e:
            logger.error(f"[OutlineSync] 청크 삭제 실패 ({document_id}): {e}")
        return 0

    def _upsert_chunks_sync(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[dict],
    ):
        """청크를 ChromaDB에 upsert (동기)"""
        collection = self._get_collection()
        # 소배치로 나눠서 upsert (GPU 메모리 보호)
        for i in range(0, len(ids), EMBED_BATCH_SIZE):
            batch_ids = ids[i:i + EMBED_BATCH_SIZE]
            batch_docs = documents[i:i + EMBED_BATCH_SIZE]
            batch_metas = metadatas[i:i + EMBED_BATCH_SIZE]
            collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
            )

    async def process_single_document(
        self,
        document_id: str,
        event_type: str,
    ) -> dict:
        """단일 문서를 처리 (webhook에서 호출)

        Args:
            document_id: Outline 문서 ID
            event_type: 이벤트 유형 (documents.create/update/publish/delete/archive)

        Returns:
            처리 결과 dict
        """
        loop = asyncio.get_event_loop()

        # 삭제/보관 이벤트
        if event_type in ("documents.delete", "documents.archive"):
            deleted = await loop.run_in_executor(
                _sync_executor,
                self._delete_document_chunks_sync, document_id,
            )
            logger.info(f"[OutlineSync] 문서 삭제 처리: {document_id}, 청크 {deleted}개 제거")
            return {"action": "delete", "document_id": document_id, "chunks_deleted": deleted}

        # 문서 조회
        doc = await self._fetch_document(document_id)
        if not doc:
            return {"action": "skip", "document_id": document_id, "reason": "문서 조회 실패"}

        title = doc.get("title", "제목 없음")
        body = doc.get("text", "")

        # 청크 분할
        chunks = _chunk_document(title, body)
        if not chunks:
            # 본문 없는 문서 → 기존 청크 정리
            await loop.run_in_executor(
                _sync_executor,
                self._delete_document_chunks_sync, document_id,
            )
            return {"action": "skip", "document_id": document_id, "reason": "본문 없음"}

        # 기존 청크 삭제
        await loop.run_in_executor(
            _sync_executor,
            self._delete_document_chunks_sync, document_id,
        )

        # 새 청크 생성
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "collection_id": doc.get("collectionId", ""),
                "title": title,
                "chunk_index": i,
                "updated_at": doc.get("updatedAt", ""),
                "created_at": doc.get("createdAt", ""),
                "url": doc.get("url", ""),
            }
            for i in range(len(chunks))
        ]

        # ChromaDB upsert (소배치, 스레드풀에서 실행)
        await loop.run_in_executor(
            _sync_executor,
            self._upsert_chunks_sync, ids, chunks, metadatas,
        )

        logger.info(f"[OutlineSync] 문서 처리 완료: '{title}' → 청크 {len(chunks)}개")
        return {
            "action": "upsert",
            "document_id": document_id,
            "title": title,
            "chunks": len(chunks),
        }

    # ── 전체 동기화 (초기 적재 / 폴백) ───────────────────────

    async def full_sync(self) -> dict:
        """전체 동기화 (초기 적재 또는 수동 실행)"""
        global _sync_status
        if _sync_status["running"]:
            return {"error": "동기화가 이미 실행 중입니다.", "status": _sync_status}

        _sync_status["running"] = True
        _sync_status["synced_docs"] = 0
        _sync_status["errors"] = 0
        start = time.time()

        try:
            logger.info("[OutlineSync] ===== 전체 동기화 시작 =====")

            # 1. Outline 전체 문서 가져오기
            all_docs = await self._fetch_all_documents()
            _sync_status["total_docs"] = len(all_docs)
            logger.info(f"[OutlineSync] Outline 문서 {len(all_docs)}건 로드 완료")

            if not all_docs:
                return {"message": "동기화할 문서가 없습니다.", "total": 0}

            # 2. ChromaDB 기존 데이터 조회 (변경 감지)
            loop = asyncio.get_event_loop()
            existing = await loop.run_in_executor(
                _sync_executor,
                self._get_existing_docs_metadata_sync,
            )
            logger.info(f"[OutlineSync] ChromaDB 기존 문서 {len(existing)}건")

            # 3. 문서별 처리
            total_synced = 0
            total_errors = 0
            total_chunks = 0

            for doc in all_docs:
                doc_id = doc.get("id", "")
                updated_at = doc.get("updatedAt", "")

                if not doc_id:
                    continue

                # 변경 감지: updated_at 비교
                if doc_id in existing and existing[doc_id] == updated_at:
                    continue  # 변경 없음 → 스킵

                try:
                    result = await self.process_single_document(doc_id, "documents.update")
                    if result.get("action") == "upsert":
                        total_synced += 1
                        total_chunks += result.get("chunks", 0)
                    _sync_status["synced_docs"] = total_synced
                except Exception as e:
                    logger.error(f"[OutlineSync] 문서 처리 실패 ({doc_id}): {e}")
                    total_errors += 1
                    _sync_status["errors"] = total_errors

                # 이벤트 루프에 양보
                await asyncio.sleep(0.05)

                if total_synced % 10 == 0 and total_synced > 0:
                    logger.info(f"[OutlineSync] 진행: {total_synced}건 처리, 청크 {total_chunks}개")

            # 4. 삭제된 문서 정리
            outline_ids = {doc["id"] for doc in all_docs if doc.get("id")}
            existing_ids = await loop.run_in_executor(
                _sync_executor,
                self._get_existing_doc_ids_sync,
            )
            orphan_ids = existing_ids - outline_ids
            deleted = 0
            for orphan_id in orphan_ids:
                try:
                    d = await loop.run_in_executor(
                        _sync_executor,
                        self._delete_document_chunks_sync, orphan_id,
                    )
                    deleted += d
                except Exception as e:
                    logger.error(f"[OutlineSync] 고아 문서 삭제 실패 ({orphan_id}): {e}")

            if deleted:
                logger.info(f"[OutlineSync] 삭제된 문서 청크 {deleted}개 제거")

            elapsed = time.time() - start
            result = {
                "message": "동기화 완료",
                "total_outline_docs": len(all_docs),
                "synced": total_synced,
                "total_chunks": total_chunks,
                "skipped": len(all_docs) - total_synced - total_errors,
                "deleted_chunks": deleted,
                "errors": total_errors,
                "elapsed_seconds": round(elapsed, 1),
            }

            _sync_status["last_sync"] = datetime.now(timezone.utc).isoformat()
            _sync_status["last_sync_time"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"[OutlineSync] ===== 동기화 완료: {result} =====")
            return result

        except Exception as e:
            logger.error(f"[OutlineSync] 전체 동기화 실패: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            _sync_status["running"] = False

    async def delta_sync(self) -> dict:
        """증분 동기화: last_sync 이후 변경된 문서만 처리 (폴백용)"""
        global _sync_status
        if _sync_status["running"]:
            return {"error": "동기화가 이미 실행 중입니다."}

        _sync_status["running"] = True
        start = time.time()

        try:
            logger.info("[OutlineSync] ===== Delta sync 시작 =====")

            # last_sync 이후 변경된 문서만 가져오기 (최신순)
            result = await self._outline_request("documents.list", {
                "limit": 100,
                "offset": 0,
                "sort": "updatedAt",
                "direction": "DESC",
                "statusFilter": ["published"],
            })

            if "error" in result:
                return {"error": result["error"]}

            docs = result.get("data", [])
            if not docs:
                _sync_status["last_sync_time"] = datetime.now(timezone.utc).isoformat()
                return {"message": "변경된 문서 없음", "synced": 0}

            # 기존 ChromaDB 메타데이터와 비교
            loop = asyncio.get_event_loop()
            existing = await loop.run_in_executor(
                _sync_executor,
                self._get_existing_docs_metadata_sync,
            )

            synced = 0
            for doc in docs:
                doc_id = doc.get("id", "")
                updated_at = doc.get("updatedAt", "")
                if not doc_id:
                    continue

                # 변경 없으면 스킵 (이후 문서는 더 오래된 것이므로 중단)
                if doc_id in existing and existing[doc_id] == updated_at:
                    break

                try:
                    await self.process_single_document(doc_id, "documents.update")
                    synced += 1
                except Exception as e:
                    logger.error(f"[OutlineSync] Delta sync 문서 처리 실패 ({doc_id}): {e}")

                await asyncio.sleep(0.05)

            elapsed = time.time() - start
            _sync_status["last_sync_time"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"[OutlineSync] ===== Delta sync 완료: {synced}건, {elapsed:.1f}초 =====")
            return {"message": "delta sync 완료", "synced": synced, "elapsed_seconds": round(elapsed, 1)}

        except Exception as e:
            logger.error(f"[OutlineSync] Delta sync 실패: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            _sync_status["running"] = False

    # ── 시멘틱 검색 ───────────────────────────────────────────

    def _semantic_search_sync(
        self,
        query: str,
        n_results: int = 5,
        collection_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        """ChromaDB 시멘틱 검색 — 청크 단위 매칭 → 문서 단위 그룹핑 (동기)"""
        collection = self._get_collection()

        try:
            where_filter = None
            if collection_ids:
                where_filter = {
                    "collection_id": {"$in": collection_ids}
                }

            # 청크 단위 검색 (문서당 여러 청크가 매칭될 수 있으므로 여유 있게)
            result = collection.query(
                query_texts=[query],
                n_results=n_results * 3,
                where=where_filter,
                include=["metadatas", "distances", "documents"],
            )
        except Exception as e:
            logger.error(f"[OutlineSync] 시멘틱 검색 실패: {e}")
            return []

        if not result or not result.get("ids") or not result["ids"][0]:
            return []

        # 청크 → 문서 그룹핑
        doc_best: Dict[str, dict] = {}     # document_id → 최고 스코어 정보
        doc_chunks: Dict[str, List[str]] = {}  # document_id → 매칭 청크 텍스트

        for i, chunk_id in enumerate(result["ids"][0]):
            meta = result["metadatas"][0][i] if result.get("metadatas") else {}
            distance = result["distances"][0][i] if result.get("distances") else 1.0
            chunk_text = result["documents"][0][i] if result.get("documents") else ""
            score = max(0, 1 - distance)

            doc_id = meta.get("document_id", chunk_id)

            # 청크 텍스트 수집
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
            # 제목 접두사 제거하고 저장
            clean_text = chunk_text
            title_prefix = f"# {meta.get('title', '')}\n\n"
            if clean_text.startswith(title_prefix):
                clean_text = clean_text[len(title_prefix):]
            doc_chunks[doc_id].append(clean_text)

            # 최고 스코어 기록
            if doc_id not in doc_best or score > doc_best[doc_id]["score"]:
                doc_best[doc_id] = {
                    "document_id": doc_id,
                    "collection_id": meta.get("collection_id", ""),
                    "title": meta.get("title", ""),
                    "url": meta.get("url", ""),
                    "updated_at": meta.get("updated_at", ""),
                    "score": round(score, 4),
                }

        # 문서별 결과 생성 (스코어 순 정렬)
        hits = []
        for doc_id in sorted(doc_best, key=lambda x: doc_best[x]["score"], reverse=True):
            entry = doc_best[doc_id]
            # 매칭된 청크 중 상위 2개를 snippet으로 조합
            chunks = doc_chunks.get(doc_id, [])
            entry["snippet"] = "\n---\n".join(chunks[:2])
            entry["matched_chunks"] = len(chunks)
            hits.append(entry)

        return hits[:n_results]

    async def semantic_search(
        self,
        query: str,
        n_results: int = 5,
        collection_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        """ChromaDB 시멘틱 검색 (스레드풀에서 실행, 이벤트 루프 비블로킹)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _sync_executor,
            self._semantic_search_sync, query, n_results, collection_ids,
        )

    # ── 상태 조회 ─────────────────────────────────────────────

    def get_sync_status(self) -> dict:
        """현재 동기화 상태 반환"""
        return dict(_sync_status)


# ── 싱글톤 ────────────────────────────────────────────────────
_outline_sync_service: Optional[OutlineSyncService] = None


def get_outline_sync_service() -> OutlineSyncService:
    global _outline_sync_service
    if _outline_sync_service is None:
        _outline_sync_service = OutlineSyncService()
    return _outline_sync_service

# -*- coding: utf-8 -*-
"""Outline Wiki ↔ ChromaDB 시멘틱 검색 동기화 서비스

Outline 위키 문서를 Haiku로 요약 → BGE-m3-ko 임베딩 → ChromaDB 저장.
주기적 증분 동기화(delta sync)로 변경분만 갱신.

ChromaDB 컬렉션: "outline_wiki" (단일 통합 컬렉션)
메타데이터: document_id, collection_id, title, summary, updated_at
"""

import os
import sys
import json
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

# 요약 설정
SUMMARY_TEXT_INPUT_MAX = 3000      # Haiku에 보낼 본문 최대 길이
SUMMARY_MAX_LENGTH = 300           # 요약 최대 길이
EMBED_TEXT_MAX = 800               # 임베딩 대상 텍스트 최대 길이 (제목+요약)

# 배치 설정
BATCH_SIZE = 20                    # Outline API 페이지 크기
EMBED_BATCH_SIZE = 32              # 임베딩 배치 크기
HAIKU_CONCURRENCY = 5              # Haiku 동시 요약 수

# 동기화 상태
_sync_status = {
    "running": False,
    "last_sync": None,
    "total_docs": 0,
    "synced_docs": 0,
    "errors": 0,
}

# ── 요약 프롬프트 ─────────────────────────────────────────────
WIKI_SUMMARY_PROMPT = """다음 위키 문서의 내용을 200~300자 이내로 요약하세요.

## 문서 제목
{title}

## 문서 본문
{body}

## 요약 규칙
1. 이 문서가 무엇에 대한 것인지, 핵심 내용이 무엇인지 명확히 전달
2. 기술 용어, 고유명사, 제품명은 반드시 포함
3. 절차/단계가 있으면 핵심 단계만 언급
4. 200~300자 이내, 한국어, 평서문
5. "이 문서는" 같은 메타 표현 없이 바로 내용 요약

요약:"""


class OutlineSyncService:
    """Outline 위키 ↔ ChromaDB 동기화 서비스"""

    def __init__(self):
        self._chromadb_service = None
        self._bedrock_service = None
        self._semaphore = asyncio.Semaphore(HAIKU_CONCURRENCY)

    @property
    def chromadb(self):
        if self._chromadb_service is None:
            from app.services.chromadb_service import get_chromadb_service
            self._chromadb_service = get_chromadb_service()
        return self._chromadb_service

    @property
    def bedrock(self):
        if self._bedrock_service is None:
            from app.services.bedrock_service import BedrockService
            self._bedrock_service = BedrockService()
        return self._bedrock_service

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

    # ── Haiku 요약 ────────────────────────────────────────────

    async def _call_haiku_safe(self, prompt: str, max_tokens: int = 500, temperature: float = 0.2) -> str:
        """generate_text_haiku 래퍼 — boto3 동기 호출을 executor로 격리
        (VOC 위키 서비스와 동일 패턴: 이벤트 루프 블로킹 방지)
        """
        loop = asyncio.get_event_loop()

        def _sync_call():
            import json as _json
            bedrock = self.bedrock
            haiku_model_id = os.getenv(
                "BEDROCK_FALLBACK_MODEL_ID",
                "us.anthropic.claude-haiku-4-5-20251001-v1:0"
            )
            effective_model_id = bedrock._get_model_id(haiku_model_id)

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": prompt}]}
                ]
            }

            logger.info(f"[OutlineSync] Calling Haiku: {effective_model_id}")
            response = bedrock.client.invoke_model(
                modelId=effective_model_id,
                body=_json.dumps(request_body)
            )
            response_body = _json.loads(response['body'].read())

            if 'content' in response_body and len(response_body['content']) > 0:
                return response_body['content'][0]['text']
            return ""

        return await loop.run_in_executor(_sync_executor, _sync_call)

    async def _summarize_document(self, title: str, body: str) -> str:
        """Haiku로 문서 요약 생성 (세마포어로 동시성 제한)"""
        # 본문이 너무 짧으면 요약 불필요
        if len(body.strip()) < 50:
            return body.strip()[:SUMMARY_MAX_LENGTH]

        prompt = WIKI_SUMMARY_PROMPT.format(
            title=title,
            body=body[:SUMMARY_TEXT_INPUT_MAX],
        )

        async with self._semaphore:
            try:
                summary = await self._call_haiku_safe(
                    prompt=prompt,
                    max_tokens=500,
                    temperature=0.2,
                )
                return summary.strip()[:SUMMARY_MAX_LENGTH]
            except Exception as e:
                logger.error(f"[OutlineSync] 요약 실패 ({title}): {e}")
                # 폴백: 본문 앞부분
                return body.strip()[:SUMMARY_MAX_LENGTH]

    # ── ChromaDB 동기화 ───────────────────────────────────────

    def _get_existing_docs_sync(self) -> Dict[str, dict]:
        """ChromaDB에 저장된 기존 문서 메타데이터 조회 (동기, 스레드풀에서 호출)"""
        collection = self._get_collection()
        try:
            result = collection.get(include=["metadatas"])
        except Exception:
            return {}

        existing = {}
        if result and result.get("ids"):
            for i, doc_id in enumerate(result["ids"]):
                meta = result["metadatas"][i] if result.get("metadatas") else {}
                existing[doc_id] = meta

        return existing

    async def _get_existing_docs(self) -> Dict[str, dict]:
        """ChromaDB 기존 문서 조회 (스레드풀에서 실행, 이벤트 루프 비블로킹)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_sync_executor, self._get_existing_docs_sync)

    async def _sync_batch(
        self,
        docs: List[dict],
        existing: Dict[str, dict],
    ) -> Tuple[int, int]:
        """문서 배치를 요약 + 임베딩 + ChromaDB 저장

        Returns:
            (synced_count, error_count)
        """
        # 변경 감지: updated_at 비교
        to_sync = []
        for doc in docs:
            doc_id = doc.get("id", "")
            updated_at = doc.get("updatedAt", "")

            if not doc_id:
                continue

            existing_meta = existing.get(doc_id)
            if existing_meta and existing_meta.get("updated_at") == updated_at:
                continue  # 변경 없음 → 스킵

            to_sync.append(doc)

        if not to_sync:
            return 0, 0

        # Haiku 요약 병렬 생성
        summaries = await asyncio.gather(*[
            self._summarize_document(
                doc.get("title", ""),
                doc.get("text", ""),
            )
            for doc in to_sync
        ], return_exceptions=True)

        # ChromaDB에 upsert
        ids = []
        documents = []
        metadatas = []
        errors = 0

        for i, doc in enumerate(to_sync):
            summary = summaries[i]
            if isinstance(summary, Exception):
                logger.error(f"[OutlineSync] 요약 예외 ({doc.get('title')}): {summary}")
                errors += 1
                # 폴백: 본문 앞부분
                summary = (doc.get("text", "") or "")[:SUMMARY_MAX_LENGTH]

            doc_id = doc["id"]
            title = doc.get("title", "제목 없음")
            embed_text = f"# {title}\n\n{summary}"

            ids.append(doc_id)
            documents.append(embed_text[:EMBED_TEXT_MAX])
            metadatas.append({
                "document_id": doc_id,
                "collection_id": doc.get("collectionId", ""),
                "title": title,
                "summary": summary,
                "updated_at": doc.get("updatedAt", ""),
                "created_at": doc.get("createdAt", ""),
                "url": doc.get("url", ""),
            })

        if ids:
            try:
                # ChromaDB upsert를 스레드풀에서 실행 (임베딩 포함, 이벤트 루프 블로킹 방지)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    _sync_executor,
                    self._upsert_sync, ids, documents, metadatas,
                )
                logger.info(f"[OutlineSync] {len(ids)}건 upsert 완료")
            except Exception as e:
                logger.error(f"[OutlineSync] ChromaDB upsert 실패: {e}")
                errors += len(ids)
                return 0, errors

        return len(ids) - errors, errors

    def _upsert_sync(self, ids: list, documents: list, metadatas: list):
        """ChromaDB upsert (동기, 스레드풀에서 호출)"""
        collection = self._get_collection()
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def _delete_sync(self, ids: list):
        """ChromaDB delete (동기, 스레드풀에서 호출)"""
        collection = self._get_collection()
        collection.delete(ids=ids)

    async def _remove_deleted_docs(
        self, outline_ids: Set[str], existing: Dict[str, dict]
    ) -> int:
        """Outline에 없는 문서를 ChromaDB에서 제거"""
        to_delete = [
            doc_id for doc_id in existing
            if doc_id not in outline_ids
        ]

        if not to_delete:
            return 0

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_sync_executor, self._delete_sync, to_delete)
            logger.info(f"[OutlineSync] 삭제된 문서 {len(to_delete)}건 제거")
            return len(to_delete)
        except Exception as e:
            logger.error(f"[OutlineSync] ChromaDB 삭제 실패: {e}")
            return 0

    # ── 전체 동기화 ───────────────────────────────────────────

    async def full_sync(self) -> dict:
        """전체 동기화 (초기 또는 수동 실행)

        Returns:
            동기화 결과 요약 dict
        """
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

            # 2. ChromaDB 기존 데이터 조회 (스레드풀에서 실행)
            existing = await self._get_existing_docs()
            logger.info(f"[OutlineSync] ChromaDB 기존 {len(existing)}건")

            # 3. 배치별 동기화
            total_synced = 0
            total_errors = 0

            for i in range(0, len(all_docs), BATCH_SIZE):
                batch = all_docs[i:i + BATCH_SIZE]
                synced, errors = await self._sync_batch(batch, existing)
                total_synced += synced
                total_errors += errors
                _sync_status["synced_docs"] = total_synced
                _sync_status["errors"] = total_errors
                logger.info(f"[OutlineSync] 진행: {total_synced}/{len(all_docs)} (에러 {total_errors})")
                # 이벤트 루프에 양보 (다른 요청 처리 가능)
                await asyncio.sleep(0.1)

            # 4. 삭제된 문서 정리
            outline_ids = {doc["id"] for doc in all_docs if doc.get("id")}
            deleted = await self._remove_deleted_docs(outline_ids, existing)

            elapsed = time.time() - start
            result = {
                "message": "동기화 완료",
                "total_outline_docs": len(all_docs),
                "synced": total_synced,
                "skipped": len(all_docs) - total_synced - total_errors,
                "deleted": deleted,
                "errors": total_errors,
                "elapsed_seconds": round(elapsed, 1),
            }

            _sync_status["last_sync"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"[OutlineSync] ===== 동기화 완료: {result} =====")
            return result

        except Exception as e:
            logger.error(f"[OutlineSync] 전체 동기화 실패: {e}", exc_info=True)
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
        """ChromaDB 시멘틱 검색 (동기, 스레드풀에서 호출)"""
        collection = self._get_collection()

        try:
            where_filter = None
            if collection_ids:
                where_filter = {
                    "collection_id": {"$in": collection_ids}
                }

            result = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
                include=["metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"[OutlineSync] 시멘틱 검색 실패: {e}")
            return []

        if not result or not result.get("ids") or not result["ids"][0]:
            return []

        hits = []
        for i, doc_id in enumerate(result["ids"][0]):
            meta = result["metadatas"][0][i] if result.get("metadatas") else {}
            distance = result["distances"][0][i] if result.get("distances") else 1.0
            score = max(0, 1 - distance)

            hits.append({
                "document_id": meta.get("document_id", doc_id),
                "collection_id": meta.get("collection_id", ""),
                "title": meta.get("title", ""),
                "summary": meta.get("summary", ""),
                "url": meta.get("url", ""),
                "updated_at": meta.get("updated_at", ""),
                "score": round(score, 4),
            })

        return hits

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
        """현재 동기화 상태 반환 (ChromaDB 접근 없이 빠르게)"""
        return dict(_sync_status)


# ── 싱글톤 ────────────────────────────────────────────────────
_outline_sync_service: Optional[OutlineSyncService] = None


def get_outline_sync_service() -> OutlineSyncService:
    global _outline_sync_service
    if _outline_sync_service is None:
        _outline_sync_service = OutlineSyncService()
    return _outline_sync_service

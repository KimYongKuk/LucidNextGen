"""
BM25 + Semantic 하이브리드 검색 서비스

- BM25Okapi 키워드 검색으로 시멘틱 서치의 코드/식별자 검색 약점 보완
- Reciprocal Rank Fusion (RRF) 으로 두 결과를 합산
- 컬렉션별 BM25 인덱스 캐싱 (TTL + count 기반 자동 무효화)
"""

import re
import sys
import time
import threading
from typing import Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi


# ── 환경변수로 가중치 오버라이드 가능 ───────────────────
import os

HYBRID_SEMANTIC_WEIGHT = float(os.getenv("HYBRID_SEMANTIC_WEIGHT", "0.5"))
HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", "0.5"))
HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))
BM25_CACHE_TTL = int(os.getenv("BM25_CACHE_TTL", "300"))  # seconds


# ── 토크나이저 ──────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    """한국어 + 영문/숫자 코드를 위한 토크나이저

    - PP2509-138 같은 코드를 통째로 토큰 유지
    - 한글 단어 분리
    - 모두 소문자 변환
    """
    tokens = re.findall(
        r'[A-Za-z0-9][\w\-\.]*[A-Za-z0-9]|[가-힣]+|\w+',
        text,
    )
    return [t.lower() for t in tokens]


# ── BM25 인덱스 ────────────────────────────────────────

class BM25Index:
    """단일 컬렉션에 대한 BM25 인덱스."""

    def __init__(self, documents: List[str]):
        self.documents = documents
        self.count = len(documents)
        self.created_at = time.time()

        tokenized = [tokenize(doc) for doc in documents]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int) -> List[Tuple[int, float]]:
        """BM25 검색. (doc_index, score) 리스트 반환 (점수 내림차순)."""
        query_tokens = tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        return [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]


# ── BM25 캐시 매니저 ───────────────────────────────────

class BM25CacheManager:
    """스레드 안전한 BM25 인덱스 캐시. collection_name + count로 무효화."""

    def __init__(self):
        self._cache: Dict[str, BM25Index] = {}
        self._lock = threading.Lock()

    def get_or_build(
        self,
        collection_name: str,
        collection_count: int,
        documents: List[str],
    ) -> BM25Index:
        """캐시에서 가져오거나 새로 빌드. 스레드 안전."""
        with self._lock:
            cached = self._cache.get(collection_name)
            if cached is not None:
                age = time.time() - cached.created_at
                if cached.count == collection_count and age < BM25_CACHE_TTL:
                    return cached

            t0 = time.time()
            index = BM25Index(documents)
            self._cache[collection_name] = index
            elapsed = time.time() - t0
            print(
                f"[BM25] Built index for '{collection_name}': "
                f"{len(documents)} docs in {elapsed:.3f}s",
                file=sys.stderr,
            )
            return index

    def invalidate(self, collection_name: str):
        """컬렉션 캐시 명시적 무효화 (업로드/삭제 시 호출)."""
        with self._lock:
            self._cache.pop(collection_name, None)


# 모듈 레벨 싱글턴
_bm25_cache = BM25CacheManager()


def get_bm25_cache() -> BM25CacheManager:
    return _bm25_cache


# ── RRF 합산 ───────────────────────────────────────────

def _doc_key(text: str) -> str:
    """문서 중복 제거용 키 (앞 200자)."""
    return text[:200]


def reciprocal_rank_fusion(
    semantic_results: List[Dict],
    bm25_results: List[Tuple[int, float]],
    all_documents: List[str],
    all_metadatas: List[Dict],
    limit: int,
    min_relevance: float = 0.0,
    semantic_weight: Optional[float] = None,
    bm25_weight: Optional[float] = None,
    k: Optional[int] = None,
) -> List[Dict]:
    """시멘틱 + BM25 결과를 RRF로 합산.

    반환 형식: [{"text", "metadata", "similarity", "hybrid_score"}]
    chromadb_service의 기존 반환 형식과 호환.
    """
    sw = semantic_weight if semantic_weight is not None else HYBRID_SEMANTIC_WEIGHT
    bw = bm25_weight if bm25_weight is not None else HYBRID_BM25_WEIGHT
    rrf_k = k if k is not None else HYBRID_RRF_K

    doc_scores: Dict[str, Dict] = {}

    # 시멘틱 결과 처리
    for rank, result in enumerate(semantic_results):
        key = _doc_key(result["text"])
        rrf = sw * (1 / (rrf_k + rank + 1))
        if key not in doc_scores:
            doc_scores[key] = {
                "text": result["text"],
                "metadata": result["metadata"],
                "similarity": result["similarity"],
                "rrf": 0.0,
                "from_semantic": True,
                "from_bm25": False,
            }
        doc_scores[key]["rrf"] += rrf

    # BM25 결과 처리
    for rank, (doc_idx, bm25_score) in enumerate(bm25_results):
        doc_text = all_documents[doc_idx]
        key = _doc_key(doc_text)
        rrf = bw * (1 / (rrf_k + rank + 1))
        if key not in doc_scores:
            doc_scores[key] = {
                "text": doc_text,
                "metadata": all_metadatas[doc_idx] if doc_idx < len(all_metadatas) else {},
                "similarity": 0.0,
                "rrf": 0.0,
                "from_semantic": False,
                "from_bm25": True,
            }
        else:
            doc_scores[key]["from_bm25"] = True
        doc_scores[key]["rrf"] += rrf

    # RRF 점수 내림차순 정렬
    ranked = sorted(doc_scores.values(), key=lambda x: x["rrf"], reverse=True)

    # min_relevance 필터:
    #   - 시멘틱에서 온 결과: 기존처럼 cosine similarity로 필터
    #   - BM25에서만 온 결과: 키워드 정확 매칭이므로 통과 (이게 핵심)
    filtered = []
    for r in ranked:
        if min_relevance > 0:
            if r["from_semantic"] and r["similarity"] < min_relevance and not r["from_bm25"]:
                continue

        filtered.append({
            "text": r["text"],
            "metadata": r["metadata"],
            "similarity": round(r["similarity"], 3),
        })
        if len(filtered) >= limit:
            break

    return filtered

# -*- coding: utf-8 -*-
"""User Directory Service — 사번 ↔ 이름/부서 매핑

TIMS PostgreSQL v_user_info_mapping + v_org_chart 활용.
- 백엔드 startup 시 1회 fetch → in-memory cache
- 24시간마다 자동 갱신 (또는 수동 refresh)
- 동기 lookup 제공 (다른 서비스에서 sync 컨텍스트로 호출 가능)
"""
import os
import time
import asyncio
import logging
from typing import Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)

TIMS_DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "")
CACHE_TTL_SEC = 24 * 3600  # 24시간

# in-memory: { user_id (사번): { name, team, position } }
_cache: Dict[str, Dict[str, str]] = {}
_loaded_at: float = 0.0


async def refresh_cache() -> int:
    """v_org_chart에서 사번/이름/부서 전체 fetch → 캐시 갱신.

    반환: 캐시된 사용자 수.
    호출 위치: main.py startup, 또는 24h 주기 task.
    """
    global _cache, _loaded_at

    if not TIMS_DATABASE_URL:
        logger.warning("[UserDirectory] TIMS_DATABASE_URL 미설정 — 캐시 비움")
        _cache = {}
        return 0

    try:
        conn = await asyncpg.connect(TIMS_DATABASE_URL)
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT user_id, 이름 AS name, 부서 AS team, 직책 AS position
                FROM v_org_chart
                WHERE user_id IS NOT NULL AND 이름 IS NOT NULL
                """
            )
        finally:
            await conn.close()

        new_cache = {}
        for r in rows:
            uid = str(r["user_id"])
            new_cache[uid] = {
                "name": r["name"] or "",
                "team": r["team"] or "",
                "position": r["position"] or "",
            }
        _cache = new_cache
        _loaded_at = time.time()
        logger.info(f"[UserDirectory] cached {len(_cache)} users from v_org_chart")
        return len(_cache)
    except Exception as e:
        logger.error(f"[UserDirectory] refresh failed: {e}")
        return 0


def get_user_info(user_id: Optional[str]) -> Optional[Dict[str, str]]:
    """사번 → {name, team, position} 동기 lookup.

    캐시 미스 시 None 반환. 캐시는 startup에서 채워짐.
    """
    if not user_id:
        return None
    return _cache.get(str(user_id))


def get_name(user_id: Optional[str]) -> str:
    """사번 → 이름 (없으면 사번 그대로 반환 — fallback)"""
    info = get_user_info(user_id)
    if info and info.get("name"):
        return info["name"]
    return user_id or ""


def is_cache_stale() -> bool:
    return time.time() - _loaded_at > CACHE_TTL_SEC


def cache_size() -> int:
    return len(_cache)

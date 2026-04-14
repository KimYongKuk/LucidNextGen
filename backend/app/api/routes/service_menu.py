"""서비스 메뉴 API 라우터

그룹웨어 플로팅 위젯에서 사용할 서비스 메뉴 목록을 반환합니다.
사번 → PostgreSQL(go_users → go_companies) → 소속 조직 판별 → MySQL(service_menu) 필터링
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import asyncpg
import json

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)
router = APIRouter()

# PostgreSQL 연결 (그룹웨어 DB — 조직 조회용)
PG_DATABASE_URL = "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"
_pg_pool: Optional[asyncpg.Pool] = None

# 사번 → 조직명 캐시 (프로세스 수명)
_company_cache: dict[str, str] = {}


async def _get_pg_pool() -> asyncpg.Pool:
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = await asyncpg.create_pool(
            PG_DATABASE_URL, min_size=1, max_size=3, command_timeout=10
        )
    return _pg_pool


async def _get_company_name(empno: str) -> Optional[str]:
    """사번으로 소속 회사명 조회 (캐시 적용)"""
    if empno in _company_cache:
        return _company_cache[empno]

    try:
        pool = await _get_pg_pool()
        row = await pool.fetchrow(
            """
            SELECT c.name
            FROM go_users u
            JOIN go_companies c ON u.company_id = c.id
            WHERE u.employee_number = $1
              AND u.deleted_at IS NULL
            """,
            empno,
        )
        if row:
            company_name = row["name"]
            _company_cache[empno] = company_name
            logger.info(f"[ServiceMenu] empno={empno} → company={company_name}")
            return company_name
        else:
            logger.warning(f"[ServiceMenu] empno={empno} not found in go_users")
            return None
    except Exception as e:
        logger.error(f"[ServiceMenu] PG query failed: {e}")
        return None


@router.get("/v1/service-menu")
async def get_service_menu(empno: str = Query(..., description="사번")):
    """사번에 해당하는 조직의 서비스 메뉴 목록 반환"""
    company_name = await _get_company_name(empno)
    if not company_name:
        raise HTTPException(status_code=404, detail="사번에 해당하는 조직을 찾을 수 없습니다")

    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, name, icon, target_url, orgs, sort_order "
            "FROM service_menu "
            "WHERE enabled = 1 "
            "ORDER BY sort_order"
        )
        rows = cursor.fetchall()

    menus = []
    for row in rows:
        orgs = row["orgs"]
        if isinstance(orgs, str):
            orgs = json.loads(orgs)
        if company_name in orgs:
            menus.append({
                "id": row["id"],
                "name": row["name"],
                "icon": row["icon"],
                "url": row["target_url"],
            })

    return {"company": company_name, "menus": menus}
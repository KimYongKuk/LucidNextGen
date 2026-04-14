"""서비스 메뉴 API 라우터

그룹웨어 플로팅 위젯에서 사용할 서비스 메뉴 목록을 반환합니다.
사번 → PostgreSQL(v_user_info_mapping + v_org_chart) → 소속 조직 판별 → MySQL(service_menu) 필터링
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

# 부서경로 2번째 ID → 회사명 매핑
_DEPT_PATH_COMPANY_MAP = {
    "12": "엘앤에프",
    "566": "엘앤에프플러스",
    "58": "JH화학공업",
}


async def _get_pg_pool() -> asyncpg.Pool:
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = await asyncpg.create_pool(
            PG_DATABASE_URL, min_size=1, max_size=3, command_timeout=10
        )
    return _pg_pool


async def _get_company_name(empno: str) -> Optional[str]:
    """사번으로 소속 회사명 조회 (캐시 적용)

    v_user_info_mapping으로 user_id를 얻고, v_org_chart의 부서경로에서
    2번째 ID(12=엘앤에프, 566=엘앤에프플러스, 58=JH화학공업)로 회사를 판별한다.
    부서경로가 '10'만 있는 최상위 직속은 부서명으로 판별한다.
    """
    if empno in _company_cache:
        return _company_cache[empno]

    try:
        pool = await _get_pg_pool()
        row = await pool.fetchrow(
            """
            SELECT o."부서경로", o."부서", u.dept_name
            FROM v_user_info_mapping u
            JOIN v_org_chart o ON u.user_id = o.user_id
            WHERE u.employee_number = $1
            LIMIT 1
            """,
            empno,
        )
        if not row:
            logger.warning(f"[ServiceMenu] empno={empno} not found")
            return None

        dept_path = row["부서경로"] or ""
        dept_name = row["부서"] or row["dept_name"] or ""
        parts = dept_path.split(":")

        if len(parts) >= 2:
            # 부서경로 2번째 ID로 회사 판별
            company_name = _DEPT_PATH_COMPANY_MAP.get(parts[1])
        else:
            # 최상위 직속 (경로가 '10'만) — 부서명으로 판별
            company_name = None
            if "플러스" in dept_name or "LFP" in dept_name.upper():
                company_name = "엘앤에프플러스"
            elif "JH" in dept_name.upper() or "화학" in dept_name:
                company_name = "JH화학공업"

        if not company_name:
            company_name = "엘앤에프"  # 기본값

        _company_cache[empno] = company_name
        logger.info(f"[ServiceMenu] empno={empno} → company={company_name} (path={dept_path})")
        return company_name
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

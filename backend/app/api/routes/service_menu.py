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

# 사번 → 조직명 집합 캐시 (프로세스 수명, 겸직자 대응)
_company_cache: dict[str, list[str]] = {}

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


def _resolve_company(dept_path: str, dept_name: str) -> Optional[str]:
    parts = (dept_path or "").split(":")
    if len(parts) >= 2:
        return _DEPT_PATH_COMPANY_MAP.get(parts[1])
    if "플러스" in dept_name or "LFP" in dept_name.upper():
        return "엘앤에프플러스"
    if "JH" in dept_name.upper() or "화학" in dept_name:
        return "JH화학공업"
    return None


async def _get_company_names(empno: str) -> list[str]:
    """사번으로 소속 회사명 목록 조회 (겸직자는 다중 회사, 캐시 적용)

    v_user_info_mapping으로 user_id를 얻고, v_org_chart의 모든 부서경로에서
    2번째 ID(12=엘앤에프, 566=엘앤에프플러스, 58=JH화학공업)로 회사를 판별한다.
    부서경로가 '10'만 있는 최상위 직속은 부서명으로 판별한다.
    겸직자(여러 부서 보유)는 모든 소속 회사의 합집합을 반환한다.
    """
    if empno in _company_cache:
        return _company_cache[empno]

    try:
        pool = await _get_pg_pool()
        # 겸직자는 v_user_info_mapping에 dept_id별 다중 행을 가진다.
        # v_org_chart는 user당 주부서 1행만 가지므로 user_id JOIN으로는 부서별 경로를
        # 가져올 수 없다 → 각 dept_id로 v_org_chart의 부서경로를 직접 매칭한다.
        rows = await pool.fetch(
            """
            SELECT DISTINCT u.dept_id, u.dept_name, o."부서경로", o."부서"
            FROM v_user_info_mapping u
            LEFT JOIN v_org_chart o ON o."부서ID" = u.dept_id
            WHERE u.employee_number = $1
            """,
            empno,
        )
        if not rows:
            logger.warning(f"[ServiceMenu] empno={empno} not found")
            return []

        companies: list[str] = []
        seen: set[str] = set()
        for row in rows:
            dept_path = row["부서경로"] or ""
            dept_name = row["부서"] or row["dept_name"] or ""
            company = _resolve_company(dept_path, dept_name)
            if company and company not in seen:
                companies.append(company)
                seen.add(company)

        if not companies:
            companies = ["엘앤에프"]  # 기본값

        _company_cache[empno] = companies
        logger.info(f"[ServiceMenu] empno={empno} → companies={companies} (rows={len(rows)})")
        return companies
    except Exception as e:
        logger.error(f"[ServiceMenu] PG query failed: {e}")
        return []


@router.get("/v1/service-menu")
async def get_service_menu(empno: str = Query(..., description="사번")):
    """사번에 해당하는 조직의 서비스 메뉴 목록 반환

    겸직자는 소속된 회사 중 어느 하나라도 메뉴의 노출 대상에 포함되면 표시한다.
    """
    companies = await _get_company_names(empno)
    if not companies:
        raise HTTPException(status_code=404, detail="사번에 해당하는 조직을 찾을 수 없습니다")

    company_set = set(companies)

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
        if company_set.intersection(orgs):
            menus.append({
                "id": row["id"],
                "name": row["name"],
                "icon": row["icon"],
                "url": row["target_url"],
            })

    return {"companies": companies, "menus": menus}

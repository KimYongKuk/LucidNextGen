"""회의실/자산 예약 MCP 서버

그룹웨어(LFON) 자산예약 REST API를 통해
회의실 조회, 예약 등록/취소를 수행하는 MCP 서버입니다.

인증: 서비스 계정 SSO 쿠키 (자동 로그인 + 캐싱)
사용자 매핑: v_reservation_user_mapping VIEW (사번 → GO user.id)
"""
import sys
import os
import asyncpg
import httpx
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

mcp = FastMCP("Reservation Server v1")

# ── 설정 ──────────────────────────────────────────────
LFON_BASE_URL = os.getenv("LFON_BASE_URL", "https://lfon.landf.co.kr")
LFON_SSO_USERNAME = os.getenv("LFON_SSO_USERNAME", "")
LFON_SSO_PASSWORD = os.getenv("LFON_SSO_PASSWORD", "")

# PostgreSQL (사번 → GO user.id 매핑)
DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims")

# ── 전역 캐시 ──────────────────────────────────────────
_db_pool: Optional[asyncpg.Pool] = None
_sso_cookies: Optional[dict] = None
_user_mapping_cache: dict = {}   # 사번 → {go_user_id, user_name}
_sites_cache: Optional[list] = None  # 사업장 목록 (거의 불변)
_rooms_cache: dict = {}          # assetId → [rooms] (거의 불변)


# ── DB 헬퍼 ───────────────────────────────────────────

async def _get_db_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, command_timeout=15
        )
        print("[Reservation MCP] DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


async def _get_go_user_id(employee_number: str) -> Optional[dict]:
    """사번 → GO user.id 매핑 (v_user_info_mapping VIEW 재사용)

    v_user_info_mapping.user_id = GO 내부 user.id (예약 API의 user.id와 동일)
    별도 VIEW 없이 기존 VIEW 하나로 모든 Worker가 통일.
    """
    if employee_number in _user_mapping_cache:
        return _user_mapping_cache[employee_number]

    try:
        pool = await _get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, name, dept_name "
                "FROM v_user_info_mapping WHERE employee_number = $1",
                employee_number,
            )
        if not row:
            print(f"[Reservation MCP] 사용자 미발견: {employee_number}", file=sys.stderr)
            return None

        info = {
            "go_user_id": row["user_id"],      # GO 내부 user.id
            "user_name": row["name"],
            "dept_name": row["dept_name"] or "",
        }
        _user_mapping_cache[employee_number] = info
        print(f"[Reservation MCP] 사용자 매핑: {employee_number} → "
              f"GO#{info['go_user_id']} {info['user_name']}", file=sys.stderr)
        return info
    except Exception as e:
        print(f"[Reservation MCP] 사용자 매핑 실패: {e}", file=sys.stderr)
        return None


# ── SSO 인증 ──────────────────────────────────────────

async def _sso_login() -> Optional[dict]:
    """LFON SSO 로그인하여 쿠키 확보 (캐싱)"""
    global _sso_cookies
    if _sso_cookies:
        return _sso_cookies

    if not LFON_SSO_USERNAME or not LFON_SSO_PASSWORD:
        print("[Reservation MCP] SSO 인증 정보 미설정", file=sys.stderr)
        return None

    try:
        async with httpx.AsyncClient(
            base_url=LFON_BASE_URL, timeout=30, verify=False, follow_redirects=True
        ) as client:
            resp = await client.post(
                "/api/login",
                json={
                    "username": LFON_SSO_USERNAME,
                    "password": LFON_SSO_PASSWORD,
                    "captcha": "",
                    "returnUrl": "",
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if resp.status_code == 200:
                _sso_cookies = dict(resp.cookies)
                print(f"[Reservation MCP] SSO 로그인 성공: {LFON_SSO_USERNAME}", file=sys.stderr)
                return _sso_cookies
            else:
                print(f"[Reservation MCP] SSO 로그인 실패: status={resp.status_code}", file=sys.stderr)
                return None
    except Exception as e:
        print(f"[Reservation MCP] SSO 로그인 오류: {e}", file=sys.stderr)
        return None


async def _api_request(method: str, path: str, **kwargs) -> Optional[dict]:
    """LFON API 호출 (SSO 쿠키 자동 관리, 401 시 재로그인)"""
    cookies = await _sso_login()
    if not cookies:
        return None

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "GO-Agent": "",
        "TimeZoneOffset": "540",
    }
    if method.upper() in ("POST", "PUT", "DELETE"):
        headers["Content-Type"] = "application/json"
        headers["Origin"] = LFON_BASE_URL
        headers["Referer"] = f"{LFON_BASE_URL}/app/asset"

    for attempt in range(2):  # 최대 1회 재시도
        try:
            async with httpx.AsyncClient(
                base_url=LFON_BASE_URL, timeout=30, verify=False,
                follow_redirects=True
            ) as client:
                resp = await client.request(
                    method, path, headers=headers, cookies=cookies, **kwargs
                )

                if resp.status_code in (401, 403) and attempt == 0:
                    global _sso_cookies
                    _sso_cookies = None
                    cookies = await _sso_login()
                    if not cookies:
                        return None
                    continue

                if resp.status_code == 200:
                    return resp.json()
                else:
                    body = resp.text[:500] if resp.text else "(empty)"
                    print(f"[Reservation MCP] API 오류: {method} {path} → "
                          f"status={resp.status_code}, body={body}",
                          file=sys.stderr)
                    # 에러 응답도 JSON이면 파싱해서 반환 (호출자가 메시지 활용)
                    try:
                        return resp.json()
                    except Exception:
                        return {"code": str(resp.status_code), "message": body}
        except Exception as e:
            print(f"[Reservation MCP] API 호출 실패: {method} {path} → {e}", file=sys.stderr)
            return None

    return None


# ── MCP 도구 ──────────────────────────────────────────

@mcp.tool()
async def get_sites() -> str:
    """사업장(예약 카테고리) 목록을 조회합니다.
    회의실이 어떤 사업장에 속하는지 확인할 때 사용합니다.

    Returns:
        사업장 목록 (id, 이름)
    """
    global _sites_cache
    if _sites_cache:
        lines = ["## 사업장 목록\n"]
        for s in _sites_cache:
            lines.append(f"- **{s['name']}** (id={s['id']})")
        return "\n".join(lines)

    result = await _api_request("GET", "/api/asset")
    if not result or result.get("code") != "200":
        return "오류: 사업장 목록을 가져올 수 없습니다."

    sites = result["data"]
    _sites_cache = [{"id": s["id"], "name": s["name"]} for s in sites]

    lines = ["## 사업장 목록\n"]
    for s in _sites_cache:
        lines.append(f"- **{s['name']}** (id={s['id']})")
    return "\n".join(lines)


@mcp.tool()
async def get_rooms(asset_id: int) -> str:
    """특정 사업장의 회의실/자산 목록을 조회합니다.

    Args:
        asset_id: 사업장 ID (get_sites에서 확인)

    Returns:
        회의실 목록 (id, 이름)
    """
    if asset_id in _rooms_cache:
        rooms = _rooms_cache[asset_id]
    else:
        result = await _api_request("GET", f"/api/asset/{asset_id}/item/?page=0&offset=100")
        if not result or result.get("code") != "200":
            return f"오류: 사업장(id={asset_id})의 회의실 목록을 가져올 수 없습니다."
        rooms = [{"id": r["id"], "name": r["name"]} for r in result["data"]]
        _rooms_cache[asset_id] = rooms

    if not rooms:
        return f"사업장(id={asset_id})에 등록된 회의실/자산이 없습니다."

    lines = [f"## 회의실/자산 목록 (사업장 id={asset_id})\n"]
    for r in rooms:
        lines.append(f"- **{r['name']}** (id={r['id']})")
    return "\n".join(lines)


@mcp.tool()
async def get_daily_reservations(asset_id: int, date: str) -> str:
    """특정 사업장의 특정 날짜 예약 현황을 조회합니다.
    빈 회의실을 찾거나 예약 상황을 확인할 때 사용합니다.

    Args:
        asset_id: 사업장 ID
        date: 조회 날짜 (YYYY-MM-DD 형식, 예: "2026-04-01")

    Returns:
        해당 날짜의 예약 목록 (회의실, 시간, 예약자)
    """
    from_date = f"{date}T00:00:00.000+09:00"
    result = await _api_request("GET", f"/api/asset/{asset_id}/items/daily",
                                params={"fromDate": from_date})
    if not result or result.get("code") != "200":
        return f"오류: 예약 현황을 가져올 수 없습니다. (asset_id={asset_id}, date={date})"

    reservations = result["data"]
    print(f"[Reservation MCP] get_daily_reservations: API returned {len(reservations)} items "
          f"for asset_id={asset_id}, date={date}", file=sys.stderr)
    if not reservations:
        return f"{date} 에 예약된 건이 없습니다. 모든 회의실이 비어있습니다."

    # 날짜 필터링 (API가 여러 날짜를 반환할 수 있음)
    target_date = date  # "YYYY-MM-DD"
    filtered = [r for r in reservations if r["startTime"].startswith(target_date)]
    print(f"[Reservation MCP] get_daily_reservations: {len(filtered)} items after date filter "
          f"(target={target_date})", file=sys.stderr)

    if not filtered:
        return f"{date} 에 예약된 건이 없습니다. 모든 회의실이 비어있습니다."

    # 회의실별 그룹핑 (item_id 포함)
    by_room: dict = {}  # (room_name, item_id) → [bookings]
    for r in filtered:
        room_name = r.get("itemName", "알 수 없음")
        item_id = r.get("itemId") or r.get("item", {}).get("id") or "?"
        room_key = (room_name, item_id)
        if room_key not in by_room:
            by_room[room_key] = []

        start = r["startTime"][11:16]  # "HH:MM"
        end = r["endTime"][11:16]
        user_name = r.get("user", {}).get("name", "알 수 없음")
        position = r.get("user", {}).get("positionName", "")
        anonym = r.get("useAnonym", False)

        by_room[room_key].append({
            "id": r["id"],
            "time": f"{start}~{end}",
            "user": "익명" if anonym else f"{user_name} {position}".strip(),
        })

    # 시간순 정렬
    for room_key in by_room:
        by_room[room_key].sort(key=lambda x: x["time"])

    lines = [f"## {date} 예약 현황\n"]
    for (room_name, item_id), bookings in sorted(by_room.items()):
        lines.append(f"### {room_name} (item_id={item_id})")
        for b in bookings:
            lines.append(f"  - {b['time']}  {b['user']}  (예약ID: {b['id']})")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def find_available_rooms(asset_id: int, date: str, start_time: str, end_time: str) -> str:
    """특정 시간대에 비어있는 회의실을 찾습니다.
    빈 회의실을 찾을 때 get_daily_reservations 대신 이 도구를 사용하세요.
    예약 현황을 직접 분석하여 정확한 빈 회의실 목록을 반환합니다.

    Args:
        asset_id: 사업장 ID (본사=70, 성서=100 등)
        date: 조회 날짜 (YYYY-MM-DD)
        start_time: 시작 시간 (HH:MM, 예: "16:00")
        end_time: 종료 시간 (HH:MM, 예: "17:00")

    Returns:
        빈 회의실 목록과 해당 시간대의 예약 상황
    """
    # 1) 회의실 목록 가져오기
    if asset_id in _rooms_cache:
        rooms = _rooms_cache[asset_id]
    else:
        room_result = await _api_request("GET", f"/api/asset/{asset_id}/item/?page=0&offset=100")
        if not room_result or room_result.get("code") != "200":
            return f"오류: 사업장(id={asset_id})의 회의실 목록을 가져올 수 없습니다."
        rooms = [{"id": r["id"], "name": r["name"]} for r in room_result["data"]]
        _rooms_cache[asset_id] = rooms

    if not rooms:
        return f"사업장(id={asset_id})에 등록된 회의실/자산이 없습니다."

    # 2) 예약 현황 가져오기
    from_date = f"{date}T00:00:00.000+09:00"
    res_result = await _api_request("GET", f"/api/asset/{asset_id}/items/daily",
                                    params={"fromDate": from_date})
    if not res_result or res_result.get("code") != "200":
        return f"오류: 예약 현황을 가져올 수 없습니다."

    reservations = res_result.get("data", [])

    # 3) 요청 시간대와 겹치는 예약 찾기
    req_start = f"{date}T{start_time}:00"  # "YYYY-MM-DDTHH:MM:00"
    req_end = f"{date}T{end_time}:00"

    # room_id별 충돌 예약 수집
    conflicts_by_room: dict = {}  # room_id → [충돌 예약 정보]
    for r in reservations:
        if not r.get("startTime", "").startswith(date):
            continue
        r_item_id = r.get("itemId") or r.get("item", {}).get("id")
        r_start = r.get("startTime", "")[:19]
        r_end = r.get("endTime", "")[:19]
        # 시간 겹침: NOT (req_end <= r_start OR r_end <= req_start)
        if not (req_end <= r_start or r_end <= req_start):
            r_id = int(r_item_id) if r_item_id else None
            if r_id is not None:
                if r_id not in conflicts_by_room:
                    conflicts_by_room[r_id] = []
                r_user = r.get("user", {}).get("name", "알 수 없음")
                r_time = f"{r_start[11:16]}~{r_end[11:16]}"
                conflicts_by_room[r_id].append(f"{r_user} {r_time}")

    # 4) 결과 분류
    available = []
    occupied = []
    for room in rooms:
        room_id = room["id"]
        room_name = room["name"]
        if room_id in conflicts_by_room:
            occupied.append({"name": room_name, "id": room_id,
                             "conflicts": conflicts_by_room[room_id]})
        else:
            available.append({"name": room_name, "id": room_id})

    # 5) 포맷팅
    lines = [f"## {date} {start_time}~{end_time} 회의실 현황\n"]

    if available:
        lines.append(f"### ✅ 비어있는 회의실 ({len(available)}개)")
        for r in available:
            lines.append(f"  - **{r['name']}** (id={r['id']})")
        lines.append("")

    if occupied:
        lines.append(f"### ❌ 예약된 회의실 ({len(occupied)}개)")
        for r in occupied:
            conflict_str = ", ".join(r["conflicts"])
            lines.append(f"  - **{r['name']}** — {conflict_str}")
        lines.append("")

    if not available:
        lines.append("⚠️ 해당 시간대에 비어있는 회의실이 없습니다.")
        lines.append("다른 시간대나 다른 사업장을 확인해보세요.")

    print(f"[Reservation MCP] find_available_rooms: {len(available)} available, "
          f"{len(occupied)} occupied for {date} {start_time}~{end_time}",
          file=sys.stderr)

    return "\n".join(lines)


# 내 예약 ID 집합 캐시 (소유자 검증 최적화 — 60초 TTL)
_my_reservations_cache: Dict[str, tuple] = {}  # {employee_number: (ids_set, timestamp)}
_MY_RESERVATIONS_CACHE_TTL = 60  # 초


async def _fetch_my_reservations_raw(employee_number: str, days: int = 30) -> Optional[List[Dict]]:
    """내 예약 원본 데이터 반환 (본인 검증 + get_my_reservations 공통 로직).

    Returns:
        리스트 (각 항목은 userId == go_user_id인 예약 dict) — 없으면 []
        None = 사용자 매핑 실패 (호출자가 에러 처리)
    """
    import asyncio
    user_info = await _get_go_user_id(employee_number)
    if not user_info:
        return None
    go_user_id = user_info["go_user_id"]
    now = datetime.now()
    days = min(max(days, 1), 30)

    # 사업장 목록 (캐시)
    global _sites_cache
    if not _sites_cache:
        result = await _api_request("GET", "/api/asset")
        if not result or result.get("code") != "200":
            return []
        _sites_cache = [{"id": s["id"], "name": s["name"]} for s in result["data"]]

    # 날짜 스텝 (2일 간격)
    date_steps = [
        (now + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00.000+09:00")
        for i in range(0, days, 2)
    ]

    sem = asyncio.Semaphore(20)

    async def _fetch(site, from_date):
        async with sem:
            result = await _api_request(
                "GET", f"/api/asset/{site['id']}/items/daily",
                params={"fromDate": from_date}
            )
            if not result or result.get("code") != "200":
                return []
            return [
                {**r, "_site_name": site["name"]}
                for r in result["data"]
                if r.get("userId") == go_user_id
            ]

    tasks = [
        _fetch(site, from_date)
        for site in _sites_cache
        for from_date in date_steps
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_ids = set()
    my_list = []
    for res in results:
        if isinstance(res, list):
            for r in res:
                rid = r.get("id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    my_list.append(r)
    return my_list


async def _get_my_reservation_ids(employee_number: str) -> set:
    """내 예약 ID 집합 반환 (60초 TTL 캐시) — cancel_reservation 소유자 검증용"""
    import time as _t
    now = _t.time()
    cached = _my_reservations_cache.get(employee_number)
    if cached and (now - cached[1]) < _MY_RESERVATIONS_CACHE_TTL:
        return cached[0]

    raw = await _fetch_my_reservations_raw(employee_number, days=30)
    if raw is None:
        return set()  # 사용자 매핑 실패 — 빈 집합 반환하면 cancel 거부됨
    ids = {r.get("id") for r in raw if r.get("id") is not None}
    _my_reservations_cache[employee_number] = (ids, now)
    return ids


@mcp.tool()
async def get_my_reservations(employee_number: str, days: int = 7) -> str:
    """내 남은(향후) 예약 목록을 조회합니다.
    전 사업장을 병렬 조회하여 본인 예약만 필터링합니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        days: 조회 기간 (기본 7일, 최대 30일). 사용자가 "한 달" 등 요청 시 30 지정.

    Returns:
        내 예약 목록 (사업장, 회의실, 시간)
    """
    # 사번 → GO user.id 매핑 (표시용 이름)
    user_info = await _get_go_user_id(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    # 공통 헬퍼로 raw 예약 목록 조회
    my_reservations = await _fetch_my_reservations_raw(employee_number, days=days)
    if my_reservations is None:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    # cancel 검증용 캐시 동기화 (같은 턴 내 재호출 시 재사용)
    import time as _t
    _my_reservations_cache[employee_number] = (
        {r.get("id") for r in my_reservations if r.get("id") is not None},
        _t.time(),
    )

    if not my_reservations:
        return f"{user_info['user_name']}님의 예약이 없습니다."

    # 시간순 정렬
    my_reservations.sort(key=lambda r: r.get("startTime", ""))

    lines = [f"## {user_info['user_name']}님의 예약 목록 ({len(my_reservations)}건)\n"]
    for r in my_reservations:
        site_name = r.get("_site_name", "")
        item_name = r.get("itemName", "알 수 없음")
        start = r["startTime"][:16].replace("T", " ")
        end = r["endTime"][11:16]
        lines.append(
            f"- **{site_name}** {item_name}\n"
            f"  {start} ~ {end}  (예약ID: {r['id']})"
        )

    return "\n".join(lines)


@mcp.tool()
async def create_reservation(
    employee_number: str,
    asset_id: int,
    item_id: int,
    start_time: str,
    end_time: str,
) -> str:
    """회의실/자산을 예약합니다.
    반드시 사용자에게 예약 내용을 확인받은 후 호출하세요.

    Args:
        employee_number: 사번 (자동 주입됨)
        asset_id: 사업장 ID (get_sites에서 확인)
        item_id: 회의실/자산 ID (get_rooms에서 확인)
        start_time: 시작 시간 (ISO 형식, 예: "2026-04-01T14:00:00.000+09:00")
        end_time: 종료 시간 (ISO 형식, 예: "2026-04-01T15:00:00.000+09:00")

    Returns:
        예약 결과 (성공 시 예약ID, 실패 시 오류 메시지)
    """
    # 사번 → GO user.id 매핑
    user_info = await _get_go_user_id(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]

    # ── item_id 유효성 검증 (LLM 할루시네이션 방지) ──
    if asset_id in _rooms_cache:
        rooms = _rooms_cache[asset_id]
    else:
        room_result = await _api_request("GET", f"/api/asset/{asset_id}/item/?page=0&offset=100")
        if room_result and room_result.get("code") == "200":
            rooms = [{"id": r["id"], "name": r["name"]} for r in room_result["data"]]
            _rooms_cache[asset_id] = rooms
        else:
            rooms = None

    if rooms is not None:
        valid_ids = {r["id"] for r in rooms}
        if item_id not in valid_ids:
            room_list = ", ".join(f"{r['name']}(id={r['id']})" for r in rooms)
            return (f"오류: item_id={item_id}은(는) 사업장(id={asset_id})에 존재하지 않는 회의실입니다.\n"
                    f"사용 가능한 회의실: {room_list}\n"
                    f"정확한 item_id를 사용해주세요.")

    # ── 예약 전 충돌 검증 (daily API 재조회) ──
    # get_daily_reservations 결과가 불완전할 수 있으므로 예약 직전에 재확인
    req_date = start_time[:10]  # "YYYY-MM-DD"
    from_date = f"{req_date}T00:00:00.000+09:00"
    check_result = await _api_request("GET", f"/api/asset/{asset_id}/items/daily",
                                      params={"fromDate": from_date})
    if check_result and check_result.get("code") == "200":
        req_start = start_time[:19]  # "YYYY-MM-DDTHH:MM:SS"
        req_end = end_time[:19]
        conflicts = []
        for r in check_result["data"]:
            r_item_id = r.get("itemId") or r.get("item", {}).get("id")
            if str(r_item_id) != str(item_id):
                continue
            r_start = r.get("startTime", "")[:19]
            r_end = r.get("endTime", "")[:19]
            # 시간 겹침 체크: NOT (req_end <= r_start OR r_end <= req_start)
            if not (req_end <= r_start or r_end <= req_start):
                r_user = r.get("user", {}).get("name", "알 수 없음")
                r_time = f"{r_start[11:16]}~{r_end[11:16]}"
                conflicts.append(f"{r_user} ({r_time})")
        if conflicts:
            conflict_str = ", ".join(conflicts)
            # 해당 아이템의 빈 시간대도 안내
            return (f"오류: 해당 시간에 이미 예약이 있습니다.\n"
                    f"- 충돌 예약: {conflict_str}\n"
                    f"- 요청 시간: {start_time[11:16]}~{end_time[11:16]}\n\n"
                    f"다른 시간대나 다른 회의실을 선택해주세요.")

    payload = {
        "assetId": asset_id,
        "itemId": str(item_id),
        "type": "reserve",
        "startTime": start_time,
        "endTime": end_time,
        "useAnonym": False,
        "user": {"id": str(go_user_id)},
        "properties": [],
        "allday": False,
    }

    print(f"[Reservation MCP] 예약 등록 시도: asset={asset_id}, item={item_id}, "
          f"user=GO#{go_user_id}, {start_time[:16]}~{end_time[11:16]}", file=sys.stderr)

    result = await _api_request("POST", f"/api/asset/{asset_id}/item/{item_id}/reserve",
                                json=payload)
    if not result:
        return (f"오류: 예약 등록에 실패했습니다. 서버에 연결할 수 없습니다. "
                f"(asset={asset_id}, item={item_id}, user=GO#{go_user_id})")

    if result.get("code") != "200":
        msg = result.get("message", "알 수 없는 오류")
        code = result.get("code", "?")
        return f"오류: 예약 등록 실패 (code={code}) — {msg}"

    # 예약 성공 → 캐시 invalidate (새 예약 ID가 다음 cancel 시 인정되도록)
    _my_reservations_cache.pop(employee_number, None)

    data = result["data"]
    item_name = data.get("itemName", "알 수 없음")
    res_id = data.get("id", "?")
    start_display = data.get("startTime", start_time)[:16].replace("T", " ")
    end_display = data.get("endTime", end_time)[11:16]

    return (
        f"✅ 예약이 완료되었습니다!\n\n"
        f"- **회의실**: {item_name}\n"
        f"- **시간**: {start_display} ~ {end_display}\n"
        f"- **예약자**: {user_info['user_name']}\n"
        f"- **예약ID**: {res_id}"
    )


@mcp.tool()
async def cancel_reservation(
    employee_number: str,
    reservation_id: int,
) -> str:
    """예약을 취소합니다. 본인이 등록한 예약만 취소할 수 있습니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        reservation_id: 취소할 예약 ID (get_my_reservations 또는 get_daily_reservations에서 확인)

    Returns:
        취소 결과
    """
    # 사번 → GO user.id 매핑
    user_info = await _get_go_user_id(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    # 🔒 소유자 검증 (서버 강제, LLM 프롬프트 의존 X) —
    # 서비스 계정이 모든 예약 접근 가능하므로 반드시 백엔드에서 userId 매칭 확인.
    my_ids = await _get_my_reservation_ids(employee_number)
    if reservation_id not in my_ids:
        print(
            f"[Reservation MCP] 🚫 소유자 검증 실패: {employee_number}({user_info['user_name']}) "
            f"→ reservation_id={reservation_id} (본인 예약 아님)",
            file=sys.stderr,
        )
        return (
            f"오류: 본인이 등록한 예약만 취소할 수 있습니다. "
            f"(예약ID {reservation_id}는 {user_info['user_name']}님의 예약 목록에 없습니다)"
        )

    result = await _api_request("DELETE", "/api/asset/item/reservation",
                                json={"ids": [str(reservation_id)]})
    if not result:
        return "오류: 예약 취소에 실패했습니다. 서버에 연결할 수 없습니다."

    if result.get("code") != "200":
        msg = result.get("message", "알 수 없는 오류")
        return f"오류: 예약 취소 실패 — {msg}"

    # 취소 성공 → 캐시 invalidate (다음 get_my_reservations에서 새로 조회)
    _my_reservations_cache.pop(employee_number, None)

    cancelled = result["data"]
    if cancelled:
        name = cancelled[0].get("name", "알 수 없음")
        return f"✅ 예약이 취소되었습니다.\n\n- **회의실**: {name}\n- **예약ID**: {reservation_id}"

    return f"✅ 예약 {reservation_id}이(가) 취소되었습니다."


# ── 메인 ──────────────────────────────────────────────

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message=".*SSL.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    mcp.run(transport="stdio")

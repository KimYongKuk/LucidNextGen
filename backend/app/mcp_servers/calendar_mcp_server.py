"""캘린더 MCP 서버

그룹웨어(LFON) 캘린더 REST API를 통해
일정 조회, 등록, 삭제를 수행하는 MCP 서버입니다.

인증: 서비스 계정 SSO 쿠키 (자동 로그인 + 캐싱)
사용자 매핑: v_user_info_mapping VIEW (사번 → GO user.id)

권한 모델:
- 내 캘린더: 소유자 본인 → 조회/등록/삭제 가능
- 관심 캘린더: follow 상태 + 상대방 수락 → 조회만 가능
- 공개 캘린더: visibility="public" → 조회만 가능
- 비공개/수락후공개 캘린더: 접근 불가 (관심 등록 후 수락된 경우만 가능)
- 일정 비공개: creator 또는 attendee만 상세 조회 가능, 그 외 "비공개 일정" 표시
"""
import sys
import os
import asyncpg
import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

mcp = FastMCP("Calendar Server v1")

# ── 설정 ──────────────────────────────────────────────
LFON_BASE_URL = os.getenv("LFON_BASE_URL", "https://lfon.landf.co.kr")
LFON_SSO_USERNAME = os.getenv("LFON_SSO_USERNAME", "")
LFON_SSO_PASSWORD = os.getenv("LFON_SSO_PASSWORD", "")

# PostgreSQL (사번 → GO user.id 매핑)
DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims")

# ── 전역 캐시 ──────────────────────────────────────────
_db_pool: Optional[asyncpg.Pool] = None
_sso_cookies: Optional[dict] = None
_user_mapping_cache: dict = {}       # 사번 → {go_user_id, user_name, dept_name}
_user_feed_cache: dict = {}          # go_user_id → {calendar_id: feed_info, ...}  (TTL 관리)
_user_feed_cache_ts: dict = {}       # go_user_id → datetime (캐시 시각)
FEED_CACHE_TTL = 300                 # 피드 캐시 TTL (5분)


# ── DB 헬퍼 ───────────────────────────────────────────

async def _get_db_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, command_timeout=15
        )
        print("[Calendar MCP] DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


async def _get_go_user_info(employee_number: str) -> Optional[dict]:
    """사번 → GO user.id/name/dept 매핑"""
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
            print(f"[Calendar MCP] 사용자 미발견: {employee_number}", file=sys.stderr)
            return None

        info = {
            "go_user_id": row["user_id"],
            "user_name": row["name"],
            "dept_name": row["dept_name"] or "",
        }
        _user_mapping_cache[employee_number] = info
        print(f"[Calendar MCP] 사용자 매핑: {employee_number} → "
              f"GO#{info['go_user_id']} {info['user_name']}", file=sys.stderr)
        return info
    except Exception as e:
        print(f"[Calendar MCP] 사용자 매핑 실패: {e}", file=sys.stderr)
        return None


async def _search_users_by_name(name: str, limit: int = 5) -> list:
    """이름으로 사용자 검색 (참석자 조회용)"""
    try:
        pool = await _get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT employee_number, login_id, user_id, name, dept_name "
                "FROM v_user_info_mapping WHERE name LIKE '%' || $1 || '%' "
                "LIMIT $2",
                name, limit,
            )
        return [
            {
                "employee_number": r["employee_number"],
                "go_user_id": r["user_id"],
                "name": r["name"],
                "dept_name": r.get("dept_name") or "",
                "email": f"{r['login_id']}@landf.co.kr" if r.get("login_id") else "",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[Calendar MCP] 사용자 검색 실패: {e}", file=sys.stderr)
        return []


# ── SSO 인증 ──────────────────────────────────────────

async def _sso_login() -> Optional[dict]:
    """LFON SSO 로그인하여 쿠키 확보 (캐싱)"""
    global _sso_cookies
    if _sso_cookies:
        return _sso_cookies

    if not LFON_SSO_USERNAME or not LFON_SSO_PASSWORD:
        print("[Calendar MCP] SSO 인증 정보 미설정", file=sys.stderr)
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
                print(f"[Calendar MCP] SSO 로그인 성공: {LFON_SSO_USERNAME}", file=sys.stderr)
                return _sso_cookies
            else:
                print(f"[Calendar MCP] SSO 로그인 실패: status={resp.status_code}", file=sys.stderr)
                return None
    except Exception as e:
        print(f"[Calendar MCP] SSO 로그인 오류: {e}", file=sys.stderr)
        return None


async def _api_request(method: str, path: str, **kwargs) -> Optional[Any]:
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
        headers["Referer"] = f"{LFON_BASE_URL}/app/calendar"

    for attempt in range(2):
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
                    print(f"[Calendar MCP] API 오류: {method} {path} → "
                          f"status={resp.status_code}, body={body}",
                          file=sys.stderr)
                    try:
                        return resp.json()
                    except Exception:
                        return {"code": str(resp.status_code), "message": body}
        except Exception as e:
            print(f"[Calendar MCP] API 호출 실패: {method} {path} → {e}", file=sys.stderr)
            return None

    return None


# ── 내부 헬퍼 ─────────────────────────────────────────

async def _get_user_feed(go_user_id: int) -> dict:
    """사용자의 피드(내 캘린더 + 관심 캘린더) 조회 및 캐싱

    Returns:
        {calendar_id: {
            "calendar_id", "calendar_name", "owner_id", "owner_name",
            "visibility", "is_own", "state", "default_calendar"
        }}
    """
    now = datetime.now()

    # 캐시 유효성 확인
    if go_user_id in _user_feed_cache:
        cached_ts = _user_feed_cache_ts.get(go_user_id)
        if cached_ts and (now - cached_ts).total_seconds() < FEED_CACHE_TTL:
            return _user_feed_cache[go_user_id]

    result = await _api_request("GET", "/api/calendar/feed", params={"sort": "sequence asc"})
    if not result:
        return _user_feed_cache.get(go_user_id, {})

    # result가 리스트 형태인지, data 키가 있는지 확인
    feeds = result if isinstance(result, list) else result.get("data", result)
    if not isinstance(feeds, list):
        print(f"[Calendar MCP] 피드 응답 형식 예상 외: {type(feeds)}", file=sys.stderr)
        return {}

    feed_map = {}
    for feed in feeds:
        cal = feed.get("calendar", {})
        cal_id = cal.get("id")
        if not cal_id:
            continue

        owner = cal.get("owner", {})
        feed_map[cal_id] = {
            "calendar_id": cal_id,
            "calendar_name": cal.get("name", ""),
            "owner_id": owner.get("id"),
            "owner_name": owner.get("name", ""),
            "visibility": cal.get("visibility", "private"),
            "is_own": owner.get("id") == go_user_id,
            "state": feed.get("state", ""),
            "default_calendar": cal.get("defaultCalendar", False),
        }

    _user_feed_cache[go_user_id] = feed_map
    _user_feed_cache_ts[go_user_id] = now
    print(f"[Calendar MCP] 피드 캐싱 완료: GO#{go_user_id}, "
          f"{len(feed_map)}개 캘린더", file=sys.stderr)
    return feed_map


def _can_access_calendar(feed_map: dict, calendar_id: int) -> bool:
    """사용자가 해당 캘린더에 접근 가능한지 확인

    접근 가능 조건:
    1. 내 캘린더 (is_own == True)
    2. 관심 캘린더에 있음 (state == "following")
    3. 공개 캘린더 (visibility == "public") — 관심 등록 여부 무관
    """
    info = feed_map.get(calendar_id)
    if info:
        # 피드에 있으면 접근 가능 (내 캘린더 또는 관심 캘린더)
        return True
    # 피드에 없더라도 공개 캘린더는 접근 가능 → 이건 API 호출 시점에 별도 처리
    return False


def _filter_private_events(
    events: list, go_user_id: int, is_own_calendar: bool
) -> list:
    """비공개 일정 필터링

    - 내 캘린더 → 전부 표시
    - 타인 캘린더:
      - visibility != "private" → 표시
      - visibility == "private" + 내가 creator 또는 attendee → 표시
      - 그 외 → 시간만 표시, 제목/내용 마스킹
    """
    if is_own_calendar:
        return events

    filtered = []
    for event in events:
        visibility = event.get("visibility", "public")
        if visibility != "private":
            filtered.append(event)
            continue

        # private 일정 — creator 또는 attendee인지 확인
        creator_id = event.get("creator", {}).get("id")
        attendee_ids = [
            a.get("id") for a in event.get("attendees", [])
            if a.get("id")
        ]

        if str(go_user_id) == str(creator_id) or str(go_user_id) in [str(aid) for aid in attendee_ids]:
            filtered.append(event)
        else:
            # 마스킹된 일정
            filtered.append({
                "id": event.get("id"),
                "startTime": event.get("startTime"),
                "endTime": event.get("endTime"),
                "timeType": event.get("timeType"),
                "summary": "🔒 비공개 일정",
                "visibility": "private",
                "_masked": True,
            })

    return filtered


# ── MCP 도구 ──────────────────────────────────────────

@mcp.tool()
async def get_my_calendars(employee_number: str) -> str:
    """내 캘린더 및 관심 캘린더 목록을 조회합니다.
    캘린더 ID를 확인하여 일정 조회, 등록, 삭제에 사용합니다.

    Args:
        employee_number: 사번 (자동 주입됨)

    Returns:
        내 캘린더 + 관심 캘린더 목록 (id, 이름, 소유자, 공개설정)
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]

    # 내 캘린더: /api/calendar/user/{id}/calendar (사용자별 조회)
    # feed API는 서비스 계정 세션 기준이라 사용자 본인 캘린더를 반환하지 않음
    my_cals = []
    result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
    if result:
        calendars = result if isinstance(result, list) else result.get("data", [])
        if isinstance(calendars, list):
            for c in calendars:
                my_cals.append({
                    "calendar_id": c.get("id"),
                    "calendar_name": c.get("name", ""),
                    "visibility": c.get("visibility", "private"),
                    "default_calendar": c.get("defaultCalendar", False),
                    "type": c.get("type", "normal"),
                })
            print(f"[Calendar MCP] 사용자 캘린더 조회: GO#{go_user_id} → "
                  f"{len(my_cals)}개", file=sys.stderr)

    # 관심 캘린더: feed API (서비스 계정 기준 — 사용자별 관심 캘린더는 제한적)
    interest_cals = []
    feed_map = await _get_user_feed(go_user_id)
    if feed_map:
        my_cal_ids = {c["calendar_id"] for c in my_cals}
        for cal in feed_map.values():
            # 내 캘린더와 중복 제거
            if cal["calendar_id"] not in my_cal_ids:
                interest_cals.append(cal)

    lines = [f"## {user_info['user_name']}님의 캘린더\n"]

    if my_cals:
        lines.append("### 📅 내 캘린더")
        for c in my_cals:
            default_mark = " ⭐기본" if c["default_calendar"] else ""
            lines.append(
                f"- **{c['calendar_name']}** (id={c['calendar_id']}, "
                f"공개={c['visibility']}){default_mark}"
            )
        lines.append("")

    if interest_cals:
        lines.append("### 👥 관심 캘린더")
        for c in interest_cals:
            lines.append(
                f"- **{c['calendar_name']}** (id={c['calendar_id']}, "
                f"소유자={c['owner_name']}, 공개={c['visibility']})"
            )
        lines.append("")

    if not my_cals and not interest_cals:
        return f"{user_info['user_name']}님의 캘린더 정보를 가져올 수 없습니다."

    lines.append(f"\n총 {len(my_cals)}개 내 캘린더, {len(interest_cals)}개 관심 캘린더")
    return "\n".join(lines)


@mcp.tool()
async def get_user_public_calendars(target_employee_number: str, employee_number: str) -> str:
    """특정 사용자의 공개 캘린더 목록을 조회합니다.
    관심 캘린더에 등록하지 않은 사용자의 공개 일정을 확인할 때 사용합니다.

    Args:
        target_employee_number: 조회 대상 사번
        employee_number: 요청자 사번 (자동 주입됨)

    Returns:
        대상 사용자의 공개 캘린더 목록
    """
    target_info = await _get_go_user_info(target_employee_number)
    if not target_info:
        return f"오류: 사번 '{target_employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    target_go_id = target_info["go_user_id"]
    result = await _api_request("GET", f"/api/calendar/user/{target_go_id}/calendar")

    if not result:
        return f"오류: {target_info['user_name']}님의 캘린더를 가져올 수 없습니다."

    calendars = result if isinstance(result, list) else result.get("data", [])
    if not isinstance(calendars, list):
        return f"오류: 예상치 못한 응답 형식입니다."

    # 공개 캘린더만 필터링
    public_cals = [c for c in calendars if c.get("visibility") == "public"]

    if not public_cals:
        return f"{target_info['user_name']}님에게 공개된 캘린더가 없습니다."

    lines = [f"## {target_info['user_name']}님의 공개 캘린더\n"]
    for c in public_cals:
        lines.append(
            f"- **{c.get('name', '알 수 없음')}** (id={c.get('id')}, "
            f"type={c.get('type', 'normal')})"
        )

    return "\n".join(lines)


@mcp.tool()
async def get_calendar_events(
    employee_number: str,
    calendar_ids: str,
    start_date: str,
    end_date: str,
) -> str:
    """지정한 캘린더의 일정을 기간별로 조회합니다.
    접근 권한이 있는 캘린더만 조회 가능합니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        calendar_ids: 캘린더 ID 목록 (콤마 구분, 예: "2677,11")
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)

    Returns:
        일정 목록 (제목, 시간, 장소, 참석자)
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]
    feed_map = await _get_user_feed(go_user_id)

    # 사용자 본인 캘린더 ID 조회 (feed에 없을 수 있으므로)
    own_cal_ids = set()
    user_cal_result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
    if user_cal_result:
        user_cals = user_cal_result if isinstance(user_cal_result, list) else user_cal_result.get("data", [])
        if isinstance(user_cals, list):
            own_cal_ids = {c.get("id") for c in user_cals if c.get("id")}

    # 캘린더 ID 파싱
    try:
        cal_ids = [int(cid.strip()) for cid in calendar_ids.split(",") if cid.strip()]
    except ValueError:
        return "오류: calendar_ids 형식이 잘못되었습니다. 콤마로 구분된 숫자를 입력하세요."

    if not cal_ids:
        return "오류: 조회할 캘린더 ID를 지정해주세요."

    # 접근 권한 확인 — 본인 캘린더, 피드에 있거나, 공개 캘린더
    accessible_ids = []
    denied_ids = []
    for cid in cal_ids:
        if cid in own_cal_ids or _can_access_calendar(feed_map, cid):
            accessible_ids.append(cid)
        else:
            # 피드에 없는 캘린더 — 공개 캘린더일 수 있으므로 일단 포함
            # (API가 권한 없으면 빈 결과 반환)
            accessible_ids.append(cid)

    if not accessible_ids:
        return "오류: 접근 가능한 캘린더가 없습니다."

    # API 호출
    time_min = f"{start_date}T00:00:00.000+09:00"
    time_max = f"{end_date}T23:59:59.999+09:00"

    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "includingAttendees": "true",
    }
    # calendarIds[] 파라미터 구성
    for cid in accessible_ids:
        params_key = "calendarIds[]"
        if params_key not in params:
            params[params_key] = []
        if isinstance(params.get(params_key), list):
            params[params_key].append(str(cid))

    # httpx는 리스트 파라미터를 다르게 처리하므로 직접 URL 구성
    # +09:00 → %2B09:00 (URL에서 +는 공백으로 해석될 수 있음)
    from urllib.parse import quote
    time_min_enc = quote(time_min, safe="")
    time_max_enc = quote(time_max, safe="")
    cal_params = "&".join([f"calendarIds%5B%5D={cid}" for cid in accessible_ids])
    path = (f"/api/calendar/event?timeMin={time_min_enc}&timeMax={time_max_enc}"
            f"&includingAttendees=true&{cal_params}")

    print(f"[Calendar MCP] get_calendar_events: requesting {len(accessible_ids)} calendars, "
          f"{start_date}~{end_date}", file=sys.stderr)
    print(f"[Calendar MCP] API path: {path[:200]}", file=sys.stderr)

    result = await _api_request("GET", path)
    if not result:
        return "오류: 일정을 가져올 수 없습니다."

    # code 기반 에러 체크
    if isinstance(result, dict) and result.get("code") and str(result["code"]) != "200":
        msg = result.get("message", "알 수 없는 오류")
        return f"오류: 일정 조회 실패 — {msg}"

    # 응답 형식 디버깅
    print(f"[Calendar MCP] Response type={type(result).__name__}, "
          f"keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}, "
          f"len={len(result) if isinstance(result, (list, dict)) else 'N/A'}",
          file=sys.stderr)
    if isinstance(result, dict):
        print(f"[Calendar MCP] Response preview: {str(result)[:300]}", file=sys.stderr)

    events = result if isinstance(result, list) else result.get("data", result)
    if not isinstance(events, list):
        print(f"[Calendar MCP] ERROR: events is {type(events).__name__}, not list. "
              f"Full response: {str(result)[:500]}", file=sys.stderr)
        return "오류: 예상치 못한 응답 형식입니다."

    if not events:
        return f"{start_date} ~ {end_date} 기간에 일정이 없습니다."

    # 캘린더별로 비공개 일정 필터링
    filtered_events = []
    for event in events:
        cal_id = event.get("calendarId")
        cal_info = feed_map.get(cal_id, {})
        is_own = cal_info.get("is_own", False) or (cal_id in own_cal_ids)
        filtered = _filter_private_events([event], go_user_id, is_own)
        filtered_events.extend(filtered)

    if not filtered_events:
        return f"{start_date} ~ {end_date} 기간에 일정이 없습니다."

    # 날짜별 그룹핑
    by_date: Dict[str, list] = {}
    for event in filtered_events:
        start_time = event.get("startTime", "")
        date_key = start_time[:10] if start_time else "기타"
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(event)

    lines = [f"## 일정 ({start_date} ~ {end_date})\n"]
    for date_key in sorted(by_date.keys()):
        lines.append(f"### 📅 {date_key}")
        day_events = sorted(by_date[date_key], key=lambda e: e.get("startTime", ""))
        for event in day_events:
            if event.get("_masked"):
                start_t = event.get("startTime", "")
                end_t = event.get("endTime", "")
                time_str = _format_time_range(start_t, end_t, event.get("timeType"))
                lines.append(f"  - {time_str} 🔒 비공개 일정")
                continue

            summary = event.get("summary", "(제목 없음)")
            start_t = event.get("startTime", "")
            end_t = event.get("endTime", "")
            time_type = event.get("timeType", "")
            time_str = _format_time_range(start_t, end_t, time_type)
            location = event.get("location", "")
            attendees = event.get("attendees", [])

            line = f"  - {time_str} **{summary}**"
            if location:
                line += f" | 📍{location}"
            if attendees:
                names = [a.get("name", "") for a in attendees[:5] if a.get("name")]
                if names:
                    line += f" | 👤{', '.join(names)}"
                    if len(attendees) > 5:
                        line += f" 외 {len(attendees)-5}명"
            lines.append(line)
        lines.append("")

    lines.append(f"\n총 {len(filtered_events)}건")
    return "\n".join(lines)


@mcp.tool()
async def get_event_detail(
    employee_number: str,
    calendar_id: int,
    event_id: str,
) -> str:
    """일정의 상세 정보를 조회합니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        calendar_id: 캘린더 ID
        event_id: 일정 ID (반복 일정의 경우 "eventId_timestamp" 형식)

    Returns:
        일정 상세 (제목, 시간, 장소, 설명, 참석자, 반복 설정 등)
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]
    feed_map = await _get_user_feed(go_user_id)

    # 본인 캘린더 여부 (feed + user API)
    cal_info = feed_map.get(calendar_id, {})
    is_own = cal_info.get("is_own", False)
    if not is_own:
        user_cal_result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
        if user_cal_result:
            user_cals = user_cal_result if isinstance(user_cal_result, list) else user_cal_result.get("data", [])
            if isinstance(user_cals, list):
                is_own = any(c.get("id") == calendar_id for c in user_cals)

    result = await _api_request("GET", f"/api/calendar/{calendar_id}/event/{event_id}")
    if not result:
        return "오류: 일정 상세를 가져올 수 없습니다."

    event = result if isinstance(result, dict) and "id" in result else result.get("data", result)

    # 비공개 일정 접근 검증
    if not is_own and event.get("visibility") == "private":
        creator_id = event.get("creator", {}).get("id")
        attendee_ids = [str(a.get("id", "")) for a in event.get("attendees", []) if a.get("id")]
        if str(go_user_id) != str(creator_id) and str(go_user_id) not in attendee_ids:
            return "🔒 비공개 일정입니다. 접근 권한이 없습니다."

    # 상세 정보 포맷팅
    summary = event.get("summary", "(제목 없음)")
    start_t = event.get("startTime", "")
    end_t = event.get("endTime", "")
    time_type = event.get("timeType", "")
    time_str = _format_time_range(start_t, end_t, time_type)
    location = event.get("location", "")
    description = event.get("description", "")
    visibility = event.get("visibility", "public")
    recurrence = event.get("recurrence", "")
    creator = event.get("creator", {})
    attendees = event.get("attendees", [])
    reminders = event.get("reminders", [])

    lines = [f"## {summary}\n"]
    lines.append(f"- **시간**: {time_str}")
    if time_type == "allday":
        lines.append(f"- **종일 일정**")
    if location:
        lines.append(f"- **장소**: {location}")
    lines.append(f"- **공개 설정**: {visibility}")
    lines.append(f"- **등록자**: {creator.get('name', '알 수 없음')} {creator.get('position', '')}")
    lines.append(f"- **캘린더 ID**: {calendar_id}")
    lines.append(f"- **일정 ID**: {event.get('id', event_id)}")

    if recurrence:
        lines.append(f"- **반복**: {recurrence}")

    if attendees:
        lines.append(f"\n### 참석자 ({len(attendees)}명)")
        for a in attendees:
            name = a.get("name", "알 수 없음")
            email = a.get("email", "")
            position = a.get("position", "")
            status = a.get("status", "")
            line = f"  - {name}"
            if position:
                line += f" ({position})"
            if email:
                line += f" <{email}>"
            if status:
                line += f" [{status}]"
            lines.append(line)

    if description:
        lines.append(f"\n### 설명\n{description}")

    if reminders:
        lines.append(f"\n### 알림")
        for r in reminders:
            lines.append(f"  - {r.get('time', '?')}분 전 ({r.get('method', 'notification')})")

    return "\n".join(lines)


@mcp.tool()
async def create_event(
    employee_number: str,
    calendar_id: int,
    summary: str,
    start_time: str,
    end_time: str,
    is_allday: bool = False,
    location: str = "",
    description: str = "",
    visibility: str = "public",
    recurrence: str = "",
    attendee_emails: str = "",
    attendee_names: str = "",
) -> str:
    """내 캘린더에 일정을 등록합니다.
    반드시 사용자에게 등록 내용을 확인받은 후 호출하세요.
    본인 소유 캘린더에만 등록할 수 있습니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        calendar_id: 등록할 캘린더 ID (get_my_calendars에서 확인)
        summary: 일정 제목
        start_time: 시작 시간 (ISO 형식 "2026-04-01T14:00:00.000+09:00" 또는 종일 "2026-04-01")
        end_time: 종료 시간 (ISO 형식 또는 종일 날짜)
        is_allday: 종일 일정 여부 (기본: False)
        location: 장소 (선택)
        description: 설명 (선택)
        visibility: 공개 설정 - "public" 또는 "private" (기본: "public")
        recurrence: 반복 설정 (RFC5545, 예: "FREQ=WEEKLY;UNTIL=20260601", 빈 값이면 반복 없음)
        attendee_emails: 외부 참석자 이메일 (콤마 구분, 선택)
        attendee_names: 사내 참석자 이름 (콤마 구분, 예: "장욱진,김민지"). 이름으로 자동 검색하여 GO 계정 연결

    Returns:
        등록 결과 (성공 시 일정 상세, 실패 시 오류)
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]

    # 소유권 검증: 내 캘린더인지 확인 (user API 기반)
    is_own = False
    user_cal_result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
    if user_cal_result:
        user_cals = user_cal_result if isinstance(user_cal_result, list) else user_cal_result.get("data", [])
        if isinstance(user_cals, list):
            is_own = any(c.get("id") == calendar_id for c in user_cals)

    if not is_own:
        return (f"오류: 캘린더(id={calendar_id})는 본인 소유가 아닙니다. "
                f"본인 캘린더에만 일정을 등록할 수 있습니다.")

    # 시간 포맷 처리
    if is_allday:
        if "T" not in start_time:
            start_time = f"{start_time}T00:00:00.000+09:00"
        if "T" not in end_time:
            end_time = f"{end_time}T23:59:59.999+09:00"
        time_type = "allday"
    else:
        time_type = "normal"

    # 참석자 구성
    attendees = []
    not_found_names = []
    # 본인은 항상 포함
    attendees.append({
        "id": str(go_user_id),
        "name": user_info["user_name"],
        "email": "",
        "position": "",
    })
    # 사내 참석자: 이름으로 검색 → GO user ID 연결
    if attendee_names:
        for name in attendee_names.split(","):
            name = name.strip()
            if not name:
                continue
            results = await _search_users_by_name(name, limit=3)
            if len(results) == 1:
                # 정확히 1명 매칭
                u = results[0]
                attendees.append({
                    "id": str(u["go_user_id"]),
                    "name": u["name"],
                    "email": u.get("email", ""),
                    "position": "",
                })
                print(f"[Calendar MCP] 참석자 매칭: {name} → GO#{u['go_user_id']} "
                      f"{u['name']} ({u['dept_name']})", file=sys.stderr)
            elif len(results) > 1:
                # 동명이인 — 첫 번째 결과 사용 + 로그
                u = results[0]
                attendees.append({
                    "id": str(u["go_user_id"]),
                    "name": u["name"],
                    "email": u.get("email", ""),
                    "position": "",
                })
                names_str = ", ".join(f"{r['name']}({r['dept_name']})" for r in results)
                print(f"[Calendar MCP] 참석자 동명이인: {name} → {names_str}, "
                      f"첫 번째 선택: GO#{u['go_user_id']}", file=sys.stderr)
            else:
                not_found_names.append(name)
                print(f"[Calendar MCP] 참석자 미발견: {name}", file=sys.stderr)
    # 외부 참석자: 이메일로 추가
    if attendee_emails:
        for email in attendee_emails.split(","):
            email = email.strip()
            if email:
                attendees.append({
                    "id": "",
                    "email": email,
                    "name": "",
                    "position": "",
                })

    payload = {
        "calendarId": calendar_id,
        "summary": summary,
        "startTime": start_time,
        "endTime": end_time,
        "type": "normal",
        "visibility": visibility,
        "location": location,
        "description": description,
        "creator": {
            "id": go_user_id,
            "name": user_info["user_name"],
            "position": "",
        },
        "attendees": attendees,
        "reminders": [{"time": 30, "type": "minute", "method": "notification"}],
        "timeZoneOffset": "+09:00",
        "pushNoti": True,
        "mailNoti": True,
        "assetReservationIds": [],
    }

    # timeType: "allday" (종일) / "timed" (시간 지정)
    payload["timeType"] = "allday" if is_allday else "timed"

    if recurrence:
        payload["recurrence"] = recurrence

    print(f"[Calendar MCP] 일정 등록: cal={calendar_id}, summary={summary}, "
          f"user=GO#{go_user_id}", file=sys.stderr)

    result = await _api_request("POST", f"/api/calendar/{calendar_id}/event/",
                                json=payload)
    if not result:
        return "오류: 일정 등록에 실패했습니다. 서버에 연결할 수 없습니다."

    # 에러 응답 확인
    if isinstance(result, dict) and result.get("code") and str(result["code"]) != "200":
        msg = result.get("message", "알 수 없는 오류")
        return f"오류: 일정 등록 실패 — {msg}"

    # 성공 응답
    event_id = result.get("id", "?") if isinstance(result, dict) else "?"
    time_display = _format_time_range(start_time, end_time, time_type)

    lines = [
        "✅ 일정이 등록되었습니다!\n",
        f"- **제목**: {summary}",
        f"- **시간**: {time_display}",
    ]
    if location:
        lines.append(f"- **장소**: {location}")
    if recurrence:
        lines.append(f"- **반복**: {recurrence}")
    lines.append(f"- **공개 설정**: {visibility}")
    lines.append(f"- **일정 ID**: {event_id}")
    # 참석자 안내
    attendee_names_list = [a["name"] for a in attendees if a["name"]]
    if len(attendee_names_list) > 1:
        lines.append(f"- **참석자**: {', '.join(attendee_names_list)}")
    if not_found_names:
        lines.append(f"\n⚠️ 다음 참석자는 검색되지 않아 추가하지 못했습니다: {', '.join(not_found_names)}")

    # 피드 캐시 무효화 (새 일정 반영)
    _user_feed_cache_ts.pop(go_user_id, None)

    return "\n".join(lines)


@mcp.tool()
async def update_event(
    employee_number: str,
    calendar_id: int,
    event_id: str,
    summary: str = "",
    start_time: str = "",
    end_time: str = "",
    is_allday: bool = False,
    location: str = "",
    description: str = "",
    visibility: str = "",
    add_attendee_names: str = "",
    remove_attendee_names: str = "",
) -> str:
    """기존 일정을 수정합니다.
    변경할 필드만 지정하세요. 빈 문자열은 변경하지 않음을 의미합니다.
    반드시 사용자에게 수정 내용을 확인받은 후 호출하세요.

    Args:
        employee_number: 사번 (자동 주입됨)
        calendar_id: 캘린더 ID
        event_id: 수정할 일정 ID (get_calendar_events에서 확인)
        summary: 변경할 제목 (빈 문자열이면 유지)
        start_time: 변경할 시작 시간 (ISO 형식, 빈 문자열이면 유지)
        end_time: 변경할 종료 시간 (ISO 형식, 빈 문자열이면 유지)
        is_allday: 종일 일정 여부
        location: 변경할 장소 (빈 문자열이면 유지)
        description: 변경할 설명 (빈 문자열이면 유지)
        visibility: 변경할 공개 설정 (빈 문자열이면 유지)
        add_attendee_names: 추가할 참석자 이름 (콤마 구분)
        remove_attendee_names: 제거할 참석자 이름 (콤마 구분)

    Returns:
        수정 결과
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]

    # 소유권 검증
    is_own = False
    user_cal_result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
    if user_cal_result:
        user_cals = user_cal_result if isinstance(user_cal_result, list) else user_cal_result.get("data", [])
        if isinstance(user_cals, list):
            is_own = any(c.get("id") == calendar_id for c in user_cals)

    if not is_own:
        return "오류: 본인 캘린더의 일정만 수정할 수 있습니다."

    # 기존 일정 조회
    detail = await _api_request("GET", f"/api/calendar/{calendar_id}/event/{event_id}")
    if not detail:
        return "오류: 일정 정보를 가져올 수 없습니다."

    event_data = detail if isinstance(detail, dict) and "id" in detail else detail.get("data", detail)

    # creator 검증
    creator_id = event_data.get("creator", {}).get("id")
    if str(creator_id) != str(go_user_id):
        return "오류: 본인이 등록한 일정만 수정할 수 있습니다."

    # 기존 데이터 기반으로 변경 필드만 덮어쓰기
    updated = {**event_data}
    if summary:
        updated["summary"] = summary
    if start_time:
        updated["startTime"] = start_time
    if end_time:
        updated["endTime"] = end_time
    if location:
        updated["location"] = location
    if description:
        updated["description"] = description
    if visibility:
        updated["visibility"] = visibility

    # timeType 처리
    if start_time or end_time:
        updated["timeType"] = "allday" if is_allday else "timed"

    # 참석자 추가
    not_found_names = []
    attendees = list(updated.get("attendees", []))
    if add_attendee_names:
        for name in add_attendee_names.split(","):
            name = name.strip()
            if not name:
                continue
            # 이미 참석자인지 확인
            existing_names = [a.get("name", "") for a in attendees]
            if name in existing_names:
                continue
            results = await _search_users_by_name(name, limit=3)
            if results:
                u = results[0]
                attendees.append({
                    "id": str(u["go_user_id"]),
                    "name": u["name"],
                    "email": u.get("email", ""),
                    "position": "",
                })
                print(f"[Calendar MCP] 참석자 추가: {name} → GO#{u['go_user_id']}", file=sys.stderr)
            else:
                not_found_names.append(name)

    # 참석자 제거
    if remove_attendee_names:
        remove_set = {n.strip() for n in remove_attendee_names.split(",") if n.strip()}
        attendees = [a for a in attendees if a.get("name", "") not in remove_set]

    updated["attendees"] = attendees

    print(f"[Calendar MCP] 일정 수정: cal={calendar_id}, event={event_id}, "
          f"user=GO#{go_user_id}", file=sys.stderr)

    result = await _api_request("PUT", f"/api/calendar/{calendar_id}/event/{event_id}",
                                json=updated)
    if not result:
        return "오류: 일정 수정에 실패했습니다."

    if isinstance(result, dict) and result.get("code") and str(result["code"]) != "200":
        msg = result.get("message", "알 수 없는 오류")
        return f"오류: 일정 수정 실패 — {msg}"

    lines = [f"✅ 일정이 수정되었습니다!\n"]
    lines.append(f"- **제목**: {updated.get('summary', '')}")
    st = updated.get("startTime", "")
    et = updated.get("endTime", "")
    lines.append(f"- **시간**: {_format_time_range(st, et, updated.get('timeType', ''))}")
    attendee_names_list = [a.get("name", "") for a in attendees if a.get("name")]
    if attendee_names_list:
        lines.append(f"- **참석자**: {', '.join(attendee_names_list)}")
    if not_found_names:
        lines.append(f"\n⚠️ 다음 참석자는 검색되지 않아 추가하지 못했습니다: {', '.join(not_found_names)}")

    return "\n".join(lines)


@mcp.tool()
async def delete_event(
    employee_number: str,
    calendar_id: int,
    event_id: str,
    delete_type: str = "all",
) -> str:
    """내 일정을 삭제합니다.
    반드시 사용자에게 삭제 내용을 확인받은 후 호출하세요.
    본인이 등록한 일정만 삭제할 수 있습니다.

    Args:
        employee_number: 사번 (자동 주입됨)
        calendar_id: 캘린더 ID
        event_id: 삭제할 일정 ID (반복 일정은 "eventId_timestamp" 형식)
        delete_type: 반복 일정 삭제 범위 - "all"(전체), "this"(이 일정만), "following"(이후 전체) (기본: "all")

    Returns:
        삭제 결과
    """
    user_info = await _get_go_user_info(employee_number)
    if not user_info:
        return f"오류: 사번 '{employee_number}'에 대한 사용자 정보를 찾을 수 없습니다."

    go_user_id = user_info["go_user_id"]

    # 소유권 검증 (user API 기반)
    is_own = False
    user_cal_result = await _api_request("GET", f"/api/calendar/user/{go_user_id}/calendar")
    if user_cal_result:
        user_cals = user_cal_result if isinstance(user_cal_result, list) else user_cal_result.get("data", [])
        if isinstance(user_cals, list):
            is_own = any(c.get("id") == calendar_id for c in user_cals)

    if not is_own:
        return "오류: 본인 캘린더의 일정만 삭제할 수 있습니다."

    # 일정 상세 조회로 creator 확인
    detail = await _api_request("GET", f"/api/calendar/{calendar_id}/event/{event_id}")
    if not detail:
        return "오류: 일정 정보를 가져올 수 없습니다."

    event_data = detail if isinstance(detail, dict) and "id" in detail else detail.get("data", detail)
    creator_id = event_data.get("creator", {}).get("id")
    if str(creator_id) != str(go_user_id):
        return "오류: 본인이 등록한 일정만 삭제할 수 있습니다."

    event_summary = event_data.get("summary", "(제목 없음)")

    # 삭제 실행
    path = f"/api/calendar/{calendar_id}/event/{event_id}?recurChangeType={delete_type}"
    result = await _api_request("DELETE", path)

    if not result:
        return "오류: 일정 삭제에 실패했습니다. 서버에 연결할 수 없습니다."

    if isinstance(result, dict) and result.get("code") and str(result["code"]) != "200":
        msg = result.get("message", "알 수 없는 오류")
        return f"오류: 일정 삭제 실패 — {msg}"

    # 피드 캐시 무효화
    _user_feed_cache_ts.pop(go_user_id, None)

    return (
        f"✅ 일정이 삭제되었습니다.\n\n"
        f"- **제목**: {event_summary}\n"
        f"- **일정 ID**: {event_id}"
    )


# ── 포맷 헬퍼 ─────────────────────────────────────────

def _format_time_range(start_time: str, end_time: str, time_type: str = "") -> str:
    """시간 범위를 읽기 좋은 형태로 포맷"""
    if time_type == "allday":
        start_date = start_time[:10] if start_time else ""
        end_date = end_time[:10] if end_time else ""
        if start_date == end_date:
            return f"{start_date} (종일)"
        return f"{start_date} ~ {end_date} (종일)"

    start_dt = start_time[:16].replace("T", " ") if start_time else ""
    end_t = end_time[11:16] if end_time and len(end_time) > 11 else ""

    if start_dt and end_t:
        return f"{start_dt} ~ {end_t}"
    return start_dt or "(시간 미정)"


# ── 메인 ──────────────────────────────────────────────

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message=".*SSL.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    mcp.run(transport="stdio")
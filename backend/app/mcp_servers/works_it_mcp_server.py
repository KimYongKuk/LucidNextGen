"""IT/보안 VOC Knowledge Base MCP 서버

IT/보안 지원요청 해결 사례를 검색하고,
WORKS 서비스데스크(앱릿 934)에 VOC를 등록하는 MCP 서버입니다.
v_works_app_934_data 뷰를 통해 과거 해결 사례를 조회합니다.

참고: LFON은 사내 그룹웨어 시스템명입니다.
"""
import sys
import os
import asyncpg
import re
import httpx
import mimetypes
from pathlib import Path as FilePath
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

mcp = FastMCP("IT VOC Knowledge Base Server v1")

# PostgreSQL 연결 정보 (TIMS DB)
DATABASE_URL = "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"

# LFON Works API 설정
LFON_BASE_URL = os.getenv("LFON_BASE_URL", "https://lfon.landf.co.kr")
LFON_WORKS_TOKEN = os.getenv("LFON_WORKS_TOKEN", "")
LFON_SSO_USERNAME = os.getenv("LFON_SSO_USERNAME", "")
LFON_SSO_PASSWORD = os.getenv("LFON_SSO_PASSWORD", "")
WORKS_APPLET_ID = os.getenv("WORKS_APPLET_ID", "934")

# 시스템명 → 시스템 코드 매핑 (앱릿 934 드롭박스 값)
SYSTEM_NAME_TO_CODE = {
    "SAP": "0", "LFON": "1", "DLP": "2", "DRM": "3",
    "네트워크": "4", "SW": "5", "HW": "6", "기타": "7",
    "HR": "8", "EHS": "9", "NAS": "13", "보안성 검토": "14",
    "MDM": "15", "AD": "17", "MES": "18", "VPN": "19",
}

# 시스템 코드 → 담당 부서명(들) 매핑 (1 시스템 → N 부서 허용)
# 튜플 값이어야 함 (_get_dept_members 가 리스트/튜플 받음)
SYSTEM_CODE_TO_DEPTS = {
    "0":  ("ERP파트",),           "1":  ("DA파트",),
    "2":  ("보안기술팀",),        "3":  ("보안기술팀",),
    "4":  ("IT인프라팀",),        "5":  ("IT인프라팀",),
    "6":  ("IT인프라팀",),        "8":  ("ERP파트",),
    "9":  ("DA파트",),            "13": ("IT인프라팀",),
    "14": ("보안기술팀", "보안관리파트"),  # 보안성 검토: 기술+관리 공동
    "15": ("보안기술팀",),        "17": ("IT인프라팀",),
    "18": ("DX파트",),            "19": ("보안기술팀",),
}

# 담당자로 지정할 직위 (v_org_chart."직위")
# 팀원/NULL은 제외하고 파트장/책임 직위만 배정 대상
# 주의: "직책"(duty, 파트장/팀원)과 "직위"(position, 책임/선임)는 별개 필드
ASSIGNEE_ALLOWED_POSITIONS = ("파트장", "책임")

# 업로드 원본 디렉터리 (backend/data/user_uploads/{date}/{user_id}/{filename})
USER_UPLOAD_DIR = FilePath(__file__).parent.parent.parent / "data" / "user_uploads"

# Works 첨부 필드 ID (앱릿 934 / 1445 동일 구조 확인됨 — 다를 경우 env var로 override)
WORKS_ATTACHMENT_FIELD = os.getenv("WORKS_ATTACHMENT_FIELD", "_14v07o8vj")

# 전역 연결 풀
_db_pool: Optional[asyncpg.Pool] = None

# 사용자 정보 캐시 (프로세스 수명)
# 사번 → {user_id, login_id, name, dept_id, dept_name, employee_number}
_user_info_cache: dict = {}

# SSO 쿠키 캐시
_sso_cookies: Optional[dict] = None


async def get_db_pool() -> asyncpg.Pool:
    """PostgreSQL 연결 풀 가져오기 (싱글톤)"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30
        )
        print("IT VOC DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


async def _get_user_full_info(employee_number: str) -> Optional[dict]:
    """사번으로 LFON 사용자 전체 정보 조회 (user_id, login_id, name, dept_id, dept_name)"""
    if employee_number in _user_info_cache:
        return _user_info_cache[employee_number]

    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, login_id, name, dept_id, dept_name
                FROM v_user_info_mapping
                WHERE employee_number = $1
                """,
                employee_number,
            )
        if not row:
            print(f"[IT VOC MCP] 사용자 미발견: {employee_number}", file=sys.stderr)
            return None

        info = {
            "user_id": row["user_id"],
            "login_id": row["login_id"],
            "name": row["name"],
            "dept_id": row["dept_id"],
            "dept_name": row["dept_name"],
            "employee_number": employee_number,
        }
        _user_info_cache[employee_number] = info
        print(f"[IT VOC MCP] 사용자 조회: {employee_number} → {info['name']}({info['dept_name']})", file=sys.stderr)
        return info
    except Exception as e:
        print(f"[IT VOC MCP] 사용자 조회 실패: {e}", file=sys.stderr)
        return None


async def _get_dept_members(dept_names: tuple[str, ...] | list[str]) -> list[dict]:
    """부서명(들)로 해당 부서의 멤버 중 ASSIGNEE_ALLOWED_POSITIONS 직위만 조회

    dept_names 에 여러 부서명을 넣으면 합쳐서 조회 (보안성 검토처럼 공동 담당 케이스).
    """
    dept_list = list(dept_names)
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.user_id, m.login_id, m.name, m.dept_id, m.dept_name, m.employee_number
                FROM v_user_info_mapping m
                JOIN v_org_chart o ON m.user_id = o.user_id
                WHERE m.dept_name = ANY($1::text[])
                  AND o."직위" = ANY($2::text[])
                """,
                dept_list,
                list(ASSIGNEE_ALLOWED_POSITIONS),
            )
        members = [dict(r) for r in rows]
        positions = "/".join(ASSIGNEE_ALLOWED_POSITIONS)
        depts_label = "/".join(dept_list)
        print(f"[IT VOC MCP] 부서 멤버 조회: {depts_label} ({positions}) → {len(members)}명", file=sys.stderr)
        return members
    except Exception as e:
        print(f"[IT VOC MCP] 부서 멤버 조회 실패: {e}", file=sys.stderr)
        return []


async def _sso_login() -> Optional[dict]:
    """LFON SSO 로그인하여 쿠키 확보 (캐싱)"""
    global _sso_cookies
    if _sso_cookies:
        return _sso_cookies

    if not LFON_SSO_USERNAME or not LFON_SSO_PASSWORD:
        print("[IT VOC MCP] SSO 인증 정보 미설정", file=sys.stderr)
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
                print(f"[IT VOC MCP] SSO 로그인 성공: {LFON_SSO_USERNAME}", file=sys.stderr)
                return _sso_cookies
            else:
                print(f"[IT VOC MCP] SSO 로그인 실패: status={resp.status_code}", file=sys.stderr)
                return None
    except Exception as e:
        print(f"[IT VOC MCP] SSO 로그인 오류: {e}", file=sys.stderr)
        return None


def _build_assignee_obj(member: dict) -> dict:
    """v_user_info_mapping 행을 LFON 담당자 객체로 변환"""
    login_id = str(member["login_id"])
    return {
        "id": member["user_id"],
        "name": member["name"],
        "type": "MASTER",
        "deptId": member["dept_id"],
        "deptName": member["dept_name"],
        "employeeNumber": member["employee_number"],
        "loginId": login_id,
        "email": f"{login_id}@landf.co.kr",
        "originalEmail": f"{login_id}@landf.co.kr",
        "companyName": "엘앤에프",
    }


# 앱릿 934 상태 전환 Action ID
ACTION_ACCEPT = 2545       # 접수
ACTION_ASSIGN = 2619       # 담당자지정


async def _transition_status(doc_id: int, action_id: int, cookies: dict) -> bool:
    """VOC 문서 상태 전환 (접수, 담당자지정 등)"""
    try:
        async with httpx.AsyncClient(
            base_url=LFON_BASE_URL, timeout=15, verify=False, cookies=cookies,
        ) as client:
            resp = await client.put(
                f"/api/works/applets/{WORKS_APPLET_ID}/docs/{doc_id}/actions/{action_id}",
                json={},
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "TimeZoneOffset": "540",
                },
            )
            success = resp.status_code == 200
            print(f"[IT VOC MCP] 상태전환 doc={doc_id} action={action_id}: {'성공' if success else f'실패({resp.status_code})'}", file=sys.stderr)
            return success
    except Exception as e:
        print(f"[IT VOC MCP] 상태전환 오류 doc={doc_id} action={action_id}: {e}", file=sys.stderr)
        return False


def _resolve_attachment_path(filename: str, user_id: str) -> Optional[FilePath]:
    """업로드된 파일명을 USER_UPLOAD_DIR 하위 실제 경로로 resolve.

    보안:
    - 경로 구분자(/ \) 포함 금지
    - .. 포함 금지
    - USER_UPLOAD_DIR 하위 user_id 디렉터리 스코프로만 탐색
    - 여러 날짜에 동일 파일명 존재 시 최근 mtime 우선
    """
    if not filename or not user_id:
        return None
    if any(sep in filename for sep in ("/", "\\")) or ".." in filename:
        print(f"[IT VOC MCP] 첨부 경로 거부(탈출 시도): {filename}", file=sys.stderr)
        return None

    safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
    if not USER_UPLOAD_DIR.exists():
        return None

    candidates = []
    for date_dir in USER_UPLOAD_DIR.iterdir():
        if not date_dir.is_dir():
            continue
        user_dir = date_dir / safe_uid
        if not user_dir.is_dir():
            continue
        cand = user_dir / filename
        if cand.is_file():
            candidates.append(cand)

    if not candidates:
        print(f"[IT VOC MCP] 첨부 파일 미발견: {filename} (user={safe_uid})", file=sys.stderr)
        return None

    # 최근 수정 파일 우선
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    resolved = candidates[0].resolve()
    if not str(resolved).startswith(str(USER_UPLOAD_DIR.resolve())):
        print(f"[IT VOC MCP] 첨부 경로 거부(범위 이탈): {resolved}", file=sys.stderr)
        return None
    return resolved


def _dbg_log(msg: str):
    """MCP stderr가 부모 프로세스에 안 찍힐 때를 대비한 파일 로그.
    backend/data/logs/works_it_debug.log 에 append. 문제 해결 후 제거 가능.
    """
    try:
        from datetime import datetime
        log_dir = FilePath(__file__).parent.parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_dir / "works_it_debug.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


async def _upload_file_to_works(cookies: dict, file_path: FilePath) -> Optional[dict]:
    """WORKS 내부 파일 업로드 API 호출.
    Returns: {id, path, name, hostId} or None on failure.
    """
    gosso = cookies.get("GOSSOcookie") or cookies.get("gossocookie") or ""
    file_name = file_path.name
    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "application/octet-stream"

    _dbg_log(f"UPLOAD START: file={file_name}, size={file_path.stat().st_size}B, mime={mime}, gosso_len={len(gosso)}, cookie_keys={list(cookies.keys())}, applet={WORKS_APPLET_ID}")

    try:
        with open(file_path, "rb") as f:
            content = f.read()

        async with httpx.AsyncClient(
            base_url=LFON_BASE_URL, timeout=120, verify=False, follow_redirects=True,
            cookies=cookies,
        ) as client:
            resp = await client.post(
                f"/api/file?GOSSOcookie={gosso}",
                files={"file": (file_name, content, mime)},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "TimeZoneOffset": "540",
                    "Referer": f"{LFON_BASE_URL}/app/works/applet/{WORKS_APPLET_ID}/doc/new/0",
                },
            )

            _dbg_log(f"UPLOAD RESPONSE: status={resp.status_code}, headers={dict(resp.headers)}, body={resp.text[:800]}")

            if resp.status_code != 200:
                msg = f"파일 업로드 실패: {file_name} status={resp.status_code} body={resp.text[:300]}"
                print(f"[IT VOC MCP] {msg}", file=sys.stderr)
                _dbg_log(msg)
                return None

            try:
                data = resp.json()
            except Exception as je:
                _dbg_log(f"JSON parse failed: {je} / raw: {resp.text[:300]}")
                print(f"[IT VOC MCP] 파일 업로드 응답 JSON 파싱 실패: {je}", file=sys.stderr)
                return None

            # 응답이 배열로 감싸진 경우 첫 항목 사용
            if isinstance(data, list) and data:
                data = data[0]
            if not isinstance(data, dict):
                msg = f"파일 업로드 응답 형식 이상: {str(data)[:200]}"
                print(f"[IT VOC MCP] {msg}", file=sys.stderr)
                _dbg_log(msg)
                return None

            # 실제 응답 구조: {code, message, data: {hostId, fileName, filePath, ...}}
            # VOC body의 _14v07o8vj 필드 포맷은 {id, path, name, hostId}이므로 매핑 필요
            inner = data.get("data") if isinstance(data.get("data"), dict) else data

            meta = {
                "id": inner.get("id"),  # 신규 업로드 시엔 보통 None
                "path": inner.get("filePath") or inner.get("path"),
                "name": inner.get("fileName") or inner.get("name") or file_name,
                "hostId": inner.get("hostId"),
            }
            if not meta["path"] or not meta["hostId"]:
                msg = f"파일 업로드 응답 필드 누락: {meta} / full response keys={list(data.keys())}, inner keys={list(inner.keys()) if isinstance(inner, dict) else '?'}"
                print(f"[IT VOC MCP] {msg}", file=sys.stderr)
                _dbg_log(msg)
                return None
            print(f"[IT VOC MCP] 파일 업로드 성공: {file_name} → {meta['path']}", file=sys.stderr)
            _dbg_log(f"UPLOAD SUCCESS: {file_name} → {meta}")
            return meta
    except Exception as e:
        import traceback
        msg = f"파일 업로드 오류: {file_name}: {e}\n{traceback.format_exc()}"
        print(f"[IT VOC MCP] {msg}", file=sys.stderr)
        _dbg_log(msg)
        return None


# SAP RFC Bridge 설정
SAP_RFC_BRIDGE_URL = os.getenv("SAP_RFC_BRIDGE_URL", "http://192.168.100.72:8001")


async def _resolve_employee_number(identifier: str) -> Optional[str]:
    """login_id(wg0403) 또는 employee_number(A2304013)를 사번으로 해석"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # login_id로 먼저 조회
            row = await conn.fetchrow(
                "SELECT employee_number FROM v_user_info_mapping WHERE login_id = $1",
                identifier,
            )
            if row:
                print(f"[IT VOC MCP] login_id→사번: {identifier} → {row['employee_number']}", file=sys.stderr)
                return row["employee_number"]
            # 이미 사번인 경우 확인
            row = await conn.fetchrow(
                "SELECT employee_number FROM v_user_info_mapping WHERE employee_number = $1",
                identifier,
            )
            if row:
                print(f"[IT VOC MCP] 사번 확인: {identifier}", file=sys.stderr)
                return identifier
        print(f"[IT VOC MCP] 사용자 미발견: {identifier}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[IT VOC MCP] 사번 해석 오류: {e}", file=sys.stderr)
        return None


@mcp.tool()
async def reset_sap_password(employee_number: str, system: str = "prd") -> str:
    """SAP 비밀번호를 초기화합니다. 초기화 비밀번호는 Pass1234567890! 입니다.
    사용자가 "SAP 비밀번호 초기화", "SAP 패스워드 리셋" 등을 요청할 때 호출하세요.

    employee_number: 시스템이 자동 주입합니다. 호출 시 아무 값이나 넣으세요.
    system: 대상 SAP 시스템. "prd"(운영, 기본값) 또는 "dev"(개발).
        사용자가 "개발 SAP", "DEV", "개발 서버" 등을 언급하면 "dev"로 호출.
        일반적인 경우는 "prd"(운영)로 호출.
    """
    system_norm = (system or "prd").lower()
    if system_norm not in ("dev", "prd"):
        return f"오류: 지원하지 않는 system 값입니다 ('{system}'). 'dev' 또는 'prd'만 가능합니다."

    print(f"\n[IT VOC MCP] SAP 패스워드 초기화 요청: emp={employee_number}, system={system_norm}", file=sys.stderr)

    # login_id 또는 employee_number → 사번으로 해석
    emp_no = await _resolve_employee_number(employee_number)
    if not emp_no:
        return f"오류: '{employee_number}'에 해당하는 사원번호를 찾을 수 없습니다."

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{SAP_RFC_BRIDGE_URL}/rfc/call",
                json={
                    "function_name": "Z02CMF_PASSWORD_INIT",
                    "params": {"I_EMP_NO": emp_no},
                    "system": system_norm,
                },
            )
            data = resp.json()
            sys_label = "운영(PRD)" if system_norm == "prd" else "개발(DEV)"
            if data.get("success") and data.get("data"):
                es_return = data["data"].get("ES_RETURN", data["data"].get("ES_RESULT", {}))
                retcd = es_return.get("RETCD", "")
                retmg = es_return.get("RETMG", "")
                if retcd == "S":
                    print(f"[IT VOC MCP] SAP 패스워드 초기화 성공: {emp_no} ({system_norm})", file=sys.stderr)
                    return (
                        f"성공 [{sys_label}]: {retmg}\n"
                        f"초기화 비밀번호: Pass1234567890!\n"
                        f"(첫 로그인 시 반드시 변경하세요)"
                    )
                else:
                    print(f"[IT VOC MCP] SAP 패스워드 초기화 실패: {retmg} ({system_norm})", file=sys.stderr)
                    return f"실패 [{sys_label}] (RETCD={retcd}): {retmg}"
            else:
                error = data.get("error", "알 수 없는 오류")
                print(f"[IT VOC MCP] SAP RFC 호출 오류: {error} ({system_norm})", file=sys.stderr)
                return f"RFC 호출 오류 [{sys_label}]: {error}"
    except Exception as e:
        print(f"[IT VOC MCP] SAP RFC Bridge 연결 오류: {e}", file=sys.stderr)
        return f"SAP RFC Bridge 연결 실패: {e}\nBridge 서비스(192.168.100.72:8001) 상태를 확인하세요."


@mcp.tool()
async def execute_it_voc_query(sql_query: str) -> str:
    """IT VOC SQL 실행. SELECT만 허용, v_works_app_934_data 뷰 사용."""
    # 쿼리 수신 로그
    print("\n" + "="*80, file=sys.stderr)
    print("[IT VOC MCP] 쿼리 요청 수신", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"받은 쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    validation_steps = []  # 검증 과정 기록

    # 실행된 쿼리 기록 (디버깅용)
    validation_steps.append("[실행된 SQL 쿼리]")
    validation_steps.append(f"```sql\n{sql_query}\n```")
    validation_steps.append("")

    # 검증 1: SELECT만 허용
    validation_steps.append("1단계: SELECT 쿼리 검증")
    print("[검증 1/4] SELECT 쿼리 확인 중...", file=sys.stderr)
    if not sql_query.strip().upper().startswith('SELECT'):
        print("[검증 1/4] 실패: SELECT가 아닌 쿼리\n", file=sys.stderr)
        validation_steps.append("   실패: SELECT 쿼리만 허용됩니다")
        return "\n".join(validation_steps) + "\n\n오류: SELECT 쿼리만 실행 가능합니다."
    print("[검증 1/4] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 2: v_works_app_934_data 뷰 확인
    validation_steps.append("2단계: 대상 뷰 확인")
    print("[검증 2/4] 대상 뷰 확인 중...", file=sys.stderr)
    query_upper = sql_query.upper()
    if 'V_WORKS_APP_934_DATA' not in query_upper:
        print("[검증 2/4] 실패: v_works_app_934_data 뷰 미사용\n", file=sys.stderr)
        validation_steps.append("   실패: v_works_app_934_data 뷰를 사용해야 합니다")
        return "\n".join(validation_steps) + "\n\n오류: v_works_app_934_data 뷰만 접근 가능합니다.\n가이드의 쿼리 예제를 참고하세요."
    print("[검증 2/4] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 3: 조치내역 IS NOT NULL 권장 (경고만, 차단 안함)
    validation_steps.append("3단계: 조치내역 필터 확인")
    print("[검증 3/4] 조치내역 필터 확인 중...", file=sys.stderr)
    if '조치내역' not in sql_query or 'IS NOT NULL' not in query_upper:
        print("[검증 3/4] 경고: 조치내역 IS NOT NULL 조건 누락\n", file=sys.stderr)
        validation_steps.append("   경고: 조치내역 IS NOT NULL 조건을 추가하면 해결된 건만 조회됩니다")
    else:
        print("[검증 3/4] 통과\n", file=sys.stderr)
        validation_steps.append("   통과")

    # 검증 4: 위험한 SQL 명령어 (단어 경계 체크)
    validation_steps.append("4단계: 위험 SQL 명령어 스캔")
    print("[검증 4/4] 위험 SQL 명령어 스캔 중...", file=sys.stderr)

    dangerous_patterns = [
        r'\bDROP\b',
        r'\bDELETE\b',
        r'\bUPDATE\b',
        r'\bINSERT\b',
        r'\bTRUNCATE\b',
        r'\bALTER\b',
        r'\bCREATE\b',
        r';.*(DROP|DELETE|UPDATE|INSERT|TRUNCATE)',
    ]

    found_dangerous = []
    for pattern in dangerous_patterns:
        if re.search(pattern, query_upper):
            keyword = pattern.replace(r'\b', '').replace('\\', '')
            found_dangerous.append(keyword)

    if found_dangerous:
        print(f"[검증 4/4] 실패: 금지된 SQL 명령어 - {', '.join(found_dangerous)}\n", file=sys.stderr)
        validation_steps.append(f"   실패: 금지된 SQL 명령어 발견 - {', '.join(found_dangerous)}")
        return "\n".join(validation_steps) + f"\n\n오류: 읽기 전용(SELECT)만 허용됩니다. 금지된 명령어: {', '.join(found_dangerous)}"
    print("[검증 4/4] 통과 (읽기 전용 쿼리 확인)\n", file=sys.stderr)
    validation_steps.append("   통과 (읽기 전용 쿼리 확인)")

    # 실제 PostgreSQL 쿼리 실행
    validation_steps.append("5단계: PostgreSQL 쿼리 실행")

    print("\n" + "="*80, file=sys.stderr)
    print("[IT VOC MCP] SQL 쿼리 실행", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_query)

            print(f"[IT VOC MCP] 쿼리 실행 성공: {len(rows)}건 조회됨\n", file=sys.stderr)

            if not rows:
                validation_steps.append("   결과: 0건")
                return "\n".join(validation_steps) + "\n\n조회된 IT VOC 사례가 없습니다.\n\n키워드를 분리하거나 유의어로 변경하여 재검색해보세요.\n(예: '인터넷이 느려요' -> '네트워크' or '지연' or '접속')"

            validation_steps.append(f"   성공: {len(rows)}건 조회됨")

            # 첫 번째 행의 컬럼명 확인하여 쿼리 유형 판단
            first_row = dict(rows[0])
            is_voc_search = '요약' in first_row or 'summary' in first_row

            if is_voc_search:
                # VOC 검색 결과 포맷팅 (기존 로직)
                result_text = "\n".join(validation_steps) + f"\n\nIT VOC 검색 결과 ({len(rows)}건)\n\n"

                for idx, row in enumerate(rows, 1):
                    row_dict = dict(row)

                    # 주요 필드 추출
                    summary = row_dict.get('요약', row_dict.get('summary', 'N/A'))
                    detail = row_dict.get('요청상세', row_dict.get('detail', ''))
                    resolution = row_dict.get('조치내역', row_dict.get('resolution', ''))
                    created_at = str(row_dict.get('created_at', 'N/A'))
                    system_type = row_dict.get('시스템', row_dict.get('system', ''))

                    # 포맷팅
                    result_text += f"{idx}. [{summary}]\n"
                    result_text += f"   날짜: {created_at}\n"

                    if system_type:
                        result_text += f"   시스템: {system_type}\n"

                    if detail:
                        # 상세 내용이 너무 길면 축약
                        if len(detail) > 100:
                            detail = detail[:100] + "..."
                        result_text += f"   증상: {detail}\n"

                    if resolution:
                        # 조치내역이 너무 길면 축약
                        if len(resolution) > 200:
                            resolution = resolution[:200] + "..."
                        result_text += f"   조치: {resolution}\n"

                    result_text += "\n"
            else:
                # 집계/통계 쿼리 결과 포맷팅 (테이블 형식)
                result_text = "\n".join(validation_steps) + f"\n\nIT VOC 쿼리 결과 ({len(rows)}건)\n\n"

                # 컬럼명 추출
                columns = list(first_row.keys())
                result_text += "| " + " | ".join(str(col) for col in columns) + " |\n"
                result_text += "|" + "|".join("---" for _ in columns) + "|\n"

                # 데이터 행
                for row in rows:
                    row_dict = dict(row)
                    values = [str(row_dict.get(col, '')) for col in columns]
                    result_text += "| " + " | ".join(values) + " |\n"

            return result_text.strip()

    except asyncpg.PostgresError as e:
        print(f"[IT VOC MCP] DB 오류: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   DB 오류: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n데이터베이스 오류: {str(e)}"
    except Exception as e:
        print(f"[IT VOC MCP] 실행 실패: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   실행 실패: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n쿼리 실행 실패: {str(e)}"


@mcp.tool()
async def register_works_voc(
    title: str,
    details: str,
    system_name: str = "",
    attachments: Optional[list[str]] = None,
    employee_number: str = "auto",
) -> str:
    """WORKS 서비스데스크(앱릿 934)에 IT 지원 요청(VOC)을 등록합니다.
    사용자가 "등록해줘"라고 요청하면 이 도구를 호출하세요.
    요청자 정보(사번, 이름, 부서)와 담당 부서원은 자동으로 처리됩니다.

    title: 요청 요약 (1줄, 간결하게)
    details: 요청 상세 내용
    system_name: 관련 시스템명 (SAP, LFON, DLP, DRM, VPN, 네트워크, HW, SW, HR, EHS, MES, NAS, AD 등. 판단 불가 시 빈 문자열)
    attachments: 첨부할 파일명 리스트 (현재 세션에 업로드된 파일명만. 경로 금지, 파일명만). 없으면 생략.
    employee_number: 시스템이 자동 주입. 호출 시 생략하거나 아무 값이나 넣으세요.
    """
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))

    print(f"\n[IT VOC MCP] WORKS VOC 등록 요청: employee={employee_number}, system={system_name}, title={title[:50]}, attachments={attachments or []}", file=sys.stderr)

    # 1. 요청자 정보 조회
    requester = await _get_user_full_info(employee_number)
    if not requester:
        return f"오류: 사번 '{employee_number}'에 해당하는 사용자를 찾을 수 없습니다."

    # 2. 시스템 코드 및 담당 부서 결정
    system_code = SYSTEM_NAME_TO_CODE.get(system_name, "7")  # 기본: 기타
    dept_names_for_assign = SYSTEM_CODE_TO_DEPTS.get(system_code, ("IT운영팀",))
    print(f"[IT VOC MCP] 시스템: {system_name} → 코드={system_code}, 담당부서={'/'.join(dept_names_for_assign)}", file=sys.stderr)

    # 3. 담당 부서원 조회
    assignee_members = await _get_dept_members(dept_names_for_assign)
    assignee_objs = [_build_assignee_obj(m) for m in assignee_members]
    print(f"[IT VOC MCP] 담당자 {len(assignee_objs)}명: {[a['name'] for a in assignee_objs]}", file=sys.stderr)

    # 4. 요청자/부서 객체 구성
    requester_obj = {"id": requester["user_id"], "name": requester["name"]}
    dept_obj = {"id": requester["dept_id"], "name": requester["dept_name"], "companyId": 10}

    now_iso = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # 5. SSO API 페이로드 구성 (앱릿 934)
    values = {
        "_awrf64ysv": "0",                  # 소속법인 (0=엘앤에프)
        "_njwhedh92": [dept_obj],            # 요청자 부서
        "_06n4tz3aa": [requester_obj],       # 요청자
        "_33pws2fa7": "",                    # 연락처
        "_7m22dqqax": "1",                   # 공개여부 (1=공개)
        "_ywq5vff2f": [],                    # 긴급 (빈=일반)
        "_x2j86b6hi": title,                 # 요약
        "_7kcfuawt3": "",                    # 메뉴
        "_qwczls8ll": details,               # 요청 상세
        "_h8fx98gul": now_iso,               # 접수일
        "_8uzx0pk1u": assignee_objs,         # 담당자
        "_o9nnudfsi": system_code,           # 시스템 (코드 번호)
        "_xfyfduuem": [],                    # 외근필요여부
        "_0m979btld": None,                  # 외근 site
        "_l56bfjohs": None,                  # LFON 하위분류
        "_tw2ay456n": None,                  # NAS 하위분류
        "_snapoud85": None,                  # 기타 하위분류
        "_7gojr5dlx": None,                  # HW 하위분류
        "_iya26h7j2": None,                  # SW 하위분류
        "_yqof58gl7": None,                  # 네트워크 하위분류
        "_bfycrfjyf": None,                  # SAP 하위분류
        "_nv65dq0p6": None,                  # 보안성검토 하위분류
        "_0rqgvi5po": "-999",                # 공수 계산 (미선택)
        "_e2k5nsv8w": [0],                   # 작업내역 (0=기능문의)
        "privateFlag": False,
    }

    payload = {
        "appletId": WORKS_APPLET_ID,
        "values": values,
        # 상위 레벨 중복 필드 (LFON API 요구사항)
        "_awrf64ysv": "0",
        "_njwhedh92": [dept_obj],
        "_06n4tz3aa": [requester_obj],
        "_33pws2fa7": "",
        "_7m22dqqax": "1",
        "_ywq5vff2f": [],
        "_qwczls8ll": details,
        "_h8fx98gul": now_iso,
        "_8uzx0pk1u": assignee_objs,
        "_o9nnudfsi": system_code,
        "_xfyfduuem": [],
        "_0m979btld": None,
        "_l56bfjohs": None,
        "_tw2ay456n": None,
        "_snapoud85": None,
        "_7gojr5dlx": None,
        "_iya26h7j2": None,
        "_yqof58gl7": None,
        "_bfycrfjyf": None,
        "_nv65dq0p6": None,
        "_0rqgvi5po": "-999",
        "_e2k5nsv8w": [0],
        "_x2j86b6hi": title,
        "_7kcfuawt3": "",
    }

    # 6. SSO 로그인 → API 호출
    cookies = await _sso_login()
    if not cookies:
        # SSO 실패 시 OpenAPI 폴백 (담당자 없이)
        print("[IT VOC MCP] SSO 실패 → OpenAPI 폴백", file=sys.stderr)
        if attachments:
            print("[IT VOC MCP] OpenAPI 폴백은 첨부파일 미지원 — 첨부 생략됨", file=sys.stderr)
        return await _register_via_openapi(requester, title, details, system_name, system_code)

    # 6-1. 첨부파일 선업로드 (/api/file) → metadata 수집
    attachment_metas = []
    attachment_warnings = []
    if attachments:
        # user_uploads 경로 스코프는 employee_number 기준
        for fname in attachments:
            path = _resolve_attachment_path(fname, employee_number)
            if not path:
                attachment_warnings.append(f"'{fname}' (파일을 찾을 수 없음)")
                continue
            meta = await _upload_file_to_works(cookies, path)
            if meta:
                attachment_metas.append(meta)
            else:
                attachment_warnings.append(f"'{fname}' (업로드 실패)")

        if attachment_metas:
            values[WORKS_ATTACHMENT_FIELD] = attachment_metas
            payload[WORKS_ATTACHMENT_FIELD] = attachment_metas
            print(f"[IT VOC MCP] 첨부 {len(attachment_metas)}개 embed 완료", file=sys.stderr)

    try:
        async with httpx.AsyncClient(
            base_url=LFON_BASE_URL, timeout=30, verify=False, follow_redirects=True,
            cookies=cookies,
        ) as client:
            resp = await client.post(
                f"/api/works/applets/{WORKS_APPLET_ID}/docs",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

            # 세션 만료 시 재로그인 후 재시도
            if resp.status_code in (401, 403):
                global _sso_cookies
                _sso_cookies = None
                cookies = await _sso_login()
                if cookies:
                    resp = await client.post(
                        f"/api/works/applets/{WORKS_APPLET_ID}/docs",
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                    )

            if resp.status_code == 200:
                data = resp.json()
                assignee_names = ", ".join(a["name"] for a in assignee_objs) if assignee_objs else "미지정"
                print(f"[IT VOC MCP] VOC 등록 성공 (SSO): {requester['name']} - {title[:30]}, 담당: {assignee_names}", file=sys.stderr)
                print(f"[IT VOC MCP] 응답 데이터: {str(data)[:500]}", file=sys.stderr)

                # 7. 상태 전환: 접수 → 담당자지정
                # 응답에서 doc_id 추출 (다양한 키 패턴 시도)
                doc_id = (
                    data.get("id") or data.get("docId") or data.get("doc_id")
                    or data.get("documentId") or data.get("document_id")
                )
                # 중첩 구조 시도 (data.result.id 등)
                if not doc_id and isinstance(data.get("result"), dict):
                    doc_id = data["result"].get("id") or data["result"].get("docId")
                if not doc_id and isinstance(data.get("data"), dict):
                    doc_id = data["data"].get("id") or data["data"].get("docId")

                # DEBUG: 응답 키를 도구 결과에 포함 (임시)
                debug_keys = f"[DEBUG] response keys={list(data.keys())[:10]}, data={str(data)[:300]}"

                if doc_id:
                    print(f"[IT VOC MCP] 상태 전환 시작: doc_id={doc_id}", file=sys.stderr)
                    # 접수
                    await _transition_status(doc_id, ACTION_ACCEPT, cookies)
                    # 담당자지정
                    await _transition_status(doc_id, ACTION_ASSIGN, cookies)
                else:
                    print(f"[IT VOC MCP] doc_id를 응답에서 찾을 수 없음 (상태 전환 생략)", file=sys.stderr)

                attach_line = ""
                if attachment_metas:
                    names = ", ".join(m["name"] for m in attachment_metas)
                    attach_line = f"- 첨부파일: {names} ({len(attachment_metas)}개)\n"
                if attachment_warnings:
                    attach_line += f"- 첨부 제외: {', '.join(attachment_warnings)}\n"

                return (
                    f"WORKS 서비스데스크에 등록이 완료되었습니다.\n"
                    f"- 요청자: {requester['name']} ({requester['dept_name']})\n"
                    f"- 제목: {title}\n"
                    f"- 시스템: {system_name or '기타'}\n"
                    f"- 담당부서: {'/'.join(dept_names_for_assign)} ({len(assignee_objs)}명 배정)\n"
                    f"{attach_line}"
                    f"LFON WORKS에서 진행 상황을 확인하실 수 있습니다.\n"
                    f"\n{debug_keys}"
                )
            else:
                print(f"[IT VOC MCP] VOC 등록 실패 (SSO): status={resp.status_code}, body={resp.text[:300]}", file=sys.stderr)
                # SSO 실패 시 OpenAPI 폴백
                return await _register_via_openapi(requester, title, details, system_name, system_code)

    except Exception as e:
        print(f"[IT VOC MCP] VOC 등록 오류 (SSO): {e}", file=sys.stderr)
        return await _register_via_openapi(requester, title, details, system_name, system_code)


async def _register_via_openapi(
    requester: dict, title: str, details: str, system_name: str, system_code: str,
) -> str:
    """OpenAPI 폴백 (담당자 지정 불가, VOC 생성만)"""
    params = {
        "token": LFON_WORKS_TOKEN,
        "username": requester["name"],
        "dept": requester["dept_name"],
        "_affiliation": "엘앤에프",
        "_x2j86b6hi": title,
        "_qwczls8ll": details,
        "_7m22dqqax": "공개",
        "_e2k5nsv8w": "기능문의",
    }
    if system_name:
        params["_o9nnudfsi"] = system_name

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.post(
                f"{LFON_BASE_URL}/openapi/works/applets/doc",
                params=params,
            )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("resultCode") == 0 or not data.get("resultCode"):
                dept_names_for_assign = SYSTEM_CODE_TO_DEPTS.get(system_code, ("IT운영팀",))
                print(f"[IT VOC MCP] VOC 등록 성공 (OpenAPI 폴백)", file=sys.stderr)
                return (
                    f"WORKS 서비스데스크에 등록이 완료되었습니다.\n"
                    f"- 요청자: {requester['name']} ({requester['dept_name']})\n"
                    f"- 제목: {title}\n"
                    f"- 시스템: {system_name or '기타'}\n"
                    f"- 담당부서: {'/'.join(dept_names_for_assign)} (자동 배정은 실패하여 수동 배정이 필요합니다)\n"
                    f"LFON WORKS에서 진행 상황을 확인하실 수 있습니다."
                )
            else:
                return f"WORKS 등록 실패: {data.get('resultMessage', '알 수 없는 오류')}"
        else:
            return f"WORKS 등록 실패: HTTP {resp.status_code}"
    except Exception as e:
        return f"WORKS 등록 중 오류 발생: {str(e)}"


if __name__ == "__main__":
    print("IT VOC Knowledge Base MCP Server v1 시작...", file=sys.stderr)
    print("이 서버는 IT/보안 지원요청 해결 사례를 검색하고 WORKS VOC를 등록합니다.", file=sys.stderr)
    print("v_works_app_934_data 뷰를 통해 과거 VOC를 조회합니다.", file=sys.stderr)
    print("", file=sys.stderr)

    mcp.run(transport="stdio")

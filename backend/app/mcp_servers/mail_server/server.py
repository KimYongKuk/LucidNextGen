"""메일 조회 MCP 서버 v2

사용자의 사내 메일함을 실시간 조회합니다.
- PostgreSQL(TIMS DB)에서 사번 → message_store 경로 매핑
- 그룹웨어 JSP 엔드포인트(lucid_mail.jsp) HTTP 호출
- 6가지 액션: inbox, sent, search, folders, unread, detail
- v2: 메일 전체 본문 조회(detail), 메일 요약/답장 초안 지원
"""
import sys
import os
import json
import urllib3
from typing import Optional, Dict

import asyncpg
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastmcp import FastMCP

# SSL 경고 억제 (내부 서버)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

mcp = FastMCP("Mail Query Server v2")

# 본문 텍스트 길이 제한 (LLM 컨텍스트 효율)
MAIL_BODY_MAX_LENGTH = 8000

# PostgreSQL 연결 정보 (TIMS DB - org_chart MCP와 동일)
DATABASE_URL = os.environ.get(
    "TIMS_DATABASE_URL",
    "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"
)

# 메일 API 설정
MAIL_API_URL = os.environ.get("MAIL_API_URL", "https://lfon.landf.co.kr/slo/lucid_mail.jsp")
MAIL_API_KEY = os.environ.get("MAIL_API_KEY", "")

# 전역 연결 풀
_db_pool: Optional[asyncpg.Pool] = None

# message_store 캐시 (사번 → 경로, 프로세스 수명 동안 유지)
_message_store_cache: Dict[str, str] = {}


async def get_db_pool() -> asyncpg.Pool:
    """PostgreSQL 연결 풀 가져오기 (싱글톤)"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=15
        )
        print("Mail DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


async def _get_message_store(employee_number: str) -> str:
    """
    사번으로 message_store 경로 조회 (캐시 적용)

    v_mail_user_mapping 뷰를 통해 사번 → 메일 저장 경로 조회
    (원본 테이블 직접 접근 없이 VIEW만 사용)
    """
    if employee_number in _message_store_cache:
        return _message_store_cache[employee_number]

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT message_store
            FROM v_mail_user_mapping
            WHERE employee_number = $1
            """,
            employee_number
        )

    if not row or not row["message_store"]:
        raise ValueError(f"메일 계정을 찾을 수 없습니다 (사번: {employee_number})")

    message_store = row["message_store"]
    _message_store_cache[employee_number] = message_store
    print(f"[Mail MCP] {employee_number} → {message_store}", file=sys.stderr)
    return message_store


async def _call_mail_api(message_store: str, action: str, **kwargs) -> dict:
    """mail_query.jsp HTTP 호출"""
    params = {
        "api_key": MAIL_API_KEY,
        "action": action,
        "message_store": message_store,
    }
    if kwargs.get("limit") is not None:
        params["limit"] = str(kwargs["limit"])
    if kwargs.get("keyword") is not None:
        params["keyword"] = kwargs["keyword"]
    if kwargs.get("uid_no") is not None:
        params["uid_no"] = str(kwargs["uid_no"])
    if kwargs.get("folder_no") is not None:
        params["folder_no"] = str(kwargs["folder_no"])

    raw_text = ""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            verify=False,
        ) as client:
            response = await client.get(MAIL_API_URL, params=params)
            response.raise_for_status()
            raw_text = response.text
            # 응답 텍스트에서 JSON 추출 (JSP가 앞뒤 공백/개행을 포함할 수 있음)
            stripped = raw_text.strip()
            if not stripped:
                raise RuntimeError(f"메일 서버 빈 응답 (action={action})")
            return json.loads(stripped)
    except httpx.TimeoutException:
        raise RuntimeError(f"메일 서버 응답 시간 초과 (action={action})")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"메일 서버 오류: HTTP {e.response.status_code}")
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"JSON파싱실패 (action={action}) | "
            f"len={len(raw_text)} | err_pos={e.pos} | err={e.msg} | "
            f"tail={repr(raw_text[-100:])} | head={repr(raw_text[:80])}"
        )


def _format_mail_list(result: dict, label: str) -> str:
    """메일 목록 결과를 LLM 친화적 텍스트로 포맷팅"""
    data = result.get("data", [])

    if not data:
        return f"{label}: 메일이 없습니다."

    lines = [f"{label} ({len(data)}건)\n"]
    for i, mail in enumerate(data, 1):
        uid = mail.get("uid", "")
        folder_no = mail.get("folder_no", "")
        subject = mail.get("subject", "(제목 없음)")
        sender = mail.get("from", "")
        recipient = mail.get("to", "")
        date = mail.get("date", "")
        preview = mail.get("preview", "")
        flag = mail.get("flag", 0)
        read_status = "읽음" if (flag & 2) else "안읽음"

        lines.append(f"{i}. [{read_status}] {subject}")
        if uid and folder_no:
            lines.append(f"   [메일ID: uid={uid}, folder={folder_no}]")
        if sender:
            lines.append(f"   발신: {sender}")
        if recipient:
            lines.append(f"   수신: {recipient}")
        if date:
            lines.append(f"   날짜: {date}")
        if preview:
            preview_short = preview[:100] + "..." if len(preview) > 100 else preview
            lines.append(f"   미리보기: {preview_short}")
        lines.append("")

    return "\n".join(lines)


def _format_folders(result: dict) -> str:
    """메일함 목록 포맷팅"""
    data = result.get("data", [])

    if not data:
        return "메일함 정보를 가져올 수 없습니다."

    lines = [f"메일함 목록 ({len(data)}개)\n"]
    for folder in data:
        name = folder.get("folder_name", "Unknown")
        count = folder.get("msg_count", 0)
        unseen = folder.get("unseen_count", 0)
        lines.append(f"- {name}: {count}건 (안읽음 {unseen}건)")

    return "\n".join(lines)


def _format_mail_detail(result: dict) -> str:
    """메일 상세 결과를 LLM 친화적 텍스트로 포맷팅"""
    data = result.get("data", {})

    if not data:
        return "메일 상세 정보를 가져올 수 없습니다."

    lines = ["=== 메일 상세 내용 ===\n"]

    subject = data.get("subject", "(제목 없음)")
    sender = data.get("from", "")
    recipient = data.get("to", "")
    cc = data.get("cc", "")
    date = data.get("date", "")
    body = data.get("body", "")
    body_length = data.get("body_length", len(body))
    body_truncated = data.get("body_truncated", False)

    lines.append(f"제목: {subject}")
    if sender:
        lines.append(f"발신자: {sender}")
    if recipient:
        lines.append(f"수신자: {recipient}")
    if cc:
        lines.append(f"참조(CC): {cc}")
    if date:
        lines.append(f"날짜: {date}")
    lines.append("")
    lines.append("--- 본문 ---")

    if body:
        if len(body) > MAIL_BODY_MAX_LENGTH:
            body = body[:MAIL_BODY_MAX_LENGTH]
            lines.append(body)
            lines.append(f"\n[본문이 {MAIL_BODY_MAX_LENGTH:,}자로 잘렸습니다. 원문 길이: {body_length:,}자]")
        else:
            lines.append(body)
    else:
        lines.append("(본문 없음)")

    if body_truncated:
        lines.append("[JSP 서버에서 본문이 50,000자 초과로 잘렸습니다]")

    lines.append("\n=== 상세 끝 ===")
    return "\n".join(lines)


async def _query_mail(employee_number: str, action: str, label: str, **kwargs) -> str:
    """공통 메일 조회 로직"""
    import time as _time
    _start = _time.time()
    kw_summary = " ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    _log_lines = [f"[MAIL_DEBUG] action={action} employee={employee_number} {kw_summary}".rstrip()]

    try:
        # Step 1: message_store 조회
        db_start = _time.time()
        message_store = await _get_message_store(employee_number)
        db_ms = int((_time.time() - db_start) * 1000)
        cached = employee_number in _message_store_cache
        _log_lines.append(
            f"[MAIL_DEBUG] SQL: SELECT message_store FROM v_mail_user_mapping "
            f"WHERE employee_number='{employee_number}' → '{message_store}' "
            f"({'cache' if cached else 'DB'}, {db_ms}ms)"
        )

        # Step 2: JSP HTTP 호출
        api_start = _time.time()
        kw_info = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        _log_lines.append(f"[MAIL_DEBUG] HTTP: {MAIL_API_URL}?action={action}&message_store={message_store}&{kw_info}")

        result = await _call_mail_api(message_store, action, **kwargs)
        api_ms = int((_time.time() - api_start) * 1000)
        data_count = len(result.get("data", []))
        _log_lines.append(f"[MAIL_DEBUG] HTTP 응답: {data_count}건, {api_ms}ms")

        # Step 3: 포맷팅
        if action == "folders":
            formatted = _format_folders(result)
        else:
            formatted = _format_mail_list(result, label)

        total_ms = int((_time.time() - _start) * 1000)
        _log_lines.append(f"[MAIL_DEBUG] 완료: {total_ms}ms total")

        # 디버그 로그를 결과 맨 앞에 주입 (LLM에게는 무시됨, 서버 로그에 찍힘)
        debug_header = "\n".join(_log_lines) + "\n---\n"
        return debug_header + formatted

    except ValueError as e:
        _log_lines.append(f"[MAIL_DEBUG] ValueError: {e}")
        return "\n".join(_log_lines) + f"\n오류: {str(e)}"
    except RuntimeError as e:
        _log_lines.append(f"[MAIL_DEBUG] RuntimeError: {e}")
        return "\n".join(_log_lines) + f"\n메일 조회 실패: {str(e)}"
    except Exception as e:
        _log_lines.append(f"[MAIL_DEBUG] Exception: {type(e).__name__}: {e}")
        return "\n".join(_log_lines) + f"\n메일 조회 중 오류가 발생했습니다: {str(e)}"


@mcp.tool()
async def get_inbox_mail(employee_number: str, limit: int = 20) -> str:
    """받은편지함 최근 메일을 조회합니다.
    employee_number: 사용자 사번 (예: PA2601004)
    limit: 조회할 메일 수 (기본 20, 최대 100)"""
    limit = min(max(limit, 1), 100)
    return await _query_mail(employee_number, "inbox", "받은편지함", limit=limit)


@mcp.tool()
async def get_sent_mail(employee_number: str, limit: int = 20) -> str:
    """보낸편지함 최근 메일을 조회합니다.
    employee_number: 사용자 사번 (예: PA2601004)
    limit: 조회할 메일 수 (기본 20, 최대 100)"""
    limit = min(max(limit, 1), 100)
    return await _query_mail(employee_number, "sent", "보낸편지함", limit=limit)


@mcp.tool()
async def search_mail(employee_number: str, keyword: str, limit: int = 20) -> str:
    """키워드로 메일을 검색합니다 (제목, 발신자, 미리보기 본문 대상).
    employee_number: 사용자 사번 (예: PA2601004)
    keyword: 검색 키워드
    limit: 최대 결과 수 (기본 20, 최대 100)"""
    limit = min(max(limit, 1), 100)
    return await _query_mail(employee_number, "search", f"메일 검색 '{keyword}'", limit=limit, keyword=keyword)


@mcp.tool()
async def get_mail_folders(employee_number: str) -> str:
    """메일함 목록과 각 메일함의 메일 수를 조회합니다.
    employee_number: 사용자 사번 (예: PA2601004)"""
    return await _query_mail(employee_number, "folders", "메일함 목록")


@mcp.tool()
async def get_unread_mail(employee_number: str, limit: int = 20) -> str:
    """안 읽은 메일을 조회합니다.
    employee_number: 사용자 사번 (예: PA2601004)
    limit: 조회할 메일 수 (기본 20, 최대 100)"""
    limit = min(max(limit, 1), 100)
    return await _query_mail(employee_number, "unread", "안 읽은 메일", limit=limit)


@mcp.tool()
async def get_mail_detail(employee_number: str, uid_no: int, folder_no: int) -> str:
    """특정 메일의 전체 본문을 조회합니다. 메일 요약, 답장 초안 작성에 사용합니다.
    메일 목록 조회 결과의 [메일ID: uid=N, folder=M] 정보를 사용하세요.
    employee_number: 사용자 사번 (예: PA2601004)
    uid_no: 메일 고유 번호 (메일 목록의 uid 값)
    folder_no: 메일함 번호 (메일 목록의 folder 값)"""
    import time as _time
    _start = _time.time()
    _log_lines = [f"[MAIL_DEBUG] action=detail employee={employee_number} uid={uid_no} folder={folder_no}"]

    try:
        message_store = await _get_message_store(employee_number)
        _log_lines.append(f"[MAIL_DEBUG] message_store='{message_store}'")

        api_start = _time.time()
        result = await _call_mail_api(
            message_store, "detail",
            uid_no=uid_no, folder_no=folder_no
        )
        api_ms = int((_time.time() - api_start) * 1000)
        _log_lines.append(f"[MAIL_DEBUG] HTTP detail 응답: {api_ms}ms")

        formatted = _format_mail_detail(result)

        total_ms = int((_time.time() - _start) * 1000)
        _log_lines.append(f"[MAIL_DEBUG] 완료: {total_ms}ms total")

        debug_header = "\n".join(_log_lines) + "\n---\n"
        return debug_header + formatted

    except ValueError as e:
        _log_lines.append(f"[MAIL_DEBUG] ValueError: {e}")
        return "\n".join(_log_lines) + f"\n오류: {str(e)}"
    except RuntimeError as e:
        _log_lines.append(f"[MAIL_DEBUG] RuntimeError: {e}")
        return "\n".join(_log_lines) + f"\n메일 상세 조회 실패: {str(e)}"
    except Exception as e:
        _log_lines.append(f"[MAIL_DEBUG] Exception: {type(e).__name__}: {e}")
        return "\n".join(_log_lines) + f"\n메일 상세 조회 중 오류: {str(e)}"


if __name__ == "__main__":
    print("Mail Query MCP Server v2 시작...", file=sys.stderr)
    print(f"API URL: {MAIL_API_URL}", file=sys.stderr)
    print(f"API Key configured: {bool(MAIL_API_KEY)}", file=sys.stderr)
    print(f"DB URL: {DATABASE_URL[:30]}...", file=sys.stderr)

    mcp.run(transport="stdio")

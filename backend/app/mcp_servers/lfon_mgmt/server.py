"""LFON 그룹웨어 계정 관리 MCP 서버

사용자 본인의 그룹웨어 계정에 대해 destructive 관리 작업을 수행:
- OTP 초기화
- 패스워드 초기화
- 메일 용량 증설

**보안 설계 원칙**
- 2-step 패턴: 사용자가 실수로 실행 못 하도록 confirm → execute 분리
- 본인만 조작: 사번(employee_number)을 Worker의 prepare_tools()에서 강제 주입
- 사번 → user_id 변환은 MCP 서버 내부에서 수행 (LLM이 임의 user_id 주입 불가)
- LFON 서버가 원본 이력을 감사 테이블에 기록 (우리 쪽 별도 감사 테이블 없음)
- 인증: LFON_MGMT_API_KEY 환경변수의 토큰을 Authorization 헤더로 전달

**토큰 라이프사이클**
- confirm_* 호출 시 UUID 토큰 발급, 메모리에 {token: (empno, action, issued_at)} 저장
- execute_*(token=...) 호출 시:
  1. 메모리에서 검증 (토큰 존재, 60초 내, 같은 empno, 같은 action)
  2. 성공 시 LFON API 실제 호출
  3. 토큰 1회성 — 성공/실패 모두 제거

**환경변수**
- LFON_MGMT_BASE_URL: 기본 https://api.landf.co.kr:44818
- LFON_MGMT_API_KEY: Authorization 헤더 값 (필수)
- LFON_MGMT_ENABLED: on/off (기본 true)
"""
import sys
import os
import json
import time
import logging
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from dotenv import load_dotenv
load_dotenv()

import httpx
import asyncpg
from fastmcp import FastMCP

from app.utils.crypto import encrypt_empno, decrypt_empno

logger = logging.getLogger(__name__)
mcp = FastMCP("LFON Account Management Server v1")

# ─── Config ───
LFON_MGMT_BASE_URL = os.getenv("LFON_MGMT_BASE_URL", "https://api.landf.co.kr:44818")
LFON_MGMT_API_KEY = os.getenv("LFON_MGMT_API_KEY", "")
LFON_MGMT_ENABLED = os.getenv("LFON_MGMT_ENABLED", "true").lower() == "true"

TIMS_DATABASE_URL = os.getenv(
    "TIMS_DATABASE_URL",
    "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims",
)

# confirm 토큰 유효 시간 (초) — 5분으로 설정 (LLM이 재질문/재계산 등으로 지연될 수 있음)
CONFIRM_TOKEN_TTL_SECONDS = 300

# confirm 토큰 암호화 키 (WIDGET_SHARED_KEY 재사용 — stateless 토큰용, 서명 목적)
# 중요: MCP 서버가 tool call마다 subprocess 재생성되는 구조라
#       메모리 dict가 유지 안 됨 → stateless 토큰 (self-contained) 필수
_CONFIRM_KEY = os.getenv("WIDGET_SHARED_KEY", "landf01234567890")

# 사번 → user_id 캐시 (프로세스 수명)
_sabun_to_user_id_cache: dict[str, int] = {}

# ─── Endpoints ───
_ENDPOINT_MAP = {
    "reset_otp":           ("/secure/lfon/management/OTP",      "OTP"),
    "reset_password":      ("/secure/lfon/management/password", "password"),
    "increase_mail_quota": ("/secure/lfon/management/userInfo", "mail"),
}

# 액션별 사용자 친화 설명 (confirm 메시지 생성용)
_ACTION_DESCRIPTION = {
    "reset_otp":           ("OTP 초기화",
                             "OTP 장치를 초기화합니다. 초기화 후 OTP 재등록이 필요합니다."),
    "reset_password":      ("그룹웨어 비밀번호 초기화",
                             "그룹웨어 로그인 비밀번호를 초기화합니다. 초기화 후 첫 로그인 시 새 비밀번호 설정이 필요합니다."),
    "increase_mail_quota": ("메일 용량 증설",
                             "메일함 용량을 증설합니다. (이미 증설되었거나 최대치 도달 시 안내 메시지 반환)"),
}


# ─── Helpers ───

async def _lookup_user_id_by_sabun(employee_number: str) -> Optional[int]:
    """사번 → v_user_info_mapping.user_id 조회 (그룹웨어 고유 ID).

    프로세스 수명 캐싱 (매핑이 거의 바뀌지 않음).
    """
    if not employee_number:
        return None

    cached = _sabun_to_user_id_cache.get(employee_number)
    if cached is not None:
        return cached

    try:
        conn = await asyncpg.connect(TIMS_DATABASE_URL, timeout=5)
        try:
            row = await conn.fetchrow(
                "SELECT user_id FROM v_user_info_mapping WHERE employee_number = $1 LIMIT 1",
                employee_number,
            )
            if row:
                uid = int(row["user_id"])
                _sabun_to_user_id_cache[employee_number] = uid
                return uid
            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"[LFON_MGMT] user_id lookup failed for {employee_number}: {e}")
        return None


def _issue_confirm_token(empno: str, action: str, user_id: int) -> str:
    """confirm 토큰 발급 — stateless AES 암호화 (메모리 상태 불필요).

    Payload JSON: {"e": empno, "a": action, "u": user_id, "t": issued_at}
    """
    payload = {
        "e": empno,
        "a": action,
        "u": user_id,
        "t": int(time.time()),
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    # encrypt_empno는 문자열을 AES-ECB + PKCS7 + base64 + urlencode
    return encrypt_empno(payload_str, _CONFIRM_KEY)


def _consume_confirm_token(token: str, expected_empno: str, expected_action: str) -> Optional[dict]:
    """토큰 검증 — stateless 복호화 방식.

    반환: 유효하면 {empno, action, user_id, issued_at}, 아니면 None.
    주의: 1회성 보장 안 됨 (stateless 구조) → 짧은 TTL + LLM이 재전송할 이유 없음으로 완화.
    """
    # 복호화
    try:
        payload_str = decrypt_empno(token, _CONFIRM_KEY)
        payload = json.loads(payload_str)
    except Exception as e:
        logger.warning(f"[LFON_MGMT] Token decrypt failed: {e}")
        return None

    info = {
        "empno": payload.get("e"),
        "action": payload.get("a"),
        "user_id": payload.get("u"),
        "issued_at": payload.get("t", 0),
    }

    # 사번 일치 검증 (다른 사용자가 탈취한 토큰으로 실행 시도 차단)
    if info["empno"] != expected_empno:
        logger.warning(
            f"[LFON_MGMT] Token empno mismatch: token_empno={info['empno']}, actual={expected_empno}"
        )
        return None

    # 액션 일치 검증 (비밀번호 confirm 후 OTP execute 같은 트릭 차단)
    if info["action"] != expected_action:
        logger.warning(
            f"[LFON_MGMT] Token action mismatch: token_action={info['action']}, actual={expected_action}"
        )
        return None

    # 만료 검증 (issued_at이 초 단위)
    now = int(time.time())
    if now - info["issued_at"] > CONFIRM_TOKEN_TTL_SECONDS:
        logger.info(
            f"[LFON_MGMT] Token expired for {expected_empno}/{expected_action}: "
            f"age={now - info['issued_at']}s, ttl={CONFIRM_TOKEN_TTL_SECONDS}s"
        )
        return None

    return info


async def _call_lfon_api(action: str, user_id: int) -> dict:
    """실제 LFON API PUT 호출.

    Returns:
        {
            "success": bool,
            "message": str,      # 사용자 친화 메시지
            "code": str | None,  # 'full', 'end' 등 (실패 케이스)
            "raw_response": str, # 원본 응답 (디버깅용)
        }
    """
    endpoint, flag = _ENDPOINT_MAP[action]
    url = LFON_MGMT_BASE_URL.rstrip("/") + endpoint
    body = {"ids": [user_id], "updateDataFlag": flag}
    headers = {
        "Content-Type": "application/json",
        "Authorization": LFON_MGMT_API_KEY,
    }

    logger.info(f"[LFON_MGMT] Calling {action} for user_id={user_id}")

    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            resp = await client.put(url, json=body, headers=headers)
    except httpx.RequestError as e:
        logger.error(f"[LFON_MGMT] Network error: {e}")
        return {
            "success": False,
            "message": f"LFON API 호출 실패: {e}",
            "code": "network_error",
            "raw_response": "",
        }

    raw = resp.text.strip()
    logger.info(f"[LFON_MGMT] Response status={resp.status_code} body={raw[:200]}")

    # 응답 파싱 — 두 가지 케이스 처리
    # (1) 평문 "success" / "fail" (OTP, password, 메일 증설 성공)
    # (2) JSON 객체 (메일 증설 실패: full, end)
    if raw == "success":
        return {
            "success": True,
            "message": "정상 처리되었습니다.",
            "code": None,
            "raw_response": raw,
        }
    if raw == "fail":
        return {
            "success": False,
            "message": "처리에 실패했습니다. 관리자에게 문의해주세요.",
            "code": "fail",
            "raw_response": raw,
        }

    # JSON 응답 시도 — 두 가지 구조 모두 지원
    # (1) {"result": "success"} / {"result": "fail"} — 문자열 result (증설 완료 등)
    # (2) {"result": {"success": bool, "message": str, "code": str}} — 객체 result (full/end 등)
    try:
        data = resp.json()
        result = data.get("result", {})

        # 문자열 result 케이스
        if isinstance(result, str):
            is_success = result.strip().lower() == "success"
            return {
                "success": is_success,
                "message": "정상 처리되었습니다." if is_success else f"처리에 실패했습니다 ({result})",
                "code": None if is_success else "fail",
                "raw_response": raw,
            }

        # 객체 result 케이스
        if isinstance(result, dict):
            return {
                "success": bool(result.get("success", False)),
                "message": result.get("message", "알 수 없는 응답"),
                "code": result.get("code"),
                "raw_response": raw,
            }

        # 예상 외 타입 (list, None 등)
        return {
            "success": False,
            "message": f"알 수 없는 응답 구조: {raw[:200]}",
            "code": "unknown_structure",
            "raw_response": raw,
        }
    except (ValueError, json.JSONDecodeError):
        return {
            "success": False,
            "message": f"알 수 없는 응답 형식: {raw[:100]}",
            "code": "unknown_response",
            "raw_response": raw,
        }
    except Exception as e:
        # catch-all: 예상 외 파싱 오류도 친화적 메시지로 (MCP 에러 대신)
        logger.error(f"[LFON_MGMT] Response parsing error: {e}, raw={raw[:200]}")
        return {
            "success": False,
            "message": f"응답 파싱 오류: {e}",
            "code": "parse_error",
            "raw_response": raw,
        }


def _check_enabled():
    if not LFON_MGMT_ENABLED:
        return "이 기능은 현재 비활성화되어 있습니다. 관리자에게 문의해주세요."
    if not LFON_MGMT_API_KEY:
        logger.error("[LFON_MGMT] LFON_MGMT_API_KEY not configured")
        return "서버 설정 오류: 인증 토큰이 설정되지 않았습니다."
    return None


# ─── MCP Tools: confirm_* (1단계) ───

async def _confirm_common(employee_number: str, action: str) -> str:
    """confirm_* 도구 공통 로직."""
    err = _check_enabled()
    if err:
        return err

    # 사번 → user_id 조회
    user_id = await _lookup_user_id_by_sabun(employee_number)
    if not user_id:
        return (
            f"사번 {employee_number}에 대한 그룹웨어 user_id를 찾을 수 없습니다. "
            "퇴사자이거나 매핑 데이터 불일치일 수 있습니다."
        )

    label, detail = _ACTION_DESCRIPTION[action]
    token = _issue_confirm_token(employee_number, action, user_id)

    return json.dumps({
        "status": "confirmation_required",
        "token": token,
        "action": action,
        "action_label": label,
        "detail": detail,
        "target_employee": employee_number,
        "expires_in_seconds": CONFIRM_TOKEN_TTL_SECONDS,
        "next_step": (
            f"사용자가 명확히 '예' 또는 '진행'이라고 답하면 "
            f"execute_{action} 도구를 token='{token}' 파라미터와 함께 호출하세요."
        ),
    }, ensure_ascii=False)


@mcp.tool()
async def confirm_reset_otp(employee_number: str) -> str:
    """OTP 초기화 확인 단계 (1/2).

    이 도구는 **사용자에게 확인만 요청**하고 실제 초기화는 수행하지 않습니다.
    사용자가 확인하면 반환된 token을 execute_reset_otp에 전달하여 실제 실행하세요.

    Args:
        employee_number: 대상 사번 (Worker의 prepare_tools에서 자동으로 본인 사번 주입됨)

    Returns:
        JSON — confirmation token + 사용자에게 보여줄 상세 설명
    """
    return await _confirm_common(employee_number, "reset_otp")


@mcp.tool()
async def confirm_reset_password(employee_number: str) -> str:
    """그룹웨어 비밀번호 초기화 확인 단계 (1/2).

    Args:
        employee_number: 대상 사번 (본인 사번 자동 주입)

    Returns:
        JSON — confirmation token + 상세
    """
    return await _confirm_common(employee_number, "reset_password")


@mcp.tool()
async def confirm_increase_mail_quota(employee_number: str) -> str:
    """메일 용량 증설 확인 단계 (1/2).

    Args:
        employee_number: 대상 사번 (본인 사번 자동 주입)

    Returns:
        JSON — confirmation token + 상세
    """
    return await _confirm_common(employee_number, "increase_mail_quota")


# ─── MCP Tools: execute_* (2단계) ───

async def _execute_common(employee_number: str, token: str, action: str) -> str:
    """execute_* 도구 공통 로직."""
    err = _check_enabled()
    if err:
        return err

    info = _consume_confirm_token(token, employee_number, action)
    if not info:
        label = _ACTION_DESCRIPTION[action][0]
        return (
            f"❌ {label} 실행이 거부되었습니다.\n\n"
            f"원인(가능한 것들):\n"
            f"- 확인 토큰이 만료되었습니다 (유효 시간: {CONFIRM_TOKEN_TTL_SECONDS}초)\n"
            f"- 토큰이 이미 사용되었습니다 (1회성)\n"
            f"- 토큰이 다른 작업/사용자로 발급되었습니다\n\n"
            f"먼저 confirm_{action} 도구로 다시 확인 요청을 해주세요."
        )

    user_id = info["user_id"]
    result = await _call_lfon_api(action, user_id)

    # 로그 (감사 목적, LFON 쪽에도 이력 기록됨)
    logger.info(
        f"[LFON_MGMT] action={action} empno={employee_number} user_id={user_id} "
        f"success={result['success']} code={result.get('code')}"
    )

    # 사용자 친화 응답 포맷팅 — 중립/긍정 톤 (LLM이 '오류'로 오해하지 않도록)
    label = _ACTION_DESCRIPTION[action][0]
    if result["success"]:
        msg = f"✅ {label}가 완료되었습니다."
        if action == "reset_password":
            msg += "\n- 첫 로그인 시 반드시 새 비밀번호를 설정해주세요."
        elif action == "reset_otp":
            msg += "\n- OTP 앱에서 재등록이 필요합니다."
        elif action == "increase_mail_quota":
            msg += "\n- 메일 용량이 증설되었습니다."
    else:
        # 메일 증설 특수 케이스 — 중립 정보 톤 (실패/오류 단어 사용 금지)
        code = result.get("code")
        if action == "increase_mail_quota" and code == "full":
            msg = (
                "ℹ️ 확인 결과: 메일 용량이 이미 증설된 상태입니다.\n\n"
                "추가 증설이 필요하시면 기안 상신을 통해 요청해주세요. "
                "현재 설정으로 충분하다면 별도 조치는 필요 없습니다."
            )
        elif action == "increase_mail_quota" and code == "end":
            msg = (
                "ℹ️ 확인 결과: 메일함이 최대 용량에 도달했습니다.\n\n"
                "오래된 메일 정리 또는 백업 진행 후 다시 시도해주세요."
            )
        else:
            msg = f"❌ {label} 실패: {result['message']}"

    return msg


@mcp.tool()
async def execute_reset_otp(employee_number: str, token: str) -> str:
    """OTP 초기화 실행 단계 (2/2).

    반드시 먼저 confirm_reset_otp로 토큰을 받고, 사용자가 확인한 뒤 호출하세요.

    Args:
        employee_number: 대상 사번 (본인 사번 자동 주입)
        token: confirm 단계에서 받은 확인 토큰
    """
    return await _execute_common(employee_number, token, "reset_otp")


@mcp.tool()
async def execute_reset_password(employee_number: str, token: str) -> str:
    """그룹웨어 비밀번호 초기화 실행 단계 (2/2).

    Args:
        employee_number: 대상 사번 (본인 사번 자동 주입)
        token: confirm 단계에서 받은 확인 토큰
    """
    return await _execute_common(employee_number, token, "reset_password")


@mcp.tool()
async def execute_increase_mail_quota(employee_number: str, token: str) -> str:
    """메일 용량 증설 실행 단계 (2/2).

    Args:
        employee_number: 대상 사번 (본인 사번 자동 주입)
        token: confirm 단계에서 받은 확인 토큰
    """
    return await _execute_common(employee_number, token, "increase_mail_quota")


if __name__ == "__main__":
    mcp.run()

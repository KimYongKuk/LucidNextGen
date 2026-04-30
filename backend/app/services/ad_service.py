"""LF AD/LDAP 인증 서비스

PWA 자체 로그인용. 사용자가 입력한 AD 계정명(sAMAccountName, 예: wg0403) +
비밀번호로 LDAP bind 시도. 성공 시 TIMS DB v_user_info_mapping에서 사번을 조회.

비밀번호는 저장하지 않음 — AD가 검증하고 우리는 결과만 받는다.

운영 진입 전 LDAPS(636) 활성화 필요. 현재 dev는 평문 LDAP(389)만 동작.
환경변수 AD_USE_LDAPS=true로 한 번에 전환 가능하게 설계.
"""
import logging
import os
import ssl
from dataclasses import dataclass
from typing import Optional

from ldap3 import ALL, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

import asyncpg

logger = logging.getLogger(__name__)


# ── 환경변수 ──

AD_HOST = os.getenv("AD_HOST", "192.168.100.98")
AD_DOMAIN = os.getenv("AD_DOMAIN", "ad.landf")
AD_USE_LDAPS = os.getenv("AD_USE_LDAPS", "false").lower() in ("true", "1", "yes")
AD_PORT = int(os.getenv("AD_PORT", "636" if AD_USE_LDAPS else "389"))
AD_BIND_TIMEOUT = int(os.getenv("AD_BIND_TIMEOUT", "5"))  # seconds

TIMS_DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "")


@dataclass
class AdUser:
    """AD bind 후 매핑된 사용자 정보"""
    empno: str
    login_id: str
    name: str


def _build_server() -> Server:
    """LDAP Server 객체 생성. LDAPS와 평문 LDAP 모두 지원."""
    if AD_USE_LDAPS:
        tls = Tls(
            validate=ssl.CERT_NONE,
            version=ssl.PROTOCOL_TLS_CLIENT,
            ciphers="ALL:@SECLEVEL=0",
        )
        return Server(
            AD_HOST, port=AD_PORT, use_ssl=True, tls=tls,
            get_info=ALL, connect_timeout=AD_BIND_TIMEOUT,
        )
    return Server(
        AD_HOST, port=AD_PORT, use_ssl=False,
        get_info=ALL, connect_timeout=AD_BIND_TIMEOUT,
    )


def verify_ad_credentials(login_id: str, password: str) -> bool:
    """LDAP bind로 자격증명 검증. 성공 시 True, 실패 시 False.

    UPN(`login_id@AD_DOMAIN`) 포맷으로 시도. dev에서는 평문 LDAP에서도 동작 확인.
    """
    if not login_id or not password:
        return False

    bind_user = f"{login_id}@{AD_DOMAIN}"
    try:
        server = _build_server()
        conn = Connection(server, user=bind_user, password=password)
        if not conn.bind():
            logger.warning(
                "[AD] Bind failed: user=%s, result=%s",
                login_id, getattr(conn, "result", None),
            )
            return False
        try:
            conn.unbind()
        except Exception:
            pass
        return True
    except LDAPException as e:
        logger.warning("[AD] LDAP error for user=%s: %s", login_id, type(e).__name__)
        return False
    except Exception as e:
        logger.error("[AD] Unexpected error for user=%s: %s: %s",
                     login_id, type(e).__name__, e)
        return False


async def resolve_user_from_login_id(login_id: str) -> Optional[AdUser]:
    """TIMS DB v_user_info_mapping에서 login_id → 사번/이름 조회.

    AD bind 성공 후 호출. users 테이블 사전 등록 불필요 — TIMS VIEW만 있으면 됨.
    """
    if not TIMS_DATABASE_URL:
        logger.error("[AD] TIMS_DATABASE_URL 미설정 — 사번 조회 불가")
        return None

    try:
        conn = await asyncpg.connect(TIMS_DATABASE_URL)
        try:
            row = await conn.fetchrow(
                """
                SELECT employee_number, login_id, name
                FROM v_user_info_mapping
                WHERE login_id = $1
                LIMIT 1
                """,
                login_id,
            )
        finally:
            await conn.close()

        if not row:
            logger.warning("[AD] login_id=%s 사번 매핑 없음 (TIMS VIEW)", login_id)
            return None

        return AdUser(
            empno=row["employee_number"],
            login_id=row["login_id"],
            name=row["name"],
        )
    except Exception as e:
        logger.error("[AD] TIMS 조회 실패 (login_id=%s): %s", login_id, e)
        return None


async def authenticate(login_id: str, password: str) -> Optional[AdUser]:
    """AD bind + 사번 조회를 한 번에 수행. 실패 시 None.

    호출자는 None 받으면 401 응답하면 된다 (실패 사유 노출 X — 보안).
    """
    login_id = (login_id or "").strip()
    if not login_id or not password:
        return None

    if not verify_ad_credentials(login_id, password):
        return None

    user = await resolve_user_from_login_id(login_id)
    if not user:
        # AD 인증은 통과했지만 TIMS에 매핑 없음 — 운영상 발생하면 안 되는 케이스
        # (퇴사자/시스템 계정 등) 보안상 동일하게 401 처리
        logger.warning(
            "[AD] AD bind OK but no TIMS mapping: login_id=%s — denied", login_id,
        )
        return None

    return user

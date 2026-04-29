"""리소스 owner 기반 인가 + 운영자 권한 헬퍼.

원칙:
- 단일 코어(_assert_owner) + 리소스별 wrapper.
- wrapper 가 호출부 가독성 + 일관된 로그 라벨을 보장.
- 거부 시 [SECURITY] 마커로 stdout 로깅 (향후 보안 이벤트 테이블 적재 지점 1곳으로 모음).
- 운영자 권한은 OPERATOR_USER_IDS 환경변수의 화이트리스트로 결정.
"""
import os
import logging
from typing import Optional, Mapping
from fastapi import HTTPException, Depends

from app.api.dependencies.auth_jwt import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Operator (운영자) 권한
# ---------------------------------------------------------------------------

_OPERATOR_USERS = [
    u.strip()
    for u in os.getenv("OPERATOR_USER_IDS", "A2304013").split(",")
    if u.strip()
]


def is_operator(empno: Optional[str]) -> bool:
    """운영자 여부 — OPERATOR_USER_IDS 환경변수 기반."""
    return bool(empno) and empno in _OPERATOR_USERS


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """관리자(=운영자)만 통과시키는 dependency.

    `Depends(get_current_admin)` 으로 admin 라우트에 적용.
    """
    if not is_operator(current_user.get("empno")):
        logger.warning(
            f"[SECURITY] admin_access_denied empno={current_user.get('empno')}"
        )
        raise HTTPException(status_code=403, detail="Admin privilege required")
    return current_user


def _assert_owner(
    resource: Optional[Mapping],
    empno: str,
    *,
    resource_type: str,
    resource_id_field: str,
    owner_field: str = "user_id",
    public_field: Optional[str] = None,
) -> None:
    if not resource:
        raise HTTPException(status_code=404, detail=f"{resource_type} not found")

    if resource.get(owner_field) == empno:
        return

    if public_field and resource.get(public_field):
        return

    logger.warning(
        f"[SECURITY] {resource_type}_access_denied "
        f"empno={empno} {resource_id_field}={resource.get(resource_id_field)} "
        f"owner={resource.get(owner_field)}"
    )
    raise HTTPException(status_code=403, detail=f"{resource_type} access denied")


def assert_workspace_owner(
    workspace: Optional[Mapping],
    empno: str,
    *,
    allow_public: bool = True,
) -> None:
    """워크스페이스 접근 권한 검증.

    - 본인 소유면 통과
    - allow_public=True 이고 is_public=1 이면 통과 (조회/사용 시)
    - 수정/삭제는 allow_public=False 로 호출하여 공용이라도 owner만 가능
    """
    _assert_owner(
        workspace, empno,
        resource_type="workspace",
        resource_id_field="uuid",
        public_field="is_public" if allow_public else None,
    )


def assert_chat_session_owner(session: Optional[Mapping], empno: str) -> None:
    """채팅 세션 접근 권한 검증 (본인만)."""
    _assert_owner(
        session, empno,
        resource_type="chat_session",
        resource_id_field="session_id",
    )

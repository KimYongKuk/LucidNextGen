"""JWT 쿠키 기반 사용자 인증 Dependency.

HttpOnly 쿠키 `auth_token`에서 JWT를 읽어 서명/만료를 검증하고,
인증된 사번(empno)과 이름을 반환한다.

FastAPI 엔드포인트에서:
    async def handler(
        request: Request,
        current_user: dict = Depends(get_current_user),
    ):
        authenticated_empno = current_user["empno"]

인증 실패 시 401 응답이 자동으로 반환된다.
"""

import os
import logging
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, status

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "landf01234567890_fastapi_secret_key_change_in_production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")


async def get_current_user(
    auth_token: Optional[str] = Cookie(None),
) -> dict:
    """HttpOnly 쿠키의 JWT를 검증하고 인증된 사용자 정보를 반환.

    Returns:
        {"empno": "A2304013", "name": "김용국"}

    Raises:
        HTTPException(401): 토큰 없음 / 만료 / 변조
    """
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 없습니다. 로그인이 필요합니다.",
        )

    try:
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다. 다시 로그인해주세요.",
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[AUTH_JWT] Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )

    empno = payload.get("empno")
    if not empno:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사번 정보가 없습니다.",
        )

    return {
        "empno": empno,
        "name": payload.get("name", ""),
    }

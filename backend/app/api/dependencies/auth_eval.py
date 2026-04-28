"""Eval 전용 인증 Dependency.

`X-Eval-Auth` 헤더의 secret이 환경변수 `EVAL_API_KEY`와 일치하면,
`X-Eval-Empno` 헤더의 사번을 그대로 인증된 사번으로 받아들인다.

JWT/위젯 인증을 우회하지만, 외부에 노출되지 않는 secret으로 보호.
운영 통계/메모리 오염 방지를 위해 source="eval"을 반환 — 호출부에서
metadata.is_eval=true로 마킹해야 한다.

활성화 조건: 환경변수 EVAL_API_KEY가 비어있지 않을 때만 동작.
"""

import os
import logging
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


async def try_eval_auth(
    x_eval_auth: Optional[str] = Header(None),
    x_eval_empno: Optional[str] = Header(None),
) -> Optional[dict]:
    """Eval 헤더가 유효하면 dict 반환, 아니면 None.

    None을 반환하면 호출부에서 다른 인증 경로(JWT/위젯)로 폴백한다.
    헤더는 있는데 secret이 틀리면 401.
    """
    if not x_eval_auth:
        return None

    expected = os.getenv("EVAL_API_KEY", "").strip()
    if not expected:
        # 서버에 키가 설정되지 않았으면 eval 경로 비활성
        logger.warning("[AUTH_EVAL] X-Eval-Auth header present but EVAL_API_KEY not set")
        return None

    if x_eval_auth != expected:
        logger.warning("[AUTH_EVAL] X-Eval-Auth secret mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eval auth secret mismatch",
        )

    if not x_eval_empno:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Eval-Empno header required when X-Eval-Auth is provided",
        )

    return {
        "empno": x_eval_empno,
        "name": f"eval_bot_{x_eval_empno}",
        "source": "eval",
    }

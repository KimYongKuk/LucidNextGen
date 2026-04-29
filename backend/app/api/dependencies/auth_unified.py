"""통합 인증 dependency.

다음 인증 방식을 한 번에 지원하기 위한 공용 헬퍼.
- X-Eval-Auth (회귀 테스트 경로 — auth_eval.try_eval_auth 검증)
- X-Widget-Auth (그룹웨어 위젯 iframe 경로 — widget_auth.get_current_user_widget)
- HttpOnly 쿠키 JWT (본 웹 UI 경로 — auth_jwt.get_current_user)

채팅 외 라우트(파일 업로드 등)에서도 위젯 호환을 위해 동일 인증 우선순위가 필요할 때 사용.
"""
from typing import Optional
from fastapi import Cookie, Header

from app.api.dependencies.auth_jwt import get_current_user
from app.api.dependencies.widget_auth import get_current_user_widget
from app.api.dependencies.auth_eval import try_eval_auth


async def get_authenticated_user(
    x_widget_auth: Optional[str] = Header(None),
    x_eval_auth: Optional[str] = Header(None),
    x_eval_empno: Optional[str] = Header(None),
    auth_token: Optional[str] = Cookie(None),
) -> dict:
    """통합 인증 — eval / widget / cookie JWT 순으로 시도.

    Returns: {"empno": ..., "name": ..., "source": "eval" | "widget" | "jwt"}
    Raises HTTPException(401) on failure.
    """
    eval_user = await try_eval_auth(x_eval_auth, x_eval_empno)
    if eval_user:
        return eval_user
    if x_widget_auth:
        return await get_current_user_widget(x_widget_auth)
    user = await get_current_user(auth_token)
    user["source"] = "jwt"
    return user

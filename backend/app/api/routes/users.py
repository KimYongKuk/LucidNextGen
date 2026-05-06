# -*- coding: utf-8 -*-
"""User Directory API — 사번 ↔ 이름/부서 lookup."""
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services import user_directory_service
from app.api.dependencies.auth_jwt import get_current_user

router = APIRouter()


class UserLookupRequest(BaseModel):
    user_ids: List[str] = Field(..., min_length=1, max_length=500)


class UserInfo(BaseModel):
    user_id: str
    name: str = ""        # 디렉토리 hit 시만 채움. 미스면 빈 문자열.
    team: str = ""
    position: str = ""
    display: str          # 디렉토리 hit 시 "부서 이름", 미스면 사번 그대로
    found: bool = False   # 디렉토리 hit 여부 (프론트가 fallback 판정용)


def _build_user_info(user_id: str) -> UserInfo:
    info = user_directory_service.get_user_info(user_id)
    if info and info.get("name"):
        name = info["name"]
        team = info.get("team") or ""
        return UserInfo(
            user_id=user_id,
            name=name,
            team=team,
            position=info.get("position") or "",
            display=f"{team} {name}".strip() if team else name,
            found=True,
        )
    # 디렉토리 미스 — name 비우고 display는 사번
    return UserInfo(
        user_id=user_id,
        name="",
        team="",
        position="",
        display=user_id,
        found=False,
    )


@router.get("/v1/users/{user_id}", response_model=UserInfo)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """단일 사번 → 이름/부서 lookup."""
    return _build_user_info(user_id)


@router.post("/v1/users/lookup")
async def lookup_users(
    request: UserLookupRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, UserInfo]:
    """배치 lookup — 사번 N개 → { user_id: UserInfo } 매핑.

    프론트가 report/카탈로그 같은 곳에서 여러 사용자 한 번에 조회용.
    디렉토리 미스 시 found=False, display=사번 (프론트는 found로 판정).
    """
    return {uid: _build_user_info(uid) for uid in request.user_ids}


@router.post("/v1/users/refresh-cache")
async def refresh_directory_cache(
    current_user: dict = Depends(get_current_user),
):
    """수동 캐시 갱신 (admin/operator만 권장 — 권한 체크 단순화 위해 일단 인증된 사용자 모두 허용)."""
    n = await user_directory_service.refresh_cache()
    return {"cached_count": n, "stale": user_directory_service.is_cache_stale()}

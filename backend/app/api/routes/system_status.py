"""시스템 상태 조회 API.

프론트엔드가 폴링하여 상단 배너 노출 여부를 결정한다.
- degraded=True: 직전 N분(기본 5분) 이내 AWS Bedrock throttling 발생
- 배너는 사용자에게 "처리 작업량 많음 → 지연 가능" 안내
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from app.core.region_fallback import get_region_fallback_manager

router = APIRouter()

_KST = timezone(timedelta(hours=9))


@router.get("/v1/system/status")
async def get_system_status() -> dict:
    """시스템 상태 조회 (인증 불필요, 공개 상태값).

    Returns:
        {
            "degraded": bool,  # 처리 지연 여부
            "message": str,    # 사용자 노출 문구 (degraded=True일 때만 의미 있음)
            "since": str|None  # throttling 시작 시각 (ISO 8601, KST)
        }
    """
    region_mgr = get_region_fallback_manager()
    degraded = region_mgr.is_degraded
    last_throttle_at = region_mgr.last_throttle_at

    since: str | None = None
    if degraded and last_throttle_at > 0:
        since = datetime.fromtimestamp(last_throttle_at, _KST).isoformat()

    return {
        "degraded": degraded,
        "message": (
            "현재 루시드AI의 처리 작업량이 많아 지연될 수 있습니다."
            if degraded else ""
        ),
        "since": since,
    }

"""통합 알림 API 라우트 (공지사항 + 메일 + 전자결재)"""
import os
import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

EMPTY_RESPONSE = {
    "notices": {"items": [], "count": 0},
    "mail": {"items": [], "count": 0},
    "approvals": {
        "pending": {"items": [], "count": 0},
        "received": {"items": [], "count": 0},
        "referenced": {"items": [], "count": 0},
    },
}


@router.get("/today")
async def get_today_notifications(user_id: str = Query(..., description="사번")):
    """통합 알림 조회 (공지사항 + 읽지 않은 메일 + 전자결재 미결)"""
    enabled = os.environ.get("NOTIFICATION_MODAL_ENABLED", "true").lower() == "true"
    if not enabled:
        return EMPTY_RESPONSE

    from app.services.notice_service import get_notification_service

    try:
        result = await get_notification_service().get_all_notifications(user_id)
        return result
    except Exception as e:
        logger.error(f"Notifications fetch failed: {e}")
        return EMPTY_RESPONSE


@router.post("/summary/stream")
async def stream_notification_summary(request: Request):
    """알림 데이터를 받아 Haiku 요약을 SSE로 스트리밍"""
    body = await request.json()

    from app.services.notice_service import NotificationService
    from app.services.bedrock_service import get_bedrock_service

    prompt = NotificationService.build_summary_prompt(
        notices=body.get("notices", {"items": [], "count": 0}),
        mail=body.get("mail", {"items": [], "count": 0}),
        approvals=body.get("approvals", {}),
    )

    async def event_generator():
        try:
            bedrock = get_bedrock_service()
            async for token in bedrock.stream_text_haiku(
                prompt, max_tokens=1000, temperature=0.2
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Summary streaming failed: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

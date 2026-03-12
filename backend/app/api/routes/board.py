"""통합 알림 API 라우트 (공지사항 + 메일 + 전자결재)"""
import os
import json
import asyncio
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


EMPTY_SECTION = {"items": [], "count": 0}
EMPTY_APPROVALS = {
    "pending": EMPTY_SECTION,
    "received": EMPTY_SECTION,
    "referenced": EMPTY_SECTION,
}


@router.get("/fast")
async def get_fast_notifications(user_id: str = Query(..., description="사번")):
    """빠른 알림 조회 (공지사항 + 전자결재) — PostgreSQL only"""
    enabled = os.environ.get("NOTIFICATION_MODAL_ENABLED", "true").lower() == "true"
    if not enabled:
        return {"notices": EMPTY_SECTION, "approvals": EMPTY_APPROVALS}

    from app.services.notice_service import get_notification_service
    svc = get_notification_service()

    async def _safe(coro, label: str):
        try:
            return await coro
        except Exception as e:
            logger.error(f"{label} 조회 실패: {e}")
            return EMPTY_SECTION

    notices, pending, received, referenced = await asyncio.gather(
        _safe(svc.get_today_notices(), "공지사항"),
        _safe(svc.get_pending_approvals(user_id), "결재 미결"),
        _safe(svc.get_received_documents(user_id), "수신문서"),
        _safe(svc.get_pending_references(user_id), "참조문서"),
    )

    return {
        "notices": notices,
        "approvals": {"pending": pending, "received": received, "referenced": referenced},
    }


@router.get("/mail")
async def get_mail_notifications(user_id: str = Query(..., description="사번")):
    """메일 알림 조회 (JSP HTTP 호출)"""
    enabled = os.environ.get("NOTIFICATION_MODAL_ENABLED", "true").lower() == "true"
    if not enabled:
        return EMPTY_SECTION

    from app.services.notice_service import get_notification_service

    try:
        return await get_notification_service().get_unread_mail(user_id)
    except Exception as e:
        logger.error(f"메일 조회 실패: {e}")
        return EMPTY_SECTION


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
                if await request.is_disconnected():
                    logger.info("Summary stream: client disconnected, stopping")
                    return
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

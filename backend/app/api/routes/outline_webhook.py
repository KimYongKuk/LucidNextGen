# -*- coding: utf-8 -*-
"""Outline Wiki Webhook 수신 엔드포인트

Outline에서 문서 변경 시 webhook으로 호출.
이벤트를 큐에 넣고 즉시 200 반환 (Outline은 빠른 응답 기대).
"""

import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks/outline", tags=["outline-webhook"])


@router.post("")
async def receive_outline_webhook(request: Request):
    """Outline webhook 수신

    Outline webhook payload 구조:
    {
      "id": "webhook-delivery-id",
      "event": "documents.update",
      "model": {
        "id": "document-uuid",
        "title": "...",
        "collectionId": "...",
        ...
      }
    }
    """
    from app.services.outline_webhook_service import get_outline_webhook_service
    service = get_outline_webhook_service()

    # 1. 서명 검증
    body = await request.body()
    signature = request.headers.get("Outline-Signature", "")
    if not service.verify_signature(body, signature):
        logger.warning("[OutlineWebhook] 서명 검증 실패")
        return Response(status_code=401, content="Invalid signature")

    # 2. 페이로드 파싱
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    event_type = payload.get("event", "")
    model = payload.get("model") or payload.get("payload", {}).get("model", {})

    if not model:
        # Outline ping/test 이벤트
        logger.info(f"[OutlineWebhook] 페이로드에 model 없음 (event={event_type}), 무시")
        return {"ok": True, "message": "no model in payload"}

    document_id = model.get("id", "")

    if not document_id or not event_type:
        return {"ok": True, "message": "missing document_id or event"}

    # 3. 지원 이벤트 확인
    from app.services.outline_webhook_service import SUPPORTED_EVENTS
    if event_type not in SUPPORTED_EVENTS:
        logger.debug(f"[OutlineWebhook] 미지원 이벤트: {event_type}")
        return {"ok": True, "message": f"unsupported event: {event_type}"}

    # 4. 큐에 추가
    enqueued = service.enqueue(document_id, event_type)

    return {
        "ok": True,
        "enqueued": enqueued,
        "event": event_type,
        "document_id": document_id,
    }


@router.get("/status")
async def webhook_status():
    """Webhook 처리 상태 조회"""
    from app.services.outline_webhook_service import get_outline_webhook_service
    service = get_outline_webhook_service()
    return service.get_status()

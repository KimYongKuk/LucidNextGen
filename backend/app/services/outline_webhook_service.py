# -*- coding: utf-8 -*-
"""Outline Wiki Webhook 처리 서비스

Outline에서 발생하는 문서 이벤트(생성/수정/삭제)를 수신하여
asyncio.Queue로 순차 처리. 단일 소비자(worker)가 1건씩 처리하므로
GPU 메모리 스파이크 방지.
"""

import os
import hmac
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Webhook 서명 검증용 시크릿
WEBHOOK_SECRET = os.environ.get("OUTLINE_WEBHOOK_SECRET", "")

# 큐 최대 크기
QUEUE_MAX_SIZE = 500

# 처리 대상 이벤트
SUPPORTED_EVENTS = {
    "documents.create",
    "documents.update",
    "documents.publish",
    "documents.delete",
    "documents.archive",
    "documents.unarchive",
}


class OutlineWebhookService:
    """Outline Webhook 이벤트를 큐 기반으로 순차 처리"""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._pending: Set[str] = set()  # 큐에 대기 중인 document_id (중복 방지)
        self._worker_task: Optional[asyncio.Task] = None
        self._processing: bool = False
        self._current_doc_id: Optional[str] = None
        self._stats = {
            "total_received": 0,
            "total_processed": 0,
            "total_errors": 0,
            "total_deduplicated": 0,
        }

    def start(self):
        """큐 소비자 태스크 시작 (lifespan에서 호출)"""
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._process_loop())
        logger.info("[OutlineWebhook] Worker 시작됨")

    def stop(self):
        """큐 소비자 태스크 중지 (lifespan에서 호출)"""
        if self._worker_task is not None:
            self._worker_task.cancel()
            self._worker_task = None
            logger.info("[OutlineWebhook] Worker 중지됨")

    def enqueue(self, document_id: str, event_type: str) -> bool:
        """이벤트를 큐에 추가

        Args:
            document_id: Outline 문서 ID
            event_type: 이벤트 유형

        Returns:
            True: 큐에 추가됨, False: 중복 또는 큐 가득 참
        """
        self._stats["total_received"] += 1

        # 중복 제거: 같은 document_id가 이미 큐에 있으면 스킵
        # (삭제 이벤트는 항상 처리 — 중복이어도 안전)
        if document_id in self._pending and event_type != "documents.delete":
            self._stats["total_deduplicated"] += 1
            logger.debug(f"[OutlineWebhook] 중복 스킵: {document_id}")
            return False

        try:
            self._queue.put_nowait((document_id, event_type, datetime.now(timezone.utc)))
            self._pending.add(document_id)
            logger.info(f"[OutlineWebhook] 큐 추가: {event_type} {document_id} "
                        f"(대기: {self._queue.qsize()})")
            return True
        except asyncio.QueueFull:
            logger.warning(f"[OutlineWebhook] 큐 가득 참, 이벤트 드롭: {document_id}")
            return False

    async def _process_loop(self):
        """큐에서 이벤트를 꺼내 1건씩 순차 처리"""
        from app.services.outline_sync_service import get_outline_sync_service

        while True:
            try:
                document_id, event_type, received_at = await self._queue.get()
                self._pending.discard(document_id)
                self._processing = True
                self._current_doc_id = document_id

                logger.info(f"[OutlineWebhook] 처리 시작: {event_type} {document_id}")

                sync_service = get_outline_sync_service()
                result = await sync_service.process_single_document(document_id, event_type)

                self._stats["total_processed"] += 1
                logger.info(f"[OutlineWebhook] 처리 완료: {result}")

            except asyncio.CancelledError:
                logger.info("[OutlineWebhook] Worker 종료 요청")
                break
            except Exception as e:
                self._stats["total_errors"] += 1
                logger.error(f"[OutlineWebhook] 처리 실패 ({document_id}): {e}", exc_info=True)
            finally:
                self._processing = False
                self._current_doc_id = None
                self._queue.task_done()

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Outline webhook 서명 검증 (HMAC-SHA256)

        Args:
            payload: 원본 요청 body (bytes)
            signature: Outline-Signature 헤더 값

        Returns:
            검증 성공 여부
        """
        if not WEBHOOK_SECRET:
            # 시크릿 미설정 → 검증 스킵 (개발 환경)
            return True

        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Outline은 "sha256=..." 형식으로 보낼 수 있음
        sig_value = signature.removeprefix("sha256=") if signature else ""
        return hmac.compare_digest(expected, sig_value)

    def get_status(self) -> dict:
        """현재 상태 조회"""
        return {
            "worker_running": self._worker_task is not None and not self._worker_task.done(),
            "processing": self._processing,
            "current_doc_id": self._current_doc_id,
            "queue_size": self._queue.qsize(),
            "pending_doc_ids": len(self._pending),
            **self._stats,
        }


# ── 싱글톤 ────────────────────────────────────────────────────
_outline_webhook_service: Optional[OutlineWebhookService] = None


def get_outline_webhook_service() -> OutlineWebhookService:
    global _outline_webhook_service
    if _outline_webhook_service is None:
        _outline_webhook_service = OutlineWebhookService()
    return _outline_webhook_service

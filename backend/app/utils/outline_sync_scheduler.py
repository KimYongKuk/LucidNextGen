# -*- coding: utf-8 -*-
"""
Outline Wiki ↔ ChromaDB 폴백 동기화 스케줄러

Webhook이 주된 동기화 경로이며, 이 스케줄러는 놓친 webhook을
보완하기 위한 폴백 delta sync를 실행합니다.
기본 주기: 4시간 (환경변수로 조정 가능)
"""
import os
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 환경변수
ENABLED = lambda: os.getenv("OUTLINE_SYNC_ENABLED", "true").lower() == "true"
INTERVAL_MINUTES = lambda: int(os.getenv("OUTLINE_SYNC_INTERVAL_MINUTES", "240"))


class OutlineSyncScheduler:
    """Outline Wiki 폴백 동기화 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self):
        """스케줄러 시작"""
        if not ENABLED():
            logger.info("[OutlineSyncScheduler] Disabled via OUTLINE_SYNC_ENABLED env")
            return

        if not os.getenv("OUTLINE_API_KEY"):
            logger.warning("[OutlineSyncScheduler] OUTLINE_API_KEY not set, skipping")
            return

        interval = INTERVAL_MINUTES()

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self._execute,
            trigger=IntervalTrigger(
                minutes=interval,
                timezone=KST,
            ),
            id="outline_wiki_sync",
            name="Outline Wiki ChromaDB Delta Sync",
            replace_existing=True,
            misfire_grace_time=120,
        )
        self.scheduler.start()
        logger.info(f"[OutlineSyncScheduler] Started - fallback delta sync every {interval} min")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[OutlineSyncScheduler] Stopped")

    async def _execute(self):
        """폴백 delta sync 실행"""
        logger.info("[OutlineSyncScheduler] 폴백 delta sync 시작...")
        try:
            from app.services.outline_sync_service import get_outline_sync_service
            service = get_outline_sync_service()
            result = await service.delta_sync()
            logger.info(f"[OutlineSyncScheduler] delta sync 완료: {result}")
        except Exception as e:
            logger.error(f"[OutlineSyncScheduler] delta sync 실패: {e}", exc_info=True)


outline_sync_scheduler = OutlineSyncScheduler()

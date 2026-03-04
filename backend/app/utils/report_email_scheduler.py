# -*- coding: utf-8 -*-
"""
주간 리포트 이메일 스케줄러
- APScheduler CronTrigger 기반 매주 자동 발송
- 기존 pdf_cleanup.py 패턴 답습
"""
import os
import logging
from datetime import date, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class ReportEmailScheduler:
    """주간 리포트 이메일 발송 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self):
        """스케줄러 시작"""
        if os.getenv("WEEKLY_REPORT_ENABLED", "false").lower() != "true":
            logger.info("[Weekly Report] Disabled via WEEKLY_REPORT_ENABLED env")
            return

        try:
            from app.services.weekly_report_service import get_weekly_report_manager
            manager = get_weekly_report_manager()
            config = manager.get_config()
        except Exception as e:
            logger.warning(f"[Weekly Report] Failed to load config (DB not ready?): {e}")
            # DB 없으면 기본값으로 스케줄러만 등록
            config = {"send_day": "mon", "send_hour": 9, "enabled": False}

        if not config.get("enabled", False):
            logger.info("[Weekly Report] Scheduler registered but disabled in config")

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self._execute,
            trigger=CronTrigger(
                day_of_week=config.get("send_day", "mon"),
                hour=config.get("send_hour", 9),
                minute=0,
            ),
            id="weekly_report_email",
            name="Weekly Report Email",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            f"[Weekly Report] Scheduler started - "
            f"{config.get('send_day', 'mon')} {config.get('send_hour', 9)}:00"
        )

    async def _execute(self):
        """주간 리포트 생성 + 발송 (CronTrigger에 의해 호출)"""
        try:
            from app.services.weekly_report_service import get_weekly_report_manager
            manager = get_weekly_report_manager()

            # DB에서 enabled 확인 (runtime toggle)
            config = manager.get_config()
            if not config.get("enabled", False):
                logger.info("[Weekly Report] Skipped: disabled in config")
                return

            date_to = date.today().strftime("%Y-%m-%d")
            date_from = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

            logger.info(f"[Weekly Report] Executing: {date_from} ~ {date_to}")
            result = manager.send_weekly_report(date_from, date_to)
            logger.info(f"[Weekly Report] Result: {result}")

        except Exception as e:
            logger.error(f"[Weekly Report] Execution failed: {e}", exc_info=True)

    def reschedule(self, day: str, hour: int):
        """스케줄 동적 변경 (Admin UI에서 설정 변경 시)"""
        if not self.scheduler:
            logger.warning("[Weekly Report] Cannot reschedule: scheduler not started")
            return

        try:
            self.scheduler.reschedule_job(
                "weekly_report_email",
                trigger=CronTrigger(day_of_week=day, hour=hour, minute=0),
            )
            logger.info(f"[Weekly Report] Rescheduled: {day} {hour}:00")
        except Exception as e:
            logger.error(f"[Weekly Report] Reschedule failed: {e}")

    def run_now(self) -> dict:
        """즉시 실행 (수동 트리거)"""
        try:
            from app.services.weekly_report_service import get_weekly_report_manager
            manager = get_weekly_report_manager()

            date_to = date.today().strftime("%Y-%m-%d")
            date_from = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

            return manager.send_weekly_report(date_from, date_to)
        except Exception as e:
            logger.error(f"[Weekly Report] Manual run failed: {e}")
            return {"success": False, "message": str(e)}

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[Weekly Report] Scheduler stopped")


# 전역 인스턴스
report_email_scheduler = ReportEmailScheduler()

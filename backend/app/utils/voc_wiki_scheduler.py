# -*- coding: utf-8 -*-
"""
IT VOC → L&F Wiki 자동 축적 스케줄러

매일 지정 시각(기본 06:00 KST)에 IT VOC 신규 해결 사례를
L&F Wiki "L&F IT 지식베이스" 컬렉션에 자동 축적합니다.
"""
import os
import logging
from datetime import date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 환경변수
ENABLED = lambda: os.getenv("VOC_WIKI_SYNC_ENABLED", "true").lower() == "true"
HOUR = lambda: int(os.getenv("VOC_WIKI_SYNC_HOUR", "6"))
COLLECTION_ID = lambda: os.getenv("VOC_WIKI_COLLECTION_ID", "")
RECIPIENT = lambda: os.getenv("VOC_WIKI_SYNC_RECIPIENT", "wg0403@landf.co.kr")


class VocWikiScheduler:
    """IT VOC → L&F Wiki 자동 축적 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self):
        """스케줄러 시작"""
        if not ENABLED():
            logger.info("[VOC Wiki Scheduler] Disabled via VOC_WIKI_SYNC_ENABLED env")
            return

        if not COLLECTION_ID():
            logger.warning("[VOC Wiki Scheduler] VOC_WIKI_COLLECTION_ID not set, skipping")
            return

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self._execute,
            trigger=CronTrigger(
                hour=HOUR(),
                minute=0,
                timezone=KST,
            ),
            id="voc_wiki_sync",
            name="IT VOC Wiki Sync",
            replace_existing=True,
            misfire_grace_time=60,  # 1분 이내 misfire만 실행 (서버 재시작 시 즉시 실행 방지)
        )
        self.scheduler.start()
        logger.info(f"[VOC Wiki Scheduler] Started - daily {HOUR():02d}:00 KST")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[VOC Wiki Scheduler] Stopped")

    async def run_now(self, target_date: str | None = None) -> dict:
        """
        수동 즉시 실행

        Args:
            target_date: YYYY-MM-DD 형식 시작일 (None이면 자동 판단)
        """
        try:
            since = date.fromisoformat(target_date) if target_date else None
            return await self._execute(since)
        except Exception as e:
            logger.error(f"[VOC Wiki Scheduler] Manual run failed: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    async def run_initial_load(self, months: int = 1) -> dict:
        """
        초기 적재: 최근 N개월치를 1주 단위로 순차 처리

        최신 주차부터 역순으로 처리하여 주제 분류가 점진적으로 안정화됩니다.

        Args:
            months: 적재할 개월 수 (기본 1)
        """
        collection_id = COLLECTION_ID()
        if not collection_id:
            return {"success": False, "message": "VOC_WIKI_COLLECTION_ID not set"}

        from app.services.voc_wiki_service import get_voc_wiki_service
        service = get_voc_wiki_service()

        today = date.today()
        start_date = today - timedelta(days=months * 30)
        total_result = {"success": True, "weeks": [], "total_voc": 0, "total_created": 0, "total_updated": 0}

        # 1주 단위로 나누기 (최신부터 역순)
        weeks = []
        current = today
        while current > start_date:
            week_start = max(current - timedelta(days=7), start_date)
            weeks.append((week_start, current))
            current = week_start

        logger.info(f"[VOC Wiki Scheduler] Initial load: {len(weeks)} weeks, {start_date} ~ {today}")

        for i, (week_start, week_end) in enumerate(weeks):
            logger.info(f"[VOC Wiki Scheduler] Processing week {i+1}/{len(weeks)}: {week_start} ~ {week_end}")
            try:
                result = await service.sync(collection_id, since=week_start)
                total_result["weeks"].append({
                    "week": f"{week_start} ~ {week_end}",
                    **result,
                })
                total_result["total_voc"] += result.get("voc_count", 0)
                total_result["total_created"] += result.get("created", 0)
                total_result["total_updated"] += result.get("updated", 0)
            except Exception as e:
                logger.error(f"[VOC Wiki Scheduler] Week {week_start}~{week_end} failed: {e}")
                total_result["weeks"].append({
                    "week": f"{week_start} ~ {week_end}",
                    "success": False,
                    "error": str(e),
                })
                total_result["success"] = False

        logger.info(f"[VOC Wiki Scheduler] Initial load completed: {total_result}")
        return total_result

    async def _execute(self, since: Optional[date] = None) -> dict:
        """메인 실행 로직"""
        try:
            collection_id = COLLECTION_ID()
            if not collection_id:
                logger.error("[VOC Wiki Scheduler] VOC_WIKI_COLLECTION_ID not set")
                return {"success": False, "message": "VOC_WIKI_COLLECTION_ID not set"}

            from app.services.voc_wiki_service import get_voc_wiki_service
            service = get_voc_wiki_service()

            result = await service.sync(collection_id, since=since)

            # 결과 메일 발송 (신규 건이 있거나 실패한 경우)
            if result.get("voc_count", 0) > 0 or not result.get("success", True):
                self._send_report_email(result)

            return result
        except Exception as e:
            logger.error(f"[VOC Wiki Scheduler] Execute failed (server will NOT crash): {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def _send_report_email(self, result: dict) -> None:
        """동기화 결과를 HTML 메일로 발송"""
        try:
            from app.services.email_service import get_email_service
            email_service = get_email_service()
            if not email_service.is_configured():
                return

            today_str = date.today().strftime("%Y-%m-%d")
            success = result.get("success", False)
            voc_count = result.get("voc_count", 0)
            created = result.get("created", 0)
            updated = result.get("updated", 0)
            status = "성공" if success else "실패"
            error = result.get("error", "")

            subject = f"[Lucid AI] IT VOC 위키 동기화 — {today_str} ({status})"

            html_body = f"""
            <div style="font-family:'맑은 고딕',sans-serif; max-width:600px; margin:0 auto;">
                <div style="background:#182F54; color:white; padding:16px 24px; border-radius:8px 8px 0 0;">
                    <h2 style="margin:0;">IT VOC 위키 동기화 결과</h2>
                    <p style="margin:4px 0 0; opacity:0.8;">{today_str}</p>
                </div>
                <div style="border:1px solid #E7EAEE; border-top:none; padding:24px; border-radius:0 0 8px 8px;">
                    <table style="width:100%; border-collapse:collapse;">
                        <tr><td style="padding:8px 0; color:#666;">상태</td>
                            <td style="padding:8px 0; font-weight:bold; color:{'#28a745' if success else '#dc3545'};">{status}</td></tr>
                        <tr><td style="padding:8px 0; color:#666;">처리 VOC 건수</td>
                            <td style="padding:8px 0; font-weight:bold;">{voc_count}건</td></tr>
                        <tr><td style="padding:8px 0; color:#666;">문서 생성</td>
                            <td style="padding:8px 0;">{created}건</td></tr>
                        <tr><td style="padding:8px 0; color:#666;">문서 업데이트</td>
                            <td style="padding:8px 0;">{updated}건</td></tr>
                        <tr><td style="padding:8px 0; color:#666;">조회 시작일</td>
                            <td style="padding:8px 0;">{result.get('since', '-')}</td></tr>
                    </table>
                    {f'<div style="margin-top:16px; padding:12px; background:#fff3cd; border-radius:4px; color:#856404;">에러: {error}</div>' if error else ''}
                    <div style="margin-top:20px; padding-top:16px; border-top:1px solid #E7EAEE; color:#999; font-size:12px;">
                        위키 확인: <a href="http://192.168.90.30:3003/collection/lf-it-jisigbeiseu-de491262-1f08-4b37-b375-dd0a0eda82e9">L&F IT 지식베이스</a>
                    </div>
                </div>
            </div>
            """

            email_service.send(
                to=RECIPIENT(),
                subject=subject,
                html_body=html_body,
            )
            logger.info(f"[VOC Wiki Scheduler] Report email sent to {RECIPIENT()}")

        except Exception as e:
            logger.error(f"[VOC Wiki Scheduler] Email send failed: {e}")


# 싱글톤
voc_wiki_scheduler = VocWikiScheduler()

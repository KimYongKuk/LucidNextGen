"""
PDF 파일 자동 정리 스케줄러
- 지정된 시간이 지난 PDF 파일을 자동으로 삭제
- APScheduler 기반
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# PDF 출력 디렉토리
PDF_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "pdf_output"

# 환경 변수에서 설정 읽기 (기본값: 24시간)
PDF_RETENTION_HOURS = int(os.getenv("PDF_RETENTION_HOURS", "24"))
PDF_CLEANUP_INTERVAL_HOURS = int(os.getenv("PDF_CLEANUP_INTERVAL_HOURS", "6"))


def cleanup_old_pdfs(retention_hours: Optional[int] = None) -> dict:
    """
    지정된 시간보다 오래된 PDF 파일 삭제

    Args:
        retention_hours: 파일 보관 시간 (시간 단위). None이면 환경 변수 사용

    Returns:
        삭제 결과 딕셔너리 {deleted: int, errors: int, total_size_kb: float}
    """
    if retention_hours is None:
        retention_hours = PDF_RETENTION_HOURS

    cutoff_time = datetime.now() - timedelta(hours=retention_hours)

    deleted = 0
    errors = 0
    total_size_kb = 0.0

    if not PDF_OUTPUT_DIR.exists():
        logger.info(f"[PDF Cleanup] Output directory does not exist: {PDF_OUTPUT_DIR}")
        return {"deleted": 0, "errors": 0, "total_size_kb": 0.0}

    for pdf_file in PDF_OUTPUT_DIR.glob("*.pdf"):
        try:
            file_mtime = datetime.fromtimestamp(pdf_file.stat().st_mtime)

            if file_mtime < cutoff_time:
                file_size = pdf_file.stat().st_size / 1024
                pdf_file.unlink()
                deleted += 1
                total_size_kb += file_size
                logger.debug(f"[PDF Cleanup] Deleted: {pdf_file.name} ({file_size:.1f} KB)")
        except Exception as e:
            errors += 1
            logger.error(f"[PDF Cleanup] Error deleting {pdf_file}: {e}")

    if deleted > 0:
        logger.info(
            f"[PDF Cleanup] Completed: {deleted} files deleted, "
            f"{total_size_kb:.1f} KB freed, {errors} errors"
        )

    return {"deleted": deleted, "errors": errors, "total_size_kb": total_size_kb}


class PDFCleanupScheduler:
    """PDF 자동 정리 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self, interval_hours: Optional[int] = None):
        """스케줄러 시작"""
        if interval_hours is None:
            interval_hours = PDF_CLEANUP_INTERVAL_HOURS

        self.scheduler = AsyncIOScheduler()

        # 주기적 정리 작업 등록
        self.scheduler.add_job(
            cleanup_old_pdfs,
            trigger=IntervalTrigger(hours=interval_hours),
            id="pdf_cleanup",
            name="PDF File Cleanup",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            f"[PDF Cleanup] Scheduler started - "
            f"Interval: {interval_hours}h, Retention: {PDF_RETENTION_HOURS}h"
        )

        # 시작 시 한 번 실행
        cleanup_old_pdfs()

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[PDF Cleanup] Scheduler stopped")

    def run_now(self) -> dict:
        """즉시 정리 실행"""
        return cleanup_old_pdfs()


# 전역 스케줄러 인스턴스
pdf_cleanup_scheduler = PDFCleanupScheduler()

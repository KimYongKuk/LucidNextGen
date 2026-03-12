"""
파일 자동 정리 스케줄러
- PDF, PPT, 차트, XLSX 출력 파일을 주기적으로 정리
- APScheduler 기반, 하나의 스케줄러로 모든 출력 디렉토리 순회
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# 기준 디렉토리 (backend/)
BASE_DIR = Path(__file__).parent.parent.parent

# 업로드 파일 보관 기간 (기본값: 7일)
UPLOAD_RETENTION_HOURS = int(os.getenv("UPLOAD_RETENTION_HOURS", "168"))

# 정리 대상 디렉토리 목록 — 모든 사용자 파일 영구 보존 (자동 삭제 비활성화)
# 필요 시 항목을 추가하여 자동 정리를 다시 활성화할 수 있음
# 예: {"dir": "data/chart_output", "pattern": "*.png", "retention_hours": 8760}
CLEANUP_TARGETS = []

# 환경 변수에서 설정 읽기 (기본값: 1년 보관, 24시간 간격)
FILE_RETENTION_HOURS = int(os.getenv("FILE_RETENTION_HOURS", "8760"))
FILE_CLEANUP_INTERVAL_HOURS = int(os.getenv("FILE_CLEANUP_INTERVAL_HOURS", "24"))


def cleanup_old_files(retention_hours: Optional[int] = None) -> dict:
    """
    지정된 시간보다 오래된 출력 파일 삭제

    Args:
        retention_hours: 파일 보관 시간 (시간 단위). None이면 환경 변수 사용

    Returns:
        삭제 결과 딕셔너리 {deleted: int, errors: int, total_size_kb: float}
    """
    if retention_hours is None:
        retention_hours = FILE_RETENTION_HOURS

    total_deleted = 0
    total_errors = 0
    total_size_kb = 0.0

    for target in CLEANUP_TARGETS:
        target_dir = BASE_DIR / target["dir"]
        pattern = target["pattern"]
        remove_empty_dirs = target.get("remove_empty_dirs", False)
        # per-target retention (미지정 시 글로벌 값 사용)
        target_retention = target.get("retention_hours", retention_hours)
        target_cutoff = datetime.now() - timedelta(hours=target_retention)

        if not target_dir.exists():
            continue

        deleted = 0
        for file_path in target_dir.glob(pattern):
            if not file_path.is_file():
                continue
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < target_cutoff:
                    file_size = file_path.stat().st_size / 1024
                    file_path.unlink()
                    deleted += 1
                    total_size_kb += file_size
                    logger.debug(f"[File Cleanup] Deleted: {file_path.name} ({file_size:.1f} KB)")
            except Exception as e:
                total_errors += 1
                logger.error(f"[File Cleanup] Error deleting {file_path}: {e}")

        # 빈 하위 디렉토리 정리 (xlsx_upload/session_id/ 등)
        if remove_empty_dirs:
            for sub_dir in sorted(target_dir.iterdir(), reverse=True):
                if sub_dir.is_dir():
                    try:
                        if not any(sub_dir.iterdir()):
                            sub_dir.rmdir()
                            logger.debug(f"[File Cleanup] Removed empty dir: {sub_dir.name}")
                    except Exception:
                        pass

        total_deleted += deleted

    if total_deleted > 0:
        logger.info(
            f"[File Cleanup] Completed: {total_deleted} files deleted, "
            f"{total_size_kb:.1f} KB freed, {total_errors} errors"
        )

    return {"deleted": total_deleted, "errors": total_errors, "total_size_kb": total_size_kb}


class FileCleanupScheduler:
    """출력 파일 자동 정리 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self, interval_hours: Optional[int] = None):
        """스케줄러 시작"""
        if interval_hours is None:
            interval_hours = FILE_CLEANUP_INTERVAL_HOURS

        self.scheduler = AsyncIOScheduler()

        self.scheduler.add_job(
            cleanup_old_files,
            trigger=IntervalTrigger(hours=interval_hours),
            id="file_cleanup",
            name="Output File Cleanup",
            replace_existing=True,
        )

        self.scheduler.start()

        target_dirs = [t["dir"] for t in CLEANUP_TARGETS]
        logger.info(
            f"[File Cleanup] Scheduler started - "
            f"Interval: {interval_hours}h, Retention: {FILE_RETENTION_HOURS}h, "
            f"Targets: {target_dirs}"
        )

        # 시작 시 한 번 실행
        cleanup_old_files()

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[File Cleanup] Scheduler stopped")

    def run_now(self) -> dict:
        """즉시 정리 실행"""
        return cleanup_old_files()


# 전역 스케줄러 인스턴스
file_cleanup_scheduler = FileCleanupScheduler()

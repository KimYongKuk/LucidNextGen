"""
ChromaDB 세션 컬렉션 자동 정리 스케줄러
- 오래된 session_* 컬렉션을 주기적으로 삭제
- workspace_* 및 user_* 컬렉션은 절대 삭제하지 않음
- APScheduler 기반
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# 환경 변수에서 설정 읽기 (기본값: 24시간 보관, 6시간 간격)
SESSION_RETENTION_HOURS = int(os.getenv("SESSION_RETENTION_HOURS", "24"))
SESSION_CLEANUP_INTERVAL_HOURS = int(os.getenv("SESSION_CLEANUP_INTERVAL_HOURS", "6"))


def _check_metadata_staleness(client, collection_name: str, cutoff_time: datetime) -> bool:
    """
    ChromaDB 청크 메타데이터의 uploaded_at으로 컬렉션 staleness 판단.
    Returns True이면 삭제 대상.
    """
    try:
        collection_obj = client.get_collection(name=collection_name)

        # 빈 컬렉션 → 삭제
        if collection_obj.count() == 0:
            return True

        result = collection_obj.get(limit=1, include=["metadatas"])

        if not result or not result.get("metadatas") or not result["metadatas"]:
            return True

        metadata = result["metadatas"][0]
        uploaded_at_str = metadata.get("uploaded_at")

        if not uploaded_at_str:
            return True

        uploaded_at = datetime.fromisoformat(uploaded_at_str)
        if uploaded_at.tzinfo is None:
            uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)

        return uploaded_at < cutoff_time

    except Exception as e:
        logger.warning(f"[Session Cleanup] Metadata check failed for {collection_name}: {e}")
        # 확인 불가하면 삭제하지 않음 (보수적 접근)
        return False


def cleanup_old_session_collections(retention_hours: Optional[int] = None) -> dict:
    """
    retention_hours보다 오래된 session_* 컬렉션 삭제

    Args:
        retention_hours: 컬렉션 보관 시간 (시간 단위). None이면 환경 변수 사용

    Returns:
        {"deleted": int, "skipped": int, "errors": int}
    """
    if retention_hours is None:
        retention_hours = SESSION_RETENTION_HOURS

    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    cutoff_local = datetime.now() - timedelta(hours=retention_hours)

    deleted = 0
    skipped = 0
    errors = 0

    # ChromaDB 클라이언트 획득
    try:
        from app.services.chromadb_service import get_user_chromadb_service
        client = get_user_chromadb_service().client
    except Exception as e:
        logger.error(f"[Session Cleanup] Failed to get ChromaDB client: {e}")
        return {"deleted": 0, "skipped": 0, "errors": 1}

    # 전체 컬렉션 목록
    try:
        all_collections = client.list_collections()
    except Exception as e:
        logger.error(f"[Session Cleanup] Failed to list collections: {e}")
        return {"deleted": 0, "skipped": 0, "errors": 1}

    # session_* 컬렉션만 필터
    session_collections: List[str] = []
    for c in all_collections:
        if isinstance(c, str):
            name = c
        else:
            name = getattr(c, "name", getattr(c, "_name", None))
        if name and name.startswith("session_"):
            session_collections.append(name)

    if not session_collections:
        return {"deleted": 0, "skipped": 0, "errors": 0}

    logger.info(f"[Session Cleanup] Found {len(session_collections)} session collections to evaluate")

    # DB 연결 시도 (chat_sessions cross-reference)
    db = None
    try:
        from app.core.database import get_database_connection
        db = get_database_connection()
    except Exception as e:
        logger.warning(f"[Session Cleanup] DB unavailable, falling back to metadata check: {e}")

    for collection_name in session_collections:
        try:
            session_id = collection_name[len("session_"):]
            should_delete = False
            reason = ""

            if db is not None:
                # DB cross-reference
                try:
                    with db.get_cursor() as cursor:
                        cursor.execute(
                            "SELECT updated_at FROM chat_sessions WHERE session_id = %s",
                            (session_id,)
                        )
                        row = cursor.fetchone()

                    if row is None:
                        # DB에 없음 → 고아 컬렉션
                        should_delete = True
                        reason = "orphan (not in chat_sessions)"
                    else:
                        updated_at = row["updated_at"]
                        if updated_at < cutoff_local:
                            should_delete = True
                            reason = f"stale (updated_at={updated_at})"
                        else:
                            skipped += 1
                            continue
                except Exception as db_err:
                    logger.warning(
                        f"[Session Cleanup] DB query failed for {collection_name}, "
                        f"falling back to metadata: {db_err}"
                    )
                    should_delete = _check_metadata_staleness(client, collection_name, cutoff_utc)
                    reason = "metadata fallback (DB query failed)"
            else:
                # DB 불가 → 메타데이터 폴백
                should_delete = _check_metadata_staleness(client, collection_name, cutoff_utc)
                reason = "metadata check (DB unavailable)"

            if should_delete:
                client.delete_collection(name=collection_name)
                deleted += 1
                logger.debug(f"[Session Cleanup] Deleted: {collection_name} ({reason})")
            else:
                skipped += 1

        except Exception as e:
            errors += 1
            logger.error(f"[Session Cleanup] Error processing {collection_name}: {e}")

    if deleted > 0 or errors > 0:
        logger.info(
            f"[Session Cleanup] Completed: {deleted} deleted, "
            f"{skipped} skipped, {errors} errors"
        )

    return {"deleted": deleted, "skipped": skipped, "errors": errors}


class SessionCleanupScheduler:
    """ChromaDB 세션 컬렉션 자동 정리 스케줄러"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self, interval_hours: Optional[int] = None):
        """스케줄러 시작"""
        if interval_hours is None:
            interval_hours = SESSION_CLEANUP_INTERVAL_HOURS

        self.scheduler = AsyncIOScheduler()

        self.scheduler.add_job(
            cleanup_old_session_collections,
            trigger=IntervalTrigger(hours=interval_hours),
            id="session_collection_cleanup",
            name="ChromaDB Session Collection Cleanup",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            f"[Session Cleanup] Scheduler started - "
            f"Interval: {interval_hours}h, Retention: {SESSION_RETENTION_HOURS}h"
        )

        # 시작 시 한 번 실행
        cleanup_old_session_collections()

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[Session Cleanup] Scheduler stopped")

    def run_now(self) -> dict:
        """즉시 정리 실행"""
        return cleanup_old_session_collections()


# 전역 스케줄러 인스턴스
session_cleanup_scheduler = SessionCleanupScheduler()

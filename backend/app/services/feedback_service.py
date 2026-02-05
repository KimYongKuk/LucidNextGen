# -*- coding: utf-8 -*-
"""Anonymous feedback service"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.core.database import get_database_connection


class FeedbackService:
    """Anonymous feedback CRUD operations"""

    def __init__(self):
        self.db = get_database_connection()

    def create_feedback(self, message: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new feedback (user_id stored but not exposed in responses)"""
        feedback_id = str(uuid.uuid4())

        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO anonymous_feedback (feedback_id, message, user_id)
                VALUES (%s, %s, %s)
            """, (feedback_id, message, user_id))

            # Get the created record
            cursor.execute("""
                SELECT feedback_id, message, created_at
                FROM anonymous_feedback
                WHERE feedback_id = %s
            """, (feedback_id,))
            row = cursor.fetchone()

        return {
            "feedback_id": row["feedback_id"],
            "message": row["message"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        }

    def list_feedbacks(
        self,
        limit: int = 50,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List feedbacks with cursor-based pagination.
        Cursor is ISO datetime string.
        Returns newest first.
        """
        query = """
            SELECT feedback_id, message, created_at
            FROM anonymous_feedback
        """
        params: List[Any] = []

        if cursor:
            query += " WHERE created_at < %s"
            params.append(cursor)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit + 1)  # Fetch one extra to detect has_more

        with self.db.get_cursor() as db_cursor:
            db_cursor.execute(query, params)
            rows = db_cursor.fetchall()

        has_more = len(rows) > limit
        feedbacks = rows[:limit]

        next_cursor = None
        if has_more and feedbacks:
            last_item = feedbacks[-1]
            next_cursor = last_item["created_at"].isoformat() if last_item["created_at"] else None

        return {
            "feedbacks": [
                {
                    "feedback_id": row["feedback_id"],
                    "message": row["message"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
                for row in feedbacks
            ],
            "has_more": has_more,
            "next_cursor": next_cursor
        }

    def get_feedbacks_since(self, timestamp: str) -> Dict[str, Any]:
        """
        Get feedbacks created after the given timestamp.
        Used for polling new feedbacks.
        """
        query = """
            SELECT feedback_id, message, created_at
            FROM anonymous_feedback
            WHERE created_at > %s
            ORDER BY created_at ASC
        """

        with self.db.get_cursor() as cursor:
            cursor.execute(query, (timestamp,))
            rows = cursor.fetchall()

        feedbacks = [
            {
                "feedback_id": row["feedback_id"],
                "message": row["message"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None
            }
            for row in rows
        ]

        latest_timestamp = None
        if feedbacks:
            latest_timestamp = feedbacks[-1]["created_at"]

        return {
            "feedbacks": feedbacks,
            "latest_timestamp": latest_timestamp
        }


# Singleton instance
_feedback_service: Optional[FeedbackService] = None


def get_feedback_service() -> FeedbackService:
    """Get singleton instance of FeedbackService"""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService()
    return _feedback_service
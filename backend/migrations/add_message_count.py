#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration: Add message_count field to chat_sessions table
Date: 2025-12-11
"""
from app.core.database import get_database_connection


def migrate():
    """Add message_count field and backfill existing data."""
    db = get_database_connection()

    with db.get_cursor() as cursor:
        print("[Migration] Step 1: Adding message_count column...")
        try:
            cursor.execute("""
                ALTER TABLE chat_sessions
                ADD COLUMN message_count INT DEFAULT 0 AFTER chat_mode
            """)
            print("[OK] message_count column added successfully")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("[WARN] message_count column already exists, skipping...")
            else:
                raise

        print("\n[Migration] Step 2: Backfilling message counts from chat_log_new...")
        cursor.execute("""
            UPDATE chat_sessions cs
            SET message_count = (
                SELECT COUNT(*)
                FROM chat_log_new cl
                WHERE cl.session = cs.session_id
            )
        """)
        rows_updated = cursor.rowcount
        print(f"[OK] Updated {rows_updated} sessions with actual message counts")

        print("\n[Migration] Step 3: Verification...")
        cursor.execute("""
            SELECT
                cs.session_id,
                cs.user_id,
                cs.title,
                cs.message_count,
                (SELECT COUNT(*) FROM chat_log_new cl WHERE cl.session = cs.session_id) as actual_count
            FROM chat_sessions cs
            LIMIT 10
        """)
        rows = cursor.fetchall()
        print("\nSample verification:")
        for row in rows:
            match = "[OK]" if row['message_count'] == row['actual_count'] else "[FAIL]"
            print(f"{match} Session: {row['session_id'][:20]}... | Stored: {row['message_count']} | Actual: {row['actual_count']}")

        print("\n[Migration] Step 4: Summary statistics...")
        cursor.execute("""
            SELECT
                COUNT(*) as total_sessions,
                SUM(message_count) as total_messages,
                AVG(message_count) as avg_messages,
                MAX(message_count) as max_messages
            FROM chat_sessions
        """)
        stats = cursor.fetchone()
        print(f"\nTotal Sessions: {stats['total_sessions']}")
        print(f"Total Messages: {stats['total_messages']}")
        print(f"Average Messages/Session: {stats['avg_messages']:.2f}")
        print(f"Max Messages in Session: {stats['max_messages']}")

        print("\n[SUCCESS] Migration completed successfully!")


if __name__ == "__main__":
    migrate()

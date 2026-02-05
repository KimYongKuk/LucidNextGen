#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Debug why chat_sessions is not being populated"""
from app.core.database import get_database_connection

db = get_database_connection()

print("=" * 60)
print("DEBUG: Chat Sessions Not Being Created")
print("=" * 60)

with db.get_cursor() as cursor:
    print("\n[1] Recent chat_log_new entries for A2304013:")
    cursor.execute("""
        SELECT userId, session, inputLog, createDate
        FROM chat_log_new
        WHERE userId = 'A2304013'
        ORDER BY createDate DESC
        LIMIT 5
    """)
    logs = cursor.fetchall()

    if not logs:
        print("  [WARN] No logs found for A2304013")
    else:
        for log in logs:
            session_id = log['session'] or '(NULL)'
            msg_preview = (log['inputLog'][:30] + '...') if len(log['inputLog']) > 30 else log['inputLog']
            print(f"  Session: {session_id}")
            print(f"  Message: {msg_preview}")
            print(f"  Date: {log['createDate']}")
            print()

    print("\n[2] chat_sessions entries for A2304013:")
    cursor.execute("""
        SELECT session_id, user_id, title, message_count, created_at
        FROM chat_sessions
        WHERE user_id = 'A2304013'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    sessions = cursor.fetchall()

    if not sessions:
        print("  [PROBLEM] No sessions found - this is the issue!")
    else:
        print(f"  Found {len(sessions)} sessions:")
        for sess in sessions:
            print(f"  Session: {sess['session_id']}, Title: {sess['title']}, Count: {sess['message_count']}")

    print("\n[3] Checking session IDs from logs that don't exist in chat_sessions:")
    cursor.execute("""
        SELECT DISTINCT cl.session
        FROM chat_log_new cl
        WHERE cl.userId = 'A2304013'
          AND cl.session IS NOT NULL
          AND cl.session != ''
          AND NOT EXISTS (
            SELECT 1 FROM chat_sessions cs WHERE cs.session_id = cl.session
          )
        LIMIT 10
    """)
    missing = cursor.fetchall()

    if missing:
        print(f"  [CRITICAL] Found {len(missing)} sessions in logs that are MISSING from chat_sessions:")
        for m in missing:
            print(f"    Missing session_id: {m['session']}")
    else:
        print("  [OK] All sessions in logs exist in chat_sessions")

    print("\n[4] Checking for NULL or empty session IDs in logs:")
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM chat_log_new
        WHERE userId = 'A2304013'
          AND (session IS NULL OR session = '')
    """)
    null_count = cursor.fetchone()['count']

    if null_count > 0:
        print(f"  [PROBLEM] Found {null_count} logs with NULL/empty session_id!")
        print("  This means save_chat_log is being called without session_id")
    else:
        print("  [OK] All logs have valid session IDs")

print("\n" + "=" * 60)
print("Analysis Complete")
print("=" * 60)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyze sessions and message counts"""
from app.core.database import get_database_connection

db = get_database_connection()

with db.get_cursor() as cursor:
    print("=== Message Count Per Session (Top 10) ===")
    cursor.execute('''
        SELECT session, COUNT(*) as msg_count
        FROM chat_log_new
        WHERE userId = "A2304013"
        GROUP BY session
        ORDER BY msg_count DESC
        LIMIT 10
    ''')
    rows = cursor.fetchall()
    for row in rows:
        print(f"Session: {row['session']}, Messages: {row['msg_count']}")

    print("\n=== Sessions WITHOUT message count field ===")
    cursor.execute('''
        SELECT cs.session_id, cs.title,
               (SELECT COUNT(*) FROM chat_log_new cl WHERE cl.session = cs.session_id) as actual_count
        FROM chat_sessions cs
        WHERE cs.user_id = "A2304013"
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    for row in rows:
        print(f"Session: {row['session_id']}, Title: {row['title']}, Actual Count: {row['actual_count']}")

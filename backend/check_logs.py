#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check recent chat logs"""
from app.core.database import get_database_connection

db = get_database_connection()

with db.get_cursor() as cursor:
    print("=== Latest chat_log_new entries for A2304013 ===")
    cursor.execute("""
        SELECT userId, session, inputLog, outputLog, createDate
        FROM chat_log_new
        WHERE userId = 'A2304013'
        ORDER BY createDate DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()

    if not rows:
        print("No logs found!")
    else:
        for i, r in enumerate(rows, 1):
            output_preview = (r['outputLog'][:50] + '...') if len(r['outputLog']) > 50 else r['outputLog']
            print(f"\n[{i}] Session: {r['session']}")
            print(f"    Input: {r['inputLog']}")
            print(f"    Output: {output_preview}")
            print(f"    Date: {r['createDate']}")

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check chat_sessions table structure"""
from app.core.database import get_database_connection

db = get_database_connection()

with db.get_cursor() as cursor:
    cursor.execute('DESCRIBE chat_sessions')
    rows = cursor.fetchall()

    print("=== chat_sessions Table Structure ===")
    for row in rows:
        print(row)

    print("\n=== Sample Data ===")
    cursor.execute('SELECT * FROM chat_sessions LIMIT 3')
    samples = cursor.fetchall()
    for sample in samples:
        print(sample)

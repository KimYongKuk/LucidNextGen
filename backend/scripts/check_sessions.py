import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import get_database_connection

def check_sessions():
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT session_id, user_id, project_id, title FROM chat_sessions WHERE user_id = 'A2304013' ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        print(f"{'Session ID':<36} | {'User ID':<20} | {'Project ID':<10} | {'Title'}")
        print("-" * 100)
        for row in rows:
            pid = str(row['project_id']) if row['project_id'] is not None else "NULL"
            print(f"{row['session_id']:<36} | {row['user_id']:<20} | {pid:<10} | {row['title']}")

if __name__ == "__main__":
    check_sessions()

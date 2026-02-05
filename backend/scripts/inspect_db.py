import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_database_connection

def inspect_db():
    db = get_database_connection()
    with db.get_cursor() as cursor:
        # Check tables
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("Tables:", [list(t.values())[0] for t in tables])

        # Check chat_sessions columns
        cursor.execute("DESCRIBE chat_sessions")
        columns = cursor.fetchall()
        print("\nchat_sessions columns:")
        for col in columns:
            print(f"- {col['Field']} ({col['Type']})")

if __name__ == "__main__":
    inspect_db()

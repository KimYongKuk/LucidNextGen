import os
import sys
from app.core.database import DatabaseConnection

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
sys.path.append(os.getcwd())

def check_schema():
    db = DatabaseConnection()
    with db.get_cursor() as cursor:
        cursor.execute("DESCRIBE chat_sessions")
        columns = cursor.fetchall()
        print("Columns in chat_sessions:")
        for col in columns:
            print(f"- {col['Field']} ({col['Type']})")
            
        is_pinned_exists = any(col['Field'] == 'is_pinned' for col in columns)
        if is_pinned_exists:
            print("\nSUCCESS: 'is_pinned' column exists.")
        else:
            print("\nFAILURE: 'is_pinned' column does NOT exist.")

if __name__ == "__main__":
    check_schema()

import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import get_database_connection

def add_pinned_column():
    db = get_database_connection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        print("Checking if 'is_pinned' column exists...")
        cursor.execute("SHOW COLUMNS FROM chat_sessions LIKE 'is_pinned'")
        result = cursor.fetchone()
        
        if result:
            print("'is_pinned' column already exists.")
        else:
            print("Adding 'is_pinned' column...")
            cursor.execute("ALTER TABLE chat_sessions ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("'is_pinned' column added successfully.")
            
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    add_pinned_column()

import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_database_connection

def init_db():
    db = get_database_connection()
    with db.get_cursor() as cursor:
        print("Creating 'projects' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INT AUTO_INCREMENT PRIMARY KEY,
                uuid VARCHAR(36) NOT NULL UNIQUE,
                user_id VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                instructions TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        print("  [OK] 'projects' table created (or exists).")

        # Check if project_id column exists in chat_sessions
        print("Checking 'chat_sessions' table...")
        cursor.execute("DESCRIBE chat_sessions")
        columns = cursor.fetchall()
        col_names = [col['Field'] for col in columns]
        
        if 'project_id' not in col_names:
            print("Adding 'project_id' column to 'chat_sessions'...")
            cursor.execute("""
                ALTER TABLE chat_sessions
                ADD COLUMN project_id INT NULL,
                ADD CONSTRAINT fk_chat_sessions_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
            """)
            print("  [OK] 'project_id' column added.")
        else:
            print("  [SKIP] 'project_id' column already exists.")

if __name__ == "__main__":
    try:
        init_db()
        print("\nDatabase initialization completed successfully.")
    except Exception as e:
        print(f"\n[ERROR] Database initialization failed: {e}")
        sys.exit(1)

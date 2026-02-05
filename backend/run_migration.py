"""Run database migration to add metadata column"""
import os
from dotenv import load_dotenv
import pymysql

load_dotenv()

# DB 연결 정보
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'genai_lucid'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def run_migration():
    """Execute migration to add metadata column"""
    connection = None
    try:
        # DB 연결
        print(f"Connecting to database: {DB_CONFIG['database']}@{DB_CONFIG['host']}")
        connection = pymysql.connect(**DB_CONFIG)

        with connection.cursor() as cursor:
            # 먼저 컬럼 존재 여부 확인
            print("\nChecking if metadata column already exists...")
            cursor.execute(f"""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = '{DB_CONFIG['database']}'
                  AND TABLE_NAME = 'chat_log_new'
                  AND COLUMN_NAME = 'metadata'
            """)
            result = cursor.fetchone()

            if result:
                print("[OK] metadata column already exists. Skipping migration.")
                return

            # 컬럼 추가
            print("\n[MIGRATE] Adding metadata column to chat_log_new table...")
            cursor.execute("""
                ALTER TABLE chat_log_new
                ADD COLUMN metadata JSON DEFAULT NULL
                COMMENT 'Images, sources, and other metadata (excludes CoT messages)'
            """)

            connection.commit()
            print("[OK] Migration completed successfully!")

            # 결과 확인
            cursor.execute(f"""
                SELECT COLUMN_NAME, DATA_TYPE, COLUMN_COMMENT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = '{DB_CONFIG['database']}'
                  AND TABLE_NAME = 'chat_log_new'
                  AND COLUMN_NAME = 'metadata'
            """)
            result = cursor.fetchone()
            print(f"\n[INFO] Column details:")
            print(f"  - Name: {result['COLUMN_NAME']}")
            print(f"  - Type: {result['DATA_TYPE']}")
            print(f"  - Comment: {result['COLUMN_COMMENT']}")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            connection.close()
            print("\n[CLOSE] Database connection closed.")

if __name__ == "__main__":
    print("="*60)
    print("DATABASE MIGRATION: Add metadata column")
    print("="*60)
    run_migration()
    print("\n" + "="*60)
    print("Migration script completed.")
    print("="*60)

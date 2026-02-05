"""
DB 마이그레이션: youtube_summaries 테이블 생성

실행 방법:
    python backend/migrations/add_youtube_summaries.py
"""
import sys
import os

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_database_connection


def create_youtube_summaries_table():
    """youtube_summaries 테이블 생성"""

    db = get_database_connection()

    # 테이블 생성 SQL
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS youtube_summaries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        video_id VARCHAR(20) NOT NULL UNIQUE,
        title TEXT NOT NULL,
        original_link VARCHAR(500) NOT NULL,
        summary TEXT NOT NULL,
        insight TEXT,
        keywords JSON,
        segments JSON,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        user_id VARCHAR(100),

        INDEX idx_video_id (video_id),
        INDEX idx_user_id (user_id),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """

    try:
        with db.get_cursor() as cursor:
            print("[Migration] youtube_summaries 테이블 생성 중...")
            cursor.execute(create_table_sql)
            print("[Migration] OK: youtube_summaries 테이블 생성 완료")

            # 테이블 구조 확인
            cursor.execute("DESCRIBE youtube_summaries")
            columns = cursor.fetchall()

            print("\n[Migration] 테이블 구조:")
            print("-" * 80)
            for col in columns:
                print(f"  {col['Field']:20} {col['Type']:20} {col['Null']:5} {col['Key']:5} {col['Default']}")
            print("-" * 80)

            return True

    except Exception as e:
        print(f"[Migration] ERROR: 오류 발생: {str(e)}")
        return False


if __name__ == "__main__":
    print("="*80)
    print("DB Migration: youtube_summaries 테이블 생성")
    print("="*80)
    print()

    success = create_youtube_summaries_table()

    print()
    if success:
        print("="*80)
        print("[Migration] 마이그레이션 성공!")
        print("="*80)
        sys.exit(0)
    else:
        print("="*80)
        print("[Migration] 마이그레이션 실패!")
        print("="*80)
        sys.exit(1)

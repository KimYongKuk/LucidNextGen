"""
프로젝트 → 워크스페이스 마이그레이션 스크립트

이 스크립트는 다음 작업을 수행합니다:
1. 'projects' 테이블을 'workspaces'로 이름 변경
2. 'chat_sessions.project_id' 컬럼을 'workspace_id'로 이름 변경
3. 외래키 제약조건 업데이트
4. 기존 데이터 보존

실행 방법:
    python backend/scripts/migrate_project_to_workspace.py

롤백 방법:
    python backend/scripts/rollback_workspace_to_project.py
"""

import sys
import os
from datetime import datetime

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_database_connection

def backup_tables():
    """마이그레이션 전 백업 테이블 생성"""
    db = get_database_connection()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    with db.get_cursor() as cursor:
        print(f"\n[BACKUP] Creating backup tables with timestamp: {timestamp}")
        
        # projects 테이블 백업
        print("  - Backing up 'projects' table...")
        cursor.execute(f"CREATE TABLE projects_backup_{timestamp} LIKE projects")
        cursor.execute(f"INSERT INTO projects_backup_{timestamp} SELECT * FROM projects")
        projects_count = cursor.rowcount
        print(f"    ✓ Backed up {projects_count} rows")
        
        # chat_sessions 테이블 백업 (project_id 컬럼 포함)
        print("  - Backing up 'chat_sessions' table...")
        cursor.execute(f"CREATE TABLE chat_sessions_backup_{timestamp} LIKE chat_sessions")
        cursor.execute(f"INSERT INTO chat_sessions_backup_{timestamp} SELECT * FROM chat_sessions")
        sessions_count = cursor.rowcount
        print(f"    ✓ Backed up {sessions_count} rows")
        
    return timestamp

def migrate_to_workspace():
    """프로젝트 → 워크스페이스 마이그레이션 실행"""
    db = get_database_connection()
    
    with db.get_cursor() as cursor:
        print("\n[MIGRATION] Starting migration process...")
        
        # 1. 외래키 제약조건 확인 및 삭제
        print("\n[STEP 1] Checking and dropping foreign key constraints...")
        cursor.execute("""
            SELECT CONSTRAINT_NAME 
            FROM information_schema.TABLE_CONSTRAINTS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'chat_sessions' 
            AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            AND CONSTRAINT_NAME LIKE '%project%'
        """)
        fk_constraints = cursor.fetchall()
        
        for fk in fk_constraints:
            fk_name = fk['CONSTRAINT_NAME']
            print(f"  - Dropping foreign key: {fk_name}")
            cursor.execute(f"ALTER TABLE chat_sessions DROP FOREIGN KEY {fk_name}")
            print(f"    ✓ Dropped")
        
        # 2. projects 테이블을 workspaces로 이름 변경
        print("\n[STEP 2] Renaming 'projects' table to 'workspaces'...")
        cursor.execute("RENAME TABLE projects TO workspaces")
        print("  ✓ Table renamed successfully")
        
        # 3. chat_sessions.project_id를 workspace_id로 이름 변경
        print("\n[STEP 3] Renaming 'project_id' column to 'workspace_id'...")
        cursor.execute("""
            ALTER TABLE chat_sessions 
            CHANGE COLUMN project_id workspace_id INT NULL
        """)
        print("  ✓ Column renamed successfully")
        
        # 4. 인덱스 이름 변경 (존재하는 경우)
        print("\n[STEP 4] Checking and updating indexes...")
        cursor.execute("""
            SELECT INDEX_NAME 
            FROM information_schema.STATISTICS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'chat_sessions' 
            AND INDEX_NAME LIKE '%project%'
        """)
        indexes = cursor.fetchall()
        
        for idx in indexes:
            idx_name = idx['INDEX_NAME']
            new_idx_name = idx_name.replace('project', 'workspace')
            print(f"  - Renaming index: {idx_name} → {new_idx_name}")
            # MySQL doesn't support direct index rename, so we need to drop and recreate
            cursor.execute(f"ALTER TABLE chat_sessions DROP INDEX {idx_name}")
            cursor.execute(f"ALTER TABLE chat_sessions ADD INDEX {new_idx_name} (workspace_id)")
            print(f"    ✓ Index updated")
        
        # 5. 외래키 제약조건 재생성
        print("\n[STEP 5] Creating new foreign key constraint...")
        cursor.execute("""
            ALTER TABLE chat_sessions
            ADD CONSTRAINT fk_chat_sessions_workspace
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
        """)
        print("  ✓ Foreign key constraint created")
        
        # 6. 데이터 검증
        print("\n[STEP 6] Verifying data integrity...")
        cursor.execute("SELECT COUNT(*) as count FROM workspaces")
        workspace_count = cursor.fetchone()['count']
        print(f"  - Workspaces count: {workspace_count}")
        
        cursor.execute("SELECT COUNT(*) as count FROM chat_sessions WHERE workspace_id IS NOT NULL")
        linked_sessions = cursor.fetchone()['count']
        print(f"  - Chat sessions linked to workspaces: {linked_sessions}")
        
        print("\n✅ Migration completed successfully!")
        print("\n⚠️  Next steps:")
        print("  1. Update backend code (services, routes, MCP server)")
        print("  2. Update frontend code (components, API client)")
        print("  3. Test the application thoroughly")
        print("  4. If issues occur, run: python backend/scripts/rollback_workspace_to_project.py")

def main():
    print("=" * 70)
    print("  PROJECT → WORKSPACE MIGRATION")
    print("=" * 70)
    print("\nThis script will:")
    print("  • Rename 'projects' table to 'workspaces'")
    print("  • Rename 'project_id' column to 'workspace_id'")
    print("  • Update foreign key constraints")
    print("  • Preserve all existing data")
    
    response = input("\n⚠️  Do you want to proceed? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n❌ Migration cancelled.")
        sys.exit(0)
    
    try:
        # 백업 생성
        timestamp = backup_tables()
        print(f"\n✓ Backup completed: projects_backup_{timestamp}, chat_sessions_backup_{timestamp}")
        
        # 마이그레이션 실행
        migrate_to_workspace()
        
        print(f"\n📝 Backup tables created:")
        print(f"  - projects_backup_{timestamp}")
        print(f"  - chat_sessions_backup_{timestamp}")
        print("\n  These can be used for rollback if needed.")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\n⚠️  The database may be in an inconsistent state.")
        print("  Please run the rollback script or restore from backup.")
        sys.exit(1)

if __name__ == "__main__":
    main()

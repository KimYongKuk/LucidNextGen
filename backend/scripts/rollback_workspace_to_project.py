"""
워크스페이스 → 프로젝트 롤백 스크립트

마이그레이션을 되돌리는 스크립트입니다.
이 스크립트는 다음 작업을 수행합니다:
1. 'workspaces' 테이블을 'projects'로 이름 변경
2. 'chat_sessions.workspace_id' 컬럼을 'project_id'로 이름 변경
3. 외래키 제약조건 업데이트

실행 방법:
    python backend/scripts/rollback_workspace_to_project.py
"""

import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_database_connection

def rollback_to_project():
    """워크스페이스 → 프로젝트 롤백 실행"""
    db = get_database_connection()
    
    with db.get_cursor() as cursor:
        print("\n[ROLLBACK] Starting rollback process...")
        
        # 1. 외래키 제약조건 확인 및 삭제
        print("\n[STEP 1] Checking and dropping foreign key constraints...")
        cursor.execute("""
            SELECT CONSTRAINT_NAME 
            FROM information_schema.TABLE_CONSTRAINTS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'chat_sessions' 
            AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            AND CONSTRAINT_NAME LIKE '%workspace%'
        """)
        fk_constraints = cursor.fetchall()
        
        for fk in fk_constraints:
            fk_name = fk['CONSTRAINT_NAME']
            print(f"  - Dropping foreign key: {fk_name}")
            cursor.execute(f"ALTER TABLE chat_sessions DROP FOREIGN KEY {fk_name}")
            print(f"    ✓ Dropped")
        
        # 2. workspaces 테이블을 projects로 이름 변경
        print("\n[STEP 2] Renaming 'workspaces' table to 'projects'...")
        cursor.execute("RENAME TABLE workspaces TO projects")
        print("  ✓ Table renamed successfully")
        
        # 3. chat_sessions.workspace_id를 project_id로 이름 변경
        print("\n[STEP 3] Renaming 'workspace_id' column to 'project_id'...")
        cursor.execute("""
            ALTER TABLE chat_sessions 
            CHANGE COLUMN workspace_id project_id INT NULL
        """)
        print("  ✓ Column renamed successfully")
        
        # 4. 인덱스 이름 변경 (존재하는 경우)
        print("\n[STEP 4] Checking and updating indexes...")
        cursor.execute("""
            SELECT INDEX_NAME 
            FROM information_schema.STATISTICS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'chat_sessions' 
            AND INDEX_NAME LIKE '%workspace%'
        """)
        indexes = cursor.fetchall()
        
        for idx in indexes:
            idx_name = idx['INDEX_NAME']
            new_idx_name = idx_name.replace('workspace', 'project')
            print(f"  - Renaming index: {idx_name} → {new_idx_name}")
            cursor.execute(f"ALTER TABLE chat_sessions DROP INDEX {idx_name}")
            cursor.execute(f"ALTER TABLE chat_sessions ADD INDEX {new_idx_name} (project_id)")
            print(f"    ✓ Index updated")
        
        # 5. 외래키 제약조건 재생성
        print("\n[STEP 5] Creating new foreign key constraint...")
        cursor.execute("""
            ALTER TABLE chat_sessions
            ADD CONSTRAINT fk_chat_sessions_project
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
        """)
        print("  ✓ Foreign key constraint created")
        
        # 6. 데이터 검증
        print("\n[STEP 6] Verifying data integrity...")
        cursor.execute("SELECT COUNT(*) as count FROM projects")
        project_count = cursor.fetchone()['count']
        print(f"  - Projects count: {project_count}")
        
        cursor.execute("SELECT COUNT(*) as count FROM chat_sessions WHERE project_id IS NOT NULL")
        linked_sessions = cursor.fetchone()['count']
        print(f"  - Chat sessions linked to projects: {linked_sessions}")
        
        print("\n✅ Rollback completed successfully!")
        print("\n⚠️  The database has been restored to the 'projects' schema.")

def main():
    print("=" * 70)
    print("  WORKSPACE → PROJECT ROLLBACK")
    print("=" * 70)
    print("\nThis script will:")
    print("  • Rename 'workspaces' table to 'projects'")
    print("  • Rename 'workspace_id' column to 'project_id'")
    print("  • Update foreign key constraints")
    print("  • Preserve all existing data")
    
    response = input("\n⚠️  Do you want to proceed with rollback? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n❌ Rollback cancelled.")
        sys.exit(0)
    
    try:
        rollback_to_project()
        
        print("\n📝 Note: You will also need to:")
        print("  1. Revert backend code changes")
        print("  2. Revert frontend code changes")
        print("  3. Restart the application")
        
    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        print("\n⚠️  The database may be in an inconsistent state.")
        print("  Please check the database manually or restore from backup.")
        sys.exit(1)

if __name__ == "__main__":
    main()

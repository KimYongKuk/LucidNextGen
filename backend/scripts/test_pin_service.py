import os
import sys
import asyncio
from app.services.chat_log_service import ChatLogService
from app.core.database import DatabaseConnection

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
sys.path.append(os.getcwd())

def test_pin_service():
    print("Testing ChatLogService.toggle_pin_status...")
    db = DatabaseConnection()
    service = ChatLogService(db)
    
    # 1. Get a session (try to find one from DB directly if list_sessions is empty for anonymous)
    with db.get_cursor() as cursor:
        cursor.execute("SELECT session_id, user_id FROM chat_sessions LIMIT 1")
        result = cursor.fetchone()
        
    if not result:
        print("No sessions found in DB.")
        return

    session_id = result['session_id']
    user_id = result['user_id']
    print(f"Testing with session_id: {session_id}, user_id: {user_id}")
    
    # 2. Pin
    print("Pinning...")
    success = service.toggle_pin_status(session_id, True)
    print(f"Pin success: {success}")
    
    # 3. Verify
    updated_sessions = service.list_sessions(user_id="anonymous", limit=1)
    is_pinned = updated_sessions['sessions'][0]['is_pinned']
    print(f"Is pinned: {is_pinned}")
    
    if is_pinned:
        print("SUCCESS: Session pinned.")
    else:
        print("FAILURE: Session NOT pinned.")
        
    # 4. Unpin
    print("Unpinning...")
    service.toggle_pin_status(session_id, False)
    print("Unpinned.")

if __name__ == "__main__":
    test_pin_service()

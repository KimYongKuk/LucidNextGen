import sys
import os
import asyncio

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.services.chat_log_service import get_chat_log_service

def test_list_sessions():
    service = get_chat_log_service()
    user_id = "A2304013" # Real user ID
    
    # 1. Test with project_id = None
    print("\n--- Testing project_id = None ---")
    result = service.list_sessions(user_id=user_id, project_id=None, limit=5)
    print(f"Count: {len(result['sessions'])}")
    for s in result['sessions']:
        print(f"Session: {s['session_id']}, Project: {s['project_id']}")

    # 2. Test with project_id = 2 (Known existing project)
    print("\n--- Testing project_id = 2 ---")
    result = service.list_sessions(user_id=user_id, project_id=2, limit=5)
    print(f"Count: {len(result['sessions'])}")
    for s in result['sessions']:
        print(f"Session: {s['session_id']}, Project: {s['project_id']}")

    # 3. Test with project_id = 999 (Non-existent)
    print("\n--- Testing project_id = 999 ---")
    result = service.list_sessions(user_id=user_id, project_id=999, limit=5)
    print(f"Count: {len(result['sessions'])}")
    for s in result['sessions']:
        print(f"Session: {s['session_id']}, Project: {s['project_id']}")

if __name__ == "__main__":
    test_list_sessions()

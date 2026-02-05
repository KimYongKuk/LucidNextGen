import requests
import sys
import os

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
sys.path.append(os.getcwd())

from app.core.database import DatabaseConnection

def get_session_id():
    db = DatabaseConnection()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT session_id FROM chat_sessions LIMIT 1")
        result = cursor.fetchone()
        return result['session_id'] if result else None

def test_api():
    session_id = get_session_id()
    if not session_id:
        print("No session found.")
        return

    print(f"Testing API with session_id: {session_id}")
    
    url = f"http://localhost:8000/api/v1/chat/sessions/{session_id}/pin"
    print(f"POST {url}")
    
    try:
        # Try setting to False (since it might be True from previous test)
        response = requests.post(url, json={"is_pinned": False})
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: API call succeeded.")
        else:
            print("FAILURE: API call failed.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()

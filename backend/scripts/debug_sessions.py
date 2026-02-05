import requests
import json

def debug_sessions():
    url = "http://localhost:8000/api/v1/chat/sessions?user_id=A2304013&project_id=2&limit=4"
    try:
        response = requests.get(url)
        data = response.json()
        print("Sessions count:", len(data.get("sessions", [])))
        print("Debug Info:")
        print(json.dumps(data.get("debug", {}), indent=2, ensure_ascii=False))
        
        print("\nSessions:")
        for s in data.get("sessions", []):
            print(f"- {s['title']} (Project ID: {s.get('project_id')})")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_sessions()

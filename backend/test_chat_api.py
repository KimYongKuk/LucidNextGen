"""채팅 API 및 로그 저장 테스트"""
import requests
import json
import time

API_URL = "http://localhost:8000/api/v1/chat/message/stream"

def test_chat_with_logging():
    """채팅 API 테스트 및 로그 저장 확인"""

    test_session_id = f"test_session_{int(time.time())}"

    payload = {
        "message": "안녕하세요? 간단한 인사를 해주세요.",
        "chat_mode": "normal",
        "session_id": test_session_id,
        "user_id": "test_user_api",
        "images": None,
        "message_history": None
    }

    print(f"[TEST] 세션 ID: {test_session_id}")
    print(f"[TEST] 요청 전송 중...")

    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=60
        )

        print(f"[TEST] 응답 상태: {response.status_code}")

        if response.status_code == 200:
            print("[TEST] 스트리밍 응답 수신 중...\n")

            collected_chunks = []

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')

                    if line_str.startswith('data: '):
                        data_str = line_str[6:].strip()

                        if data_str:
                            try:
                                data = json.loads(data_str)

                                # 콘텐츠 청크
                                if data.get('type') == 'content':
                                    chunk = data.get('chunk', '')
                                    collected_chunks.append(chunk)
                                    print(chunk, end='', flush=True)

                                # 타이밍 정보
                                elif data.get('type') == 'timing':
                                    step = data.get('step', '')
                                    if step and step not in ['AI 응답 생성 중']:
                                        print(f"\n[TIMING] {step}")

                                # 완료
                                elif data.get('complete'):
                                    print("\n\n[TEST] 스트리밍 완료!")
                                    break

                                # 에러
                                elif 'error' in data:
                                    print(f"\n[ERROR] {data['error']}")
                                    return False

                            except json.JSONDecodeError:
                                pass

            full_response = ''.join(collected_chunks)

            print(f"\n[TEST] 전체 응답 길이: {len(full_response)} 글자")
            print(f"\n[TEST] 이제 데이터베이스에서 로그 확인...")

            # 로그 확인
            time.sleep(2)  # DB 저장 대기

            from app.core.database import get_database_connection
            db = get_database_connection()

            with db.get_cursor() as cursor:
                cursor.execute(
                    'SELECT * FROM chat_log_new WHERE session = %s ORDER BY createDate DESC LIMIT 1',
                    (test_session_id,)
                )
                result = cursor.fetchone()

                if result:
                    print("\n✓ 로그가 성공적으로 저장되었습니다!")
                    print(f"  - 사용자 ID: {result['userId']}")
                    print(f"  - 생성 시간: {result['createDate']}")
                    print(f"  - 입력: {result['inputLog'][:50]}")
                    print(f"  - 출력 길이: {len(result['outputLog'])} 글자")
                    print(f"  - 모드: {result['chatMode']}")
                    print(f"  - 세션: {result['session']}")
                    return True
                else:
                    print("\n✗ 로그가 저장되지 않았습니다!")
                    return False
        else:
            print(f"[ERROR] API 오류: {response.status_code}")
            print(response.text)
            return False

    except Exception as e:
        print(f"[ERROR] 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_chat_with_logging()
    exit(0 if success else 1)

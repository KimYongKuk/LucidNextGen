import pymysql
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

print("=== DB 연결 테스트 ===")
print(f"Host: {os.getenv('DB_HOST')}")
print(f"Port: {os.getenv('DB_PORT')}")
print(f"User: {os.getenv('DB_USER')}")
print(f"Database: {os.getenv('DB_NAME')}")
print()

try:
    conn = pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        connect_timeout=5
    )
    print('[OK] DB connection success!')

    cursor = conn.cursor()
    cursor.execute('SELECT VERSION()')
    version = cursor.fetchone()
    print(f'[OK] MySQL Version: {version[0]}')

    cursor.execute('SHOW TABLES')
    tables = cursor.fetchall()
    print(f'[OK] Table count: {len(tables)}')

    if tables:
        print('\nTable list:')
        for t in tables:
            print(f'  - {t[0]}')

    conn.close()
    print('\nTest complete!')

except Exception as e:
    print(f'[FAIL] DB connection failed: {e}')

"""MySQL 데이터베이스 연결 설정 (Connection Pool)"""
import os
from typing import Optional
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from dotenv import load_dotenv
from dbutils.pooled_db import PooledDB

# .env 파일 로드
load_dotenv()


class DatabaseConnection:
    """MySQL 데이터베이스 연결 관리 (Connection Pool 사용)"""

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME", "chatbot")
        self.port = int(os.getenv("DB_PORT", "3306"))

        # 연결 풀 설정
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=int(os.getenv("DB_POOL_MAX_CONNECTIONS", "20")),
            mincached=int(os.getenv("DB_POOL_MIN_CACHED", "5")),
            maxcached=int(os.getenv("DB_POOL_MAX_CACHED", "10")),
            blocking=True,
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            charset='utf8mb4',
            cursorclass=DictCursor,
            autocommit=False
        )
        print(f"[DATABASE] Connection pool initialized: max={os.getenv('DB_POOL_MAX_CONNECTIONS', '20')}, min_cached={os.getenv('DB_POOL_MIN_CACHED', '5')}")

    def get_connection(self):
        """풀에서 연결 가져오기"""
        return self.pool.connection()

    @contextmanager
    def get_cursor(self):
        """컨텍스트 매니저로 커서 반환"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()


# 싱글톤 인스턴스
_db_connection: Optional[DatabaseConnection] = None


def get_database_connection() -> DatabaseConnection:
    """데이터베이스 연결 싱글톤 반환"""
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection()
    return _db_connection

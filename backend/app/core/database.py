"""MySQL 데이터베이스 연결 설정"""
import os
from typing import Optional
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class DatabaseConnection:
    """MySQL 데이터베이스 연결 관리"""

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME", "chatbot")
        self.port = int(os.getenv("DB_PORT", "3306"))

    def get_connection(self):
        """MySQL 연결 생성"""
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            charset='utf8mb4',
            cursorclass=DictCursor,
            autocommit=False
        )

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

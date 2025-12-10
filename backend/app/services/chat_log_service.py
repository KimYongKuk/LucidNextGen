"""채팅 로그 저장 서비스"""
from datetime import datetime
from typing import Optional
from app.core.database import get_database_connection


class ChatLogService:
    """채팅 로그를 MySQL에 저장하는 서비스"""

    def __init__(self):
        self.db = get_database_connection()

    async def save_chat_log(
        self,
        user_id: str,
        input_log: str,
        output_log: str,
        session: str,
        chat_mode: str = "normal",
        category_text: str = "temp"
    ) -> bool:
        """
        채팅 로그를 chat_log_new 테이블에 저장

        Args:
            user_id: 사용자 ID
            input_log: 사용자 질문 (프롬프트)
            output_log: AI 답변
            session: 세션 ID
            chat_mode: 채팅 모드 (기본값: "normal")
            category_text: 카테고리 (기본값: "temp")

        Returns:
            성공 여부 (True/False)
        """
        try:
            # 현재 시간 (YYYY-MM-DD HH:MM:SS)
            create_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # SQL INSERT 쿼리
            query = """
                INSERT INTO chat_log_new
                (userId, createDate, inputLog, outputLog, chatMode, categoryText, session)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            # 데이터베이스에 저장
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (
                    user_id,
                    create_date,
                    input_log,
                    output_log,
                    chat_mode,
                    category_text,
                    session
                ))

            print(f"[ChatLogService] Saved chat log for session: {session}")
            return True

        except Exception as e:
            print(f"[ChatLogService] Error saving chat log: {e}")
            return False


# 싱글톤 인스턴스
_chat_log_service: Optional[ChatLogService] = None


def get_chat_log_service() -> ChatLogService:
    """채팅 로그 서비스 싱글톤 반환"""
    global _chat_log_service
    if _chat_log_service is None:
        _chat_log_service = ChatLogService()
    return _chat_log_service

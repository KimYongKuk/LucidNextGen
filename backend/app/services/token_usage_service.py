"""토큰 사용량 로깅 서비스 — 모든 LLM 호출을 token_usage_log 테이블에 기록"""

import asyncio
import time
from typing import Optional, List, Dict

from app.core.database import get_database_connection


# 버퍼 flush 설정
_FLUSH_INTERVAL_SEC = 5
_FLUSH_BATCH_SIZE = 20


class TokenUsageService:
    """Fire-and-forget 방식 토큰 사용량 로깅. 내부 버퍼 + 주기적 batch INSERT."""

    def __init__(self):
        self.db = get_database_connection()
        self._buffer: List[Dict] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

    @staticmethod
    def _detect_model_type(model_id: str) -> str:
        model_lower = model_id.lower()
        if "haiku" in model_lower:
            return "haiku"
        return "sonnet"

    async def log(
        self,
        caller: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        api_key_name: Optional[str] = None,
    ):
        """토큰 사용량 버퍼에 추가. flush 스케줄링은 자동."""
        if input_tokens <= 0 and output_tokens <= 0:
            return

        entry = {
            "session_id": session_id,
            "user_id": user_id,
            "api_key_name": api_key_name,
            "caller": caller,
            "model_id": model_id,
            "model_type": self._detect_model_type(model_id),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
        }

        async with self._lock:
            self._buffer.append(entry)
            buf_len = len(self._buffer)

        print(f"[TOKEN_LOG] {caller} | {self._detect_model_type(model_id)} | in={input_tokens:,} out={output_tokens:,}")

        if buf_len >= _FLUSH_BATCH_SIZE:
            asyncio.create_task(self._flush())
        elif self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self):
        """일정 시간 후 flush"""
        await asyncio.sleep(_FLUSH_INTERVAL_SEC)
        await self._flush()

    async def _flush(self):
        """버퍼의 모든 항목을 batch INSERT"""
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO token_usage_log
                   (session_id, user_id, api_key_name, caller, model_id, model_type,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
                   VALUES (%(session_id)s, %(user_id)s, %(api_key_name)s, %(caller)s, %(model_id)s, %(model_type)s,
                           %(input_tokens)s, %(output_tokens)s, %(cache_read_tokens)s, %(cache_write_tokens)s)""",
                batch,
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"[TOKEN_LOG] flush error ({len(batch)} entries): {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# 싱글톤
_token_usage_service: Optional[TokenUsageService] = None


def get_token_usage_service() -> TokenUsageService:
    global _token_usage_service
    if _token_usage_service is None:
        _token_usage_service = TokenUsageService()
    return _token_usage_service

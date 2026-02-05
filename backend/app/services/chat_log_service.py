# -*- coding: utf-8 -*-
"""Chat log persistence service - SIMPLIFIED VERSION"""
from datetime import datetime
from typing import Optional
import re
from app.core.database import get_database_connection


class ChatLogService:
    """Persist chat logs into MySQL - SIMPLE AND DIRECT."""

    def __init__(self, bedrock_service=None):
        self.db = get_database_connection()
        self.bedrock = bedrock_service  # LLM 호출용 (title 생성)

    async def save_chat_log(
        self,
        user_id: str,
        input_log: str,
        output_log: str,
        session: str,
        chat_mode: str = "normal",
        category_text: str = "temp",
        metadata: Optional[dict] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """
        Save chat log - ALL IN ONE TRANSACTION, NO EXTERNAL CALLS.
        """
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            try:
                create_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                print(f"\n{'='*60}")
                print(f"[SAVE_CHAT_LOG] Starting transaction...")
                print(f"  User: {user_id}")
                print(f"  Session: {session}")
                print(f"  Message: {input_log[:50]}...")
                print(f"{'='*60}\n")

                # Step 1: Insert chat log (with metadata)
                print("[STEP 1] Inserting into chat_log_new...")
                import json
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
                cursor.execute("""
                    INSERT INTO chat_log_new
                    (userId, createDate, inputLog, outputLog, chatMode, categoryText, session, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, create_date, input_log, output_log, chat_mode, category_text, session, metadata_json))
                print("  [OK] chat_log_new INSERT successful")
                if metadata:
                    print(f"  [OK] Metadata saved: {len(metadata.get('images', []))} images, {len(metadata.get('sources', []))} sources")

                # Step 2: 먼저 UPDATE 시도 (기존 세션이면 성공)
                print("[STEP 2] Attempting UPDATE on chat_sessions...")
                
                # workspace_id가 있으면 함께 업데이트
                if workspace_id is not None:
                    cursor.execute("""
                        UPDATE chat_sessions
                        SET updated_at = %s, message_count = message_count + 1, workspace_id = %s
                        WHERE session_id = %s
                    """, (now, workspace_id, session))
                else:
                    cursor.execute("""
                        UPDATE chat_sessions
                        SET updated_at = %s, message_count = message_count + 1
                        WHERE session_id = %s
                    """, (now, session))

                # Step 3: 첫 대화라면 (rowcount == 0) → LLM으로 title 생성 후 INSERT
                if cursor.rowcount == 0:
                    print("[STEP 3] First message detected - generating title via LLM...")
                    title = await self._make_title_with_llm(input_log)
                    print(f"  [OK] Generated title: '{title}'")

                    cursor.execute("""
                        INSERT INTO chat_sessions
                        (session_id, user_id, chat_mode, message_count, title, created_at, updated_at, workspace_id)
                        VALUES (%s, %s, %s, 1, %s, %s, %s, %s)
                    """, (session, user_id, chat_mode, title, now, now, workspace_id))
                    print(f"  [OK] chat_sessions INSERT successful")
                else:
                    print(f"[STEP 3] Existing session - UPDATE successful (skipped title generation)")

                # Step 4: Commit
                print("[STEP 4] Committing transaction...")
                conn.commit()
                print("  [OK] COMMIT successful\n")

                print(f"{'='*60}")
                print(f"[SUCCESS] Chat log saved for session: {session}")
                print(f"{'='*60}\n")
                return True

            except Exception as inner_e:
                print(f"\n[ERROR] Transaction failed: {inner_e}")
                conn.rollback()
                print("[ROLLBACK] Transaction rolled back\n")
                raise inner_e
            finally:
                cursor.close()

        except Exception as e:
            import traceback
            print(f"\n{'='*60}")
            print(f"[FATAL ERROR] save_chat_log failed!")
            print(f"Error: {e}")
            print(f"Traceback:\n{traceback.format_exc()}")
            print(f"{'='*60}\n")
            return False
        finally:
            if conn:
                conn.close()

    async def _make_title_with_llm(self, text: str) -> str:
        """LLM을 사용하여 대화 제목 생성 (15자 이내)"""
        if not text:
            return "새 대화"

        # BedrockService가 없으면 폴백
        if not self.bedrock:
            print("  [WARNING] BedrockService not available, using fallback")
            return self._make_title_fallback(text)

        prompt = f"""다음 사용자 질문을 15자 이내로 요약해주세요.

사용자 질문: {text}

요구사항:
- 30자 이내 (한글 기준)
- 핵심 키워드, 문맥 중심
- 특수문자 제거
- 한글/영문만 사용
- 따옴표나 부가 설명 없이 제목만 출력

요약:"""

        try:
            response = await self.bedrock.generate_text(
                prompt=prompt,
                max_tokens=50,
                temperature=0.3
            )
            title = response.strip()
            # 따옴표 제거
            title = title.replace('"', "").replace("'", "")
            # 30자 제한
            title = title[:30] if len(title) > 30 else title

            return title if title else "새 대화"

        except Exception as e:
            print(f"  [ERROR] LLM title generation failed: {e}")
            print(f"  [FALLBACK] Using simple title extraction")
            return self._make_title_fallback(text)

    def _make_title_fallback(self, text: str) -> str:
        """LLM 실패 시 폴백: 기존 단순 방식"""
        if not text:
            return "새 대화"
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = normalized.replace('"', "").replace("'", "")
        if len(normalized) > 15:
            return normalized[:15]
        return normalized if normalized else "새 대화"

    def list_sessions(
        self,
        user_id: str,
        chat_mode: Optional[str] = None,
        range_scope: str = "recent7",
        limit: int = 100,
        cursor: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ):
        """Session listing with date range filter and cursor pagination."""

        query = """
            SELECT
                session_id,
                user_id,
                chat_mode,
                message_count,
                title,
                workspace_id,
                is_pinned,
                DATE_FORMAT(created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as created_at,
                DATE_FORMAT(updated_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as updated_at
            FROM chat_sessions
            WHERE user_id = %s
        """
        params = [user_id]

        # Project filtering
        if workspace_id is not None:
            query += " AND workspace_id = %s"
            params.append(workspace_id)

        # Range filtering: recent7 = last 7 days, all = no date filter
        if range_scope == "recent7":
            query += " AND updated_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"

        # Chat mode filtering
        if chat_mode:
            query += " AND chat_mode = %s"
            params.append(chat_mode)

        # Cursor pagination: "updated_at|session_id" format
        if cursor:
            try:
                parts = cursor.split("|")
                if len(parts) == 2:
                    cursor_updated_at, cursor_session_id = parts
                    query += """
                        AND (updated_at < %s OR
                             (updated_at = %s AND session_id < %s))
                    """
                    params.extend([cursor_updated_at, cursor_updated_at, cursor_session_id])
            except Exception:
                pass  # Invalid cursor, ignore and start from beginning

        query += " ORDER BY is_pinned DESC, updated_at DESC, session_id DESC LIMIT %s"
        params.append(limit + 1)  # fetch one extra to detect has_more

        with self.db.get_cursor() as cursor_obj:
            cursor_obj.execute(query, params)
            rows = cursor_obj.fetchall()

        # Generate next cursor if there are more results
        has_more = len(rows) > limit
        sessions = rows[:limit]
        next_cursor = None

        if has_more and sessions:
            last_session = sessions[-1]
            next_cursor = f"{last_session['updated_at']}|{last_session['session_id']}"

        return {
            "sessions": sessions,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def search_sessions(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list:
        """Search sessions by title and message content (inputLog)."""
        search_pattern = f"%{query}%"

        # Search in both chat_sessions.title and chat_log_new.inputLog
        # Use DISTINCT to avoid duplicates when multiple messages match
        sql = """
            SELECT DISTINCT
                cs.session_id,
                cs.user_id,
                cs.chat_mode,
                cs.message_count,
                cs.title,
                cs.workspace_id,
                cs.is_pinned,
                DATE_FORMAT(cs.created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as created_at,
                DATE_FORMAT(cs.updated_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as updated_at
            FROM chat_sessions cs
            LEFT JOIN chat_log_new cl ON cs.session_id = cl.session
            WHERE cs.user_id = %s
              AND (cs.title LIKE %s OR cl.inputLog LIKE %s)
            ORDER BY cs.updated_at DESC
            LIMIT %s
        """

        with self.db.get_cursor() as cursor:
            cursor.execute(sql, (user_id, search_pattern, search_pattern, limit))
            rows = cursor.fetchall()

        return rows

    def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        chat_mode: Optional[str] = None,
    ) -> bool:
        """Update mutable fields for a session."""
        fields = []
        params = []

        if title is not None:
            fields.append("title = %s")
            params.append(title)

        if chat_mode is not None:
            fields.append("chat_mode = %s")
            params.append(chat_mode)

        if not fields:
            return False

        fields.append("updated_at = %s")
        params.append(datetime.utcnow())
        params.append(session_id)

        query = f"UPDATE chat_sessions SET {', '.join(fields)} WHERE session_id = %s"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount > 0

    def toggle_pin_status(self, session_id: str, is_pinned: bool) -> bool:
        """Update is_pinned status for a session."""
        check_query = "SELECT 1 FROM chat_sessions WHERE session_id = %s"
        update_query = "UPDATE chat_sessions SET is_pinned = %s WHERE session_id = %s"
        
        with self.db.get_cursor() as cursor:
            # First check if session exists
            cursor.execute(check_query, (session_id,))
            if not cursor.fetchone():
                return False
                
            # Then update
            cursor.execute(update_query, (is_pinned, session_id))
            return True

    def delete_session(self, session_id: str) -> bool:
        """Delete session metadata and associated logs."""
        with self.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM chat_log_new WHERE session = %s", (session_id,))
            cursor.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
            return True

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session details by ID."""
        query = """
            SELECT
                session_id,
                user_id,
                chat_mode,
                message_count,
                title,
                workspace_id,
                DATE_FORMAT(created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as created_at,
                DATE_FORMAT(updated_at, '%%Y-%%m-%%dT%%H:%%i:%%s') as updated_at
            FROM chat_sessions
            WHERE session_id = %s
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (session_id,))
            row = cursor.fetchone()
            return row if row else None

    def get_session_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 100,
    ) -> list:
        """세션의 메시지 히스토리 조회 (시간순 정렬, metadata 포함)"""
        query = """
            SELECT
                userId,
                inputLog,
                outputLog,
                chatMode,
                metadata,
                DATE_FORMAT(createDate, '%%Y-%%m-%%dT%%H:%%i:%%sZ') as createDate
            FROM chat_log_new
            WHERE session = %s AND userId = %s
            ORDER BY createDate ASC
            LIMIT %s
        """

        with self.db.get_cursor() as cursor:
            cursor.execute(query, (session_id, user_id, limit))
            rows = cursor.fetchall()

        # UI 메시지 형식으로 변환 (user/assistant pair)
        import json
        messages = []
        for row in rows:
            # Parse metadata (images, sources)
            metadata = {}
            if row.get("metadata"):
                try:
                    if isinstance(row["metadata"], str):
                        metadata = json.loads(row["metadata"])
                    elif isinstance(row["metadata"], dict):
                        metadata = row["metadata"]
                except Exception as e:
                    print(f"[WARNING] Failed to parse metadata: {e}")
                    metadata = {}

            # User message
            messages.append({
                "role": "user",
                "content": row["inputLog"],
                "timestamp": row["createDate"],
            })
            # Assistant response (with metadata)
            assistant_msg = {
                "role": "assistant",
                "content": row["outputLog"],
                "timestamp": row["createDate"],
                "images": metadata.get("images", []),
                "sources": metadata.get("sources", []),
            }

            # YouTube 요약이 있으면 추가
            if metadata.get("youtube_summary"):
                assistant_msg["youtube_summary"] = metadata.get("youtube_summary")

            # Corp 문서 출처가 있으면 추가
            if metadata.get("corp_sources"):
                assistant_msg["corp_sources"] = metadata.get("corp_sources")

            # 차트 데이터가 있으면 추가
            if metadata.get("chart_data"):
                assistant_msg["chart_data"] = metadata.get("chart_data")

            messages.append(assistant_msg)

        return messages


_chat_log_service: Optional[ChatLogService] = None


def get_chat_log_service(bedrock_service=None) -> ChatLogService:
    """Return singleton instance of ChatLogService."""
    global _chat_log_service
    if _chat_log_service is None:
        # BedrockService 주입 (없으면 나중에 주입 가능)
        _chat_log_service = ChatLogService(bedrock_service=bedrock_service)
    elif bedrock_service is not None and _chat_log_service.bedrock is None:
        # 이미 생성되었지만 bedrock이 없으면 주입
        _chat_log_service.bedrock = bedrock_service
    return _chat_log_service

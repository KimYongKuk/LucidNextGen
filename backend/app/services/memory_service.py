# -*- coding: utf-8 -*-
"""Memory Service - 워크스페이스 메모리 + 사용자 전역 메모리 관리

워크스페이스 메모리: 롤링 요약(Rolling Summary) 패턴으로 프로젝트별 대화 기억
사용자 전역 메모리: Key Facts만 유지하여 사용자 개인 특성 기억 (모든 세션)
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any

from app.core.database import get_database_connection
from app.services.bedrock_service import BedrockService


# ============================================================
# 설정 상수 - 워크스페이스 메모리
# ============================================================
MEMORY_SUMMARY_THRESHOLD = 10       # N개 메시지마다 요약 업데이트
MEMORY_SUMMARY_MAX_LENGTH = 500     # 요약 최대 길이 (자)
MEMORY_KEY_FACTS_LIMIT = 10         # 최대 핵심 사실 개수
MEMORY_ENABLED = True               # 기능 활성화 플래그

# ============================================================
# 설정 상수 - 사용자 전역 메모리
# ============================================================
USER_MEMORY_ENABLED = os.environ.get("USER_MEMORY_ENABLED", "true").lower() == "true"
USER_MEMORY_THRESHOLD = 20          # 20개 메시지마다 추출 (전체 세션 합산)
USER_MEMORY_KEY_FACTS_LIMIT = 20    # 최대 20개 (워크스페이스보다 넓은 범위)
USER_MEMORY_MAX_NEW_FACTS = 3       # 1회 추출 시 최대 신규 3개 (선별적)


# ============================================================
# 프롬프트 템플릿
# ============================================================
SUMMARY_GENERATION_PROMPT = """당신은 대화 요약 전문가입니다.

## 기존 요약 (없으면 비어있음)
{existing_summary}

## 최근 대화 내용
{recent_messages}

## 작업 지시
위 정보를 통합하여 하나의 요약을 작성하세요.

요구사항:
1. 500자 이내로 작성
2. 핵심 결정사항, 진행 중인 작업, 사용자 선호도 우선
3. 최신 정보가 기존 정보와 충돌하면 최신 정보 우선
4. 일회성 질의응답은 생략 가능
5. 한국어로 작성

요약:"""


KEY_FACTS_EXTRACTION_PROMPT = """다음 대화에서 장기적으로 기억할 핵심 사실을 추출하세요.

## 대화 내용
{messages}

## 기존 핵심 사실
{existing_facts}

## 추출 기준
- 사용자 선호도 (기술, 스타일, 언어 등)
- 프로젝트 정보 (마감일, 요구사항, 제약조건)
- 반복되는 요청 패턴
- 명시적으로 "기억해줘"라고 한 내용

## 출력 형식
각 사실을 한 줄에 하나씩, 최대 5개만 출력하세요.
기존 사실과 중복되면 생략하세요.
**중요: 추출할 사실이 없으면 "NONE"만 출력하세요. 괄호 안 설명, 이유, 코멘트 등을 절대 쓰지 마세요.**

핵심 사실:"""


# ============================================================
# 프롬프트 템플릿 - 사용자 전역 메모리 (엄격한 선별 기준)
# ============================================================
USER_KEY_FACTS_EXTRACTION_PROMPT = """다음 대화에서 이 사용자에 대해 장기적으로 기억할 **개인적 특성**만 추출하세요.

## 대화 내용
{messages}

## 기존 핵심 사실
{existing_facts}

## 추출 기준 (엄격하게 적용)
**반드시 추출:**
- 사용자 이름, 부서, 직책, 역할
- 선호하는 도구, 언어, 커뮤니케이션 스타일
- 명시적으로 "기억해줘", "기억해", "잊지 마" 등으로 요청한 내용
- 반복적으로 나타나는 작업 패턴 (예: 항상 영어로 답변 요청)

**절대 추출하지 않는 것:**
- 일회성 질문이나 작업 내용 (예: "오늘 날씨", "이 코드 리뷰해줘")
- 특정 프로젝트의 세부사항 (마감일, 요구사항) — 워크스페이스 메모리 담당
- 검색한 정보나 뉴스 내용
- 대화 주제 자체 (무엇을 물어봤는지)

## 출력 형식
각 사실을 한 줄에 하나씩, 최대 {max_new_facts}개만 출력하세요.
기존 사실과 중복되면 생략하세요.
기존 사실을 업데이트해야 하면 "[업데이트] 기존내용 → 새내용" 형식으로 출력하세요.

**중요: 추출할 사실이 없으면 "NONE"만 출력하세요. 괄호 안 설명, 이유, 코멘트 등을 절대 쓰지 마세요.**

핵심 사실:"""


class WorkspaceMemoryService:
    """워크스페이스별 대화 메모리 관리 서비스"""

    def __init__(self):
        self.db = get_database_connection()
        self.bedrock = BedrockService()

    # --------------------------------------------------------
    # 메모리 조회
    # --------------------------------------------------------
    async def get_memory_context(
        self,
        workspace_id: str,  # UUID string
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        워크스페이스 메모리 컨텍스트 로드

        Returns:
            {
                "summary": "대화 요약 텍스트...",
                "key_facts": ["사실1", "사실2", ...],
                "last_updated": "2024-01-15T10:30:00"
            }
        """
        if not MEMORY_ENABLED:
            return None

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT summary, key_facts, last_summarized_at
                FROM workspace_memory
                WHERE workspace_id = %s AND user_id = %s
            """, (workspace_id, user_id))

            row = cursor.fetchone()
            if not row:
                return None

            summary = row["summary"]
            key_facts_json = row["key_facts"]
            last_updated = row["last_summarized_at"]

            # key_facts JSON 파싱
            key_facts = []
            if key_facts_json:
                try:
                    data = json.loads(key_facts_json)
                    key_facts = [f["content"] for f in data.get("facts", [])]
                except Exception:
                    pass

            return {
                "summary": summary or "",
                "key_facts": key_facts,
                "last_updated": last_updated.isoformat() if last_updated else None
            }

        except Exception as e:
            print(f"[MemoryService] Error loading memory: {e}")
            return None
        finally:
            if conn:
                conn.close()

    # --------------------------------------------------------
    # 요약 업데이트 필요 여부 확인
    # --------------------------------------------------------
    async def should_update_summary(
        self,
        workspace_id: str,  # UUID string
        user_id: str
    ) -> bool:
        """
        요약 업데이트가 필요한지 확인
        (총 메시지 수 - 마지막 요약 시점 메시지 수) >= THRESHOLD
        """
        if not MEMORY_ENABLED:
            print(f"[MemoryService] Memory disabled")
            return False

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            print(f"[MemoryService] Checking update for workspace_id={workspace_id}, user_id={user_id}")

            # 현재 워크스페이스 총 메시지 수 조회
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM chat_log_new cl
                JOIN chat_sessions cs ON cl.session = cs.session_id
                WHERE cs.workspace_id = %s AND cl.userId = %s
            """, (workspace_id, user_id))
            total_count = cursor.fetchone()["cnt"]

            # 마지막 요약 시점 메시지 수 조회
            cursor.execute("""
                SELECT last_summary_message_count
                FROM workspace_memory
                WHERE workspace_id = %s AND user_id = %s
            """, (workspace_id, user_id))

            row = cursor.fetchone()
            last_count = row["last_summary_message_count"] if row else 0

            should_update = (total_count - last_count) >= MEMORY_SUMMARY_THRESHOLD
            print(f"[MemoryService] total={total_count}, last={last_count}, threshold={MEMORY_SUMMARY_THRESHOLD}, should_update={should_update}")

            return should_update

        except Exception as e:
            print(f"[MemoryService] Error checking update: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if conn:
                conn.close()

    # --------------------------------------------------------
    # 롤링 요약 업데이트
    # --------------------------------------------------------
    async def update_summary(
        self,
        workspace_id: str,  # UUID string
        user_id: str
    ) -> bool:
        """
        롤링 요약 갱신 (백그라운드 실행)

        1. 기존 요약 로드
        2. 최근 N개 메시지 로드
        3. LLM으로 통합 요약 생성
        4. DB 업데이트
        """
        print(f"[MemoryService] Updating summary for workspace {workspace_id}")

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 1. 기존 요약 로드
            cursor.execute("""
                SELECT summary, key_facts FROM workspace_memory
                WHERE workspace_id = %s AND user_id = %s
            """, (workspace_id, user_id))

            row = cursor.fetchone()
            existing_summary = row["summary"] if row else ""
            existing_facts = row["key_facts"] if row else "{}"

            # 2. 최근 메시지 로드 (마지막 요약 이후)
            cursor.execute("""
                SELECT cl.inputLog, cl.outputLog, cl.createDate
                FROM chat_log_new cl
                JOIN chat_sessions cs ON cl.session = cs.session_id
                WHERE cs.workspace_id = %s AND cl.userId = %s
                ORDER BY cl.createDate DESC
                LIMIT %s
            """, (workspace_id, user_id, MEMORY_SUMMARY_THRESHOLD * 2))

            messages = cursor.fetchall()
            if not messages:
                return False

            # 메시지 포맷팅 (응답은 200자로 제한하여 토큰 절약)
            recent_messages = "\n".join([
                f"사용자: {m['inputLog']}\n어시스턴트: {m['outputLog'][:200] if m['outputLog'] else ''}..."
                for m in reversed(messages)
            ])

            # 3. LLM으로 새 요약 생성
            prompt = SUMMARY_GENERATION_PROMPT.format(
                existing_summary=existing_summary or "(없음)",
                recent_messages=recent_messages
            )

            new_summary = await self.bedrock.generate_text_haiku(prompt)

            # 길이 제한
            if len(new_summary) > MEMORY_SUMMARY_MAX_LENGTH:
                new_summary = new_summary[:MEMORY_SUMMARY_MAX_LENGTH] + "..."

            # 4. 핵심 사실 추출
            new_facts = await self._extract_key_facts(
                recent_messages,
                existing_facts
            )

            # 5. 총 메시지 수 조회
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM chat_log_new cl
                JOIN chat_sessions cs ON cl.session = cs.session_id
                WHERE cs.workspace_id = %s AND cl.userId = %s
            """, (workspace_id, user_id))
            total_count = cursor.fetchone()["cnt"]

            # 6. DB 업데이트 (UPSERT)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO workspace_memory
                (workspace_id, user_id, summary, key_facts,
                 total_message_count, last_summary_message_count, last_summarized_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    summary = VALUES(summary),
                    key_facts = VALUES(key_facts),
                    total_message_count = VALUES(total_message_count),
                    last_summary_message_count = VALUES(last_summary_message_count),
                    last_summarized_at = VALUES(last_summarized_at),
                    updated_at = NOW()
            """, (
                workspace_id, user_id, new_summary, new_facts,
                total_count, total_count, now
            ))

            conn.commit()
            print(f"[MemoryService] Summary updated successfully: {len(new_summary)} chars")
            return True

        except Exception as e:
            print(f"[MemoryService] Error updating summary: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    # --------------------------------------------------------
    # 핵심 사실 추출
    # --------------------------------------------------------
    async def _extract_key_facts(
        self,
        messages: str,
        existing_facts_json: str
    ) -> str:
        """LLM으로 핵심 사실 추출 및 기존 사실과 병합"""
        try:
            existing_facts = json.loads(existing_facts_json) if existing_facts_json else {"facts": []}
            existing_list = [f["content"] for f in existing_facts.get("facts", [])]

            prompt = KEY_FACTS_EXTRACTION_PROMPT.format(
                messages=messages,
                existing_facts="\n".join(f"- {f}" for f in existing_list) or "(없음)"
            )

            response = await self.bedrock.generate_text_haiku(prompt)

            # 응답 파싱
            new_facts = []
            for line in response.strip().split("\n"):
                line = line.strip().lstrip("- ").lstrip("• ").strip()
                if not line or len(line) <= 3:
                    continue
                # 무의미한 설명문 필터링
                if line.upper() == "NONE":
                    continue
                if line.startswith("(") and line.endswith(")"):
                    continue
                if any(kw in line for kw in ["없습니다", "추출할", "드러내지 않", "해당하는", "발견되지"]):
                    continue
                if line.startswith("#"):
                    continue
                if line not in existing_list:
                    new_facts.append({
                        "content": line,
                        "extracted_at": datetime.now().isoformat(),
                        "source_session": None
                    })

            # 기존 + 신규 병합, 최대 개수 제한
            all_facts = existing_facts.get("facts", []) + new_facts
            all_facts = all_facts[-MEMORY_KEY_FACTS_LIMIT:]  # 최신 N개만 유지

            return json.dumps({"facts": all_facts}, ensure_ascii=False)

        except Exception as e:
            print(f"[MemoryService] Error extracting facts: {e}")
            return existing_facts_json

    # --------------------------------------------------------
    # 메모리 삭제 (워크스페이스 삭제 시)
    # --------------------------------------------------------
    async def delete_memory(
        self,
        workspace_id: str,  # UUID string
        user_id: Optional[str] = None
    ) -> bool:
        """워크스페이스 메모리 삭제"""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    DELETE FROM workspace_memory
                    WHERE workspace_id = %s AND user_id = %s
                """, (workspace_id, user_id))
            else:
                cursor.execute("""
                    DELETE FROM workspace_memory
                    WHERE workspace_id = %s
                """, (workspace_id,))

            conn.commit()
            print(f"[MemoryService] Deleted memory for workspace {workspace_id}")
            return True

        except Exception as e:
            print(f"[MemoryService] Error deleting memory: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


# ============================================================
# 싱글톤 인스턴스
# ============================================================
_memory_service_instance = None


def get_memory_service() -> WorkspaceMemoryService:
    """WorkspaceMemoryService 싱글톤 인스턴스 반환"""
    global _memory_service_instance
    if _memory_service_instance is None:
        _memory_service_instance = WorkspaceMemoryService()
    return _memory_service_instance


# ============================================================
# 사용자 전역 메모리 서비스
# ============================================================

# 동시 추출 방지용 Lock (user_id별)
_extraction_locks: Dict[str, asyncio.Lock] = {}


class UserMemoryService:
    """사용자 전역 메모리 서비스 - key_facts만 유지, 모든 세션에서 공유"""

    def __init__(self):
        self.db = get_database_connection()
        self.bedrock = BedrockService()

    # --------------------------------------------------------
    # 메모리 조회
    # --------------------------------------------------------
    async def get_user_memory(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        사용자 전역 메모리 로드

        Returns:
            {
                "key_facts": ["사실1", "사실2", ...],
                "last_updated": "2024-01-15T10:30:00"
            }
        """
        if not USER_MEMORY_ENABLED:
            return None

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key_facts, last_extracted_at
                FROM user_memory
                WHERE user_id = %s
            """, (user_id,))

            row = cursor.fetchone()
            if not row:
                return None

            key_facts_json = row["key_facts"]
            last_updated = row["last_extracted_at"]

            # key_facts JSON 파싱
            key_facts = []
            if key_facts_json:
                try:
                    data = json.loads(key_facts_json)
                    key_facts = [f["content"] for f in data.get("facts", [])]
                except Exception:
                    pass

            if not key_facts:
                return None

            return {
                "key_facts": key_facts,
                "last_updated": last_updated.isoformat() if last_updated else None
            }

        except Exception as e:
            print(f"[UserMemory] Error loading memory: {e}")
            return None
        finally:
            if conn:
                conn.close()

    # --------------------------------------------------------
    # 추출 필요 여부 확인
    # --------------------------------------------------------
    async def should_extract_facts(self, user_id: str) -> bool:
        """
        key_facts 추출이 필요한지 확인
        (총 메시지 수 - 마지막 추출 시점 메시지 수) >= THRESHOLD
        """
        if not USER_MEMORY_ENABLED:
            return False

        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 사용자의 전체 메시지 수 (모든 세션)
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM chat_log_new
                WHERE userId = %s
            """, (user_id,))
            total_count = cursor.fetchone()["cnt"]

            # 마지막 추출 시점 메시지 수
            cursor.execute("""
                SELECT last_extraction_message_count
                FROM user_memory
                WHERE user_id = %s
            """, (user_id,))

            row = cursor.fetchone()
            last_count = row["last_extraction_message_count"] if row else 0

            should_extract = (total_count - last_count) >= USER_MEMORY_THRESHOLD
            print(f"[UserMemory] user={user_id}, total={total_count}, last={last_count}, threshold={USER_MEMORY_THRESHOLD}, should_extract={should_extract}")

            return should_extract

        except Exception as e:
            print(f"[UserMemory] Error checking extraction: {e}")
            return False
        finally:
            if conn:
                conn.close()

    # --------------------------------------------------------
    # key_facts 추출 및 업데이트
    # --------------------------------------------------------
    async def extract_and_update_facts(self, user_id: str) -> bool:
        """
        사용자 전역 key_facts 추출 (백그라운드 실행)

        1. 동시 실행 방지 (per-user lock)
        2. 기존 facts 로드
        3. 최근 메시지 로드
        4. LLM으로 key_facts 추출
        5. DB 업데이트
        """
        # 동시 실행 방지
        lock = _extraction_locks.setdefault(user_id, asyncio.Lock())
        if lock.locked():
            print(f"[UserMemory] Extraction already in progress for {user_id}, skipping")
            return False

        async with lock:
            print(f"[UserMemory] Extracting facts for user {user_id}")

            conn = None
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()

                # 1. 기존 facts 로드
                cursor.execute("""
                    SELECT key_facts FROM user_memory
                    WHERE user_id = %s
                """, (user_id,))

                row = cursor.fetchone()
                existing_facts_json = row["key_facts"] if row else "{}"

                # 2. 최근 메시지 로드 (전체 세션에서)
                cursor.execute("""
                    SELECT inputLog, outputLog, createDate
                    FROM chat_log_new
                    WHERE userId = %s
                    ORDER BY createDate DESC
                    LIMIT %s
                """, (user_id, USER_MEMORY_THRESHOLD * 2))

                messages = cursor.fetchall()
                if not messages:
                    return False

                # 메시지 포맷팅 (응답 200자 제한)
                recent_messages = "\n".join([
                    f"사용자: {m['inputLog']}\n어시스턴트: {m['outputLog'][:200] if m['outputLog'] else ''}..."
                    for m in reversed(messages)
                ])

                # 3. LLM으로 key_facts 추출
                new_facts_json = await self._extract_user_facts(
                    recent_messages,
                    existing_facts_json
                )

                # 4. 총 메시지 수 조회
                cursor.execute("""
                    SELECT COUNT(*) as cnt FROM chat_log_new
                    WHERE userId = %s
                """, (user_id,))
                total_count = cursor.fetchone()["cnt"]

                # 5. DB 업데이트 (UPSERT)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("""
                    INSERT INTO user_memory
                    (user_id, key_facts, total_message_count,
                     last_extraction_message_count, last_extracted_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        key_facts = VALUES(key_facts),
                        total_message_count = VALUES(total_message_count),
                        last_extraction_message_count = VALUES(last_extraction_message_count),
                        last_extracted_at = VALUES(last_extracted_at),
                        updated_at = NOW()
                """, (
                    user_id, new_facts_json,
                    total_count, total_count, now
                ))

                conn.commit()

                # 결과 로깅
                try:
                    facts_data = json.loads(new_facts_json)
                    facts_count = len(facts_data.get("facts", []))
                except Exception:
                    facts_count = 0
                print(f"[UserMemory] Facts updated for {user_id}: {facts_count} facts")

                return True

            except Exception as e:
                print(f"[UserMemory] Error extracting facts: {e}")
                import traceback
                traceback.print_exc()
                if conn:
                    conn.rollback()
                return False
            finally:
                if conn:
                    conn.close()

    # --------------------------------------------------------
    # 사용자 전역 key_facts 추출 (내부)
    # --------------------------------------------------------
    async def _extract_user_facts(
        self,
        messages: str,
        existing_facts_json: str
    ) -> str:
        """LLM으로 사용자 개인 특성 추출 및 기존 사실과 병합"""
        try:
            existing_facts = json.loads(existing_facts_json) if existing_facts_json else {"facts": []}
            existing_list = [f["content"] for f in existing_facts.get("facts", [])]

            prompt = USER_KEY_FACTS_EXTRACTION_PROMPT.format(
                messages=messages,
                existing_facts="\n".join(f"- {f}" for f in existing_list) or "(없음)",
                max_new_facts=USER_MEMORY_MAX_NEW_FACTS
            )

            response = await self.bedrock.generate_text_haiku(prompt)

            # 응답 파싱
            new_facts = []
            updated_indices = set()  # 업데이트된 기존 fact의 인덱스

            for line in response.strip().split("\n"):
                line = line.strip().lstrip("- ").lstrip("• ").strip()
                if not line or len(line) <= 3:
                    continue

                # "NONE" 또는 무의미한 설명문 필터링
                if line.upper() == "NONE":
                    continue
                # 괄호로 감싼 설명문 필터 (예: "(추출할 특성이 없습니다)")
                if line.startswith("(") and line.endswith(")"):
                    continue
                # "없습니다" 류 설명문 필터
                if any(kw in line for kw in ["없습니다", "추출할", "드러내지 않", "해당하는", "발견되지"]):
                    continue
                # "# " 시작하는 마크다운 헤더 필터
                if line.startswith("#"):
                    continue

                # [업데이트] 처리: 기존 사실 교체
                if line.startswith("[업데이트]"):
                    update_content = line[len("[업데이트]"):].strip()
                    # "A → B" 형식에서 새 내용 추출
                    if "→" in update_content:
                        old_part, new_part = update_content.split("→", 1)
                        old_part = old_part.strip()
                        new_part = new_part.strip()

                        # 기존 facts에서 매칭되는 항목 찾아 교체
                        for i, existing in enumerate(existing_facts.get("facts", [])):
                            if old_part in existing["content"]:
                                existing["content"] = new_part
                                existing["extracted_at"] = datetime.now().isoformat()
                                updated_indices.add(i)
                                break
                    continue

                # 일반 신규 fact
                if line not in existing_list and len(new_facts) < USER_MEMORY_MAX_NEW_FACTS:
                    new_facts.append({
                        "content": line,
                        "extracted_at": datetime.now().isoformat(),
                    })

            # 기존 + 신규 병합, 최대 개수 제한
            all_facts = existing_facts.get("facts", []) + new_facts
            all_facts = all_facts[-USER_MEMORY_KEY_FACTS_LIMIT:]  # 최신 N개만 유지

            return json.dumps({"facts": all_facts}, ensure_ascii=False)

        except Exception as e:
            print(f"[UserMemory] Error extracting user facts: {e}")
            return existing_facts_json

    # --------------------------------------------------------
    # 메모리 삭제
    # --------------------------------------------------------
    async def delete_user_memory(self, user_id: str) -> bool:
        """사용자 전역 메모리 삭제"""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_memory WHERE user_id = %s", (user_id,))
            conn.commit()
            print(f"[UserMemory] Deleted memory for user {user_id}")
            return True
        except Exception as e:
            print(f"[UserMemory] Error deleting memory: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


# ============================================================
# 싱글톤 인스턴스 - 사용자 전역 메모리
# ============================================================
_user_memory_instance = None


def get_user_memory_service() -> UserMemoryService:
    """UserMemoryService 싱글톤 인스턴스 반환"""
    global _user_memory_instance
    if _user_memory_instance is None:
        _user_memory_instance = UserMemoryService()
    return _user_memory_instance

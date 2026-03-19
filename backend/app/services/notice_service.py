"""통합 알림 서비스 (공지사항 + 메일 + 전자결재)

페이지 로드 시 모달 알림용 경량 API에 사용됩니다.
- 공지: v_board_search PostgreSQL 뷰
- 메일: v_mail_user_mapping → JSP HTTP 호출
- 결재: v_appr_user_pending / v_appr_dept_received / v_appr_user_referenced 뷰
- 요약: Haiku LLM으로 알림 내용 자연어 요약
"""
import os
import json
import asyncio
import logging
import urllib3
from typing import Optional, List, Dict, Any
from datetime import date

import asyncpg
import httpx

# 내부 서버 SSL 경고 억제
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

TIMS_DATABASE_URL = os.environ.get(
    "TIMS_DATABASE_URL",
    "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"
)

# 공지 대상 게시판
NOTICE_BOARD_NAMES = ["전사게시판", "L&F 게시판"]

# 메일 API 설정
MAIL_API_URL = os.environ.get("MAIL_API_URL", "https://lfon.landf.co.kr/slo/lucid_mail.jsp")
MAIL_API_KEY = os.environ.get("MAIL_API_KEY", "")

EMPTY_SECTION = {"items": [], "count": 0}


def _fix_mojibake(text: str) -> str:
    """JSP QP 디코더 버그로 깨진 한글 복원 (UTF-8 바이트가 Latin-1 char로 저장된 경우)"""
    if not text:
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _safe_date(val) -> str:
    """날짜 값을 ISO 문자열로 안전하게 변환 (이미 str이면 그대로)"""
    if not val:
        return ""
    if isinstance(val, str):
        return val
    try:
        return val.isoformat()
    except AttributeError:
        return str(val)


class NotificationService:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._message_store_cache: Dict[str, str] = {}
        self._login_id_cache: Dict[str, str] = {}
        self._dept_id_cache: Dict[str, int] = {}

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            async def _init_conn(conn):
                await conn.execute("SET DateStyle = 'ISO, YMD'")

            self._pool = await asyncpg.create_pool(
                TIMS_DATABASE_URL,
                min_size=1,
                max_size=5,
                command_timeout=15,
                init=_init_conn
            )
            logger.info("Notification DB connection pool created")
        return self._pool

    # ── 공지사항 ──────────────────────────────────────────────

    async def get_today_notices(self) -> Dict[str, Any]:
        """최근 공지사항 조회 (JHC 제외, 최근 3건)"""
        pool = await self._get_pool()

        query = """
            SELECT post_id, board_name, post_title, header_name,
                   author_name, author_dept, posted_at, post_url
            FROM v_board_search
            WHERE board_name NOT LIKE '%JHC%'
              AND board_category NOT LIKE 'L&F Plus%'
            ORDER BY posted_at DESC
            LIMIT 3
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query)

        items = [
            {
                "post_id": row["post_id"],
                "board_name": row["board_name"],
                "title": (
                    f'{row["header_name"]} {row["post_title"]}'
                    if row["header_name"]
                    else row["post_title"]
                ),
                "author": row["author_name"],
                "author_dept": row["author_dept"] or "",
                "posted_at": _safe_date(row["posted_at"]),
                "post_url": (row["post_url"] or "").replace("/posts/", "/post/"),
            }
            for row in rows
        ]
        return {"items": items, "count": len(items)}

    # ── 읽지 않은 메일 ───────────────────────────────────────

    async def _get_message_store(self, employee_number: str) -> str:
        """사번 → message_store 경로 조회 (캐시)"""
        if employee_number in self._message_store_cache:
            return self._message_store_cache[employee_number]

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT message_store FROM v_mail_user_mapping WHERE employee_number = $1",
                employee_number
            )

        if not row or not row["message_store"]:
            raise ValueError(f"메일 계정을 찾을 수 없습니다 (사번: {employee_number})")

        self._message_store_cache[employee_number] = row["message_store"]
        return row["message_store"]

    async def get_unread_mail(self, employee_number: str) -> Dict[str, Any]:
        """읽지 않은 메일 조회 (JSP HTTP 호출)"""
        message_store = await self._get_message_store(employee_number)

        params = {
            "api_key": MAIL_API_KEY,
            "action": "unread",
            "message_store": message_store,
            "limit": "3",
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            verify=False,
        ) as client:
            response = await client.get(MAIL_API_URL, params=params)
            response.raise_for_status()
            result = json.loads(response.content.decode("utf-8"))

        data = result.get("data", [])
        items = [
            {
                "subject": _fix_mojibake(mail.get("subject", "(제목 없음)")),
                "from": _fix_mojibake(mail.get("from", "")),
                "date": mail.get("date", ""),
            }
            for mail in data[:3]
        ]
        return {"items": items, "count": len(items)}

    # ── 전자결재 ───────────────────────────────────────────────

    async def _get_user_info(self, employee_number: str) -> dict:
        """사번 → login_id, dept_id 조회 (캐시, v_user_info_mapping VIEW 사용)"""
        if employee_number in self._login_id_cache and employee_number in self._dept_id_cache:
            return {
                "login_id": self._login_id_cache[employee_number],
                "dept_id": self._dept_id_cache[employee_number],
            }

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT login_id, dept_id FROM v_user_info_mapping WHERE employee_number = $1",
                employee_number
            )

        if not row:
            raise ValueError(f"사용자를 찾을 수 없습니다 (사번: {employee_number})")

        self._login_id_cache[employee_number] = row["login_id"]
        self._dept_id_cache[employee_number] = row["dept_id"]
        return {"login_id": row["login_id"], "dept_id": row["dept_id"]}

    async def _get_login_id(self, employee_number: str) -> str:
        """사번 → login_id 조회 (캐시)"""
        if employee_number in self._login_id_cache:
            return self._login_id_cache[employee_number]
        info = await self._get_user_info(employee_number)
        return info["login_id"]

    async def _get_dept_id(self, employee_number: str) -> int:
        """사번 → dept_id 조회 (캐시)"""
        if employee_number in self._dept_id_cache:
            return self._dept_id_cache[employee_number]
        info = await self._get_user_info(employee_number)
        return info["dept_id"]

    # _get_dept_id에서 더 이상 직접 쿼리하지 않음 (위의 _get_user_info 사용)

    async def get_pending_approvals(self, employee_number: str) -> Dict[str, Any]:
        """전자결재 미결 문서 조회"""
        login_id = await self._get_login_id(employee_number)

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM v_appr_user_pending WHERE login_id = $1",
                login_id
            )
            total_count = count_row["cnt"] if count_row else 0

            rows = await conn.fetch(
                """
                SELECT doc_id, title, form_name, drafted_at, drafter_name
                FROM v_appr_user_pending
                WHERE login_id = $1
                ORDER BY drafted_at DESC
                LIMIT 3
                """,
                login_id
            )

        items = [
            {
                "doc_id": row["doc_id"],
                "title": row["title"] or "",
                "form_name": row["form_name"] or "",
                "drafted_at": _safe_date(row["drafted_at"]),
                "drafter_name": row["drafter_name"] or "",
            }
            for row in rows
        ]
        return {"items": items, "count": total_count}

    async def get_received_documents(self, employee_number: str) -> Dict[str, Any]:
        """부서 수신 문서 조회 (접수 대기)"""
        dept_id = await self._get_dept_id(employee_number)

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as cnt FROM v_appr_dept_received
                WHERE dept_id = $1 AND is_assigned = false AND is_reception_returned = false
                  AND appr_status NOT IN ('CANCEL', 'RETURN', 'TEMPSAVE')
                """,
                dept_id
            )
            total_count = count_row["cnt"] if count_row else 0

            rows = await conn.fetch(
                """
                SELECT doc_id, title, form_name, drafter_name, drafter_dept_name, received_at
                FROM v_appr_dept_received
                WHERE dept_id = $1 AND is_assigned = false AND is_reception_returned = false
                  AND appr_status NOT IN ('CANCEL', 'RETURN', 'TEMPSAVE')
                ORDER BY received_at DESC NULLS LAST
                LIMIT 3
                """,
                dept_id
            )

        items = [
            {
                "doc_id": row["doc_id"],
                "title": row["title"] or "",
                "form_name": row["form_name"] or "",
                "drafted_at": _safe_date(row["received_at"]),
                "drafter_name": row["drafter_name"] or "",
                "drafter_dept_name": row["drafter_dept_name"] or "",
            }
            for row in rows
        ]
        return {"items": items, "count": total_count}

    async def get_pending_references(self, employee_number: str) -> Dict[str, Any]:
        """안 읽은 참조 문서 조회"""
        login_id = await self._get_login_id(employee_number)

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as cnt FROM v_appr_user_referenced
                WHERE login_id = $1 AND is_read = false
                """,
                login_id
            )
            total_count = count_row["cnt"] if count_row else 0

            rows = await conn.fetch(
                """
                SELECT doc_id, title, form_name, drafter_name, drafted_at
                FROM v_appr_user_referenced
                WHERE login_id = $1 AND is_read = false
                ORDER BY drafted_at DESC
                LIMIT 3
                """,
                login_id
            )

        items = [
            {
                "doc_id": row["doc_id"],
                "title": row["title"] or "",
                "form_name": row["form_name"] or "",
                "drafted_at": _safe_date(row["drafted_at"]),
                "drafter_name": row["drafter_name"] or "",
            }
            for row in rows
        ]
        return {"items": items, "count": total_count}

    # ── AI 요약 프롬프트 빌드 ────────────────────────────────────

    @staticmethod
    def build_summary_prompt(
        notices: Dict, mail: Dict, approvals: Dict
    ) -> str:
        """알림 데이터로 Haiku 요약 프롬프트 생성 (제목만 사용)"""
        # 공지: 제목만
        notice_texts = [
            f"- {item['title']}"
            for item in notices.get("items", [])
        ]

        # 메일: 제목 + 발신자
        mail_texts = [
            f"- {m['subject']} (발신: {m['from']})"
            for m in mail.get("items", [])
        ]

        # 결재: 서브카테고리별 제목+양식
        appr_texts = {"pending": [], "received": [], "referenced": []}
        labels = {"pending": "결재 미결", "received": "수신문서", "referenced": "참조"}
        for sub_key, label in labels.items():
            for a in approvals.get(sub_key, {}).get("items", []):
                form = f" ({a['form_name']})" if a.get("form_name") else ""
                appr_texts[sub_key].append(f"- {a.get('title', '')}{form}")

        all_appr = []
        for sub_key, label in labels.items():
            if appr_texts[sub_key]:
                all_appr.append(f"  [{label}]")
                all_appr.extend(appr_texts[sub_key])

        return f"""오늘의 알림을 간결하게 요약하세요.

규칙:
- "주요 공지:", "주요 결재:", "주요 메일:" 세 영역으로 나눠 각 1줄씩 요약
- 각 영역은 반드시 줄바꿈으로 구분
- 항목이 없는 영역은 생략
- "~확인 필요", "~안내" 같은 간결체
- 존댓말, 마침표로 끝나는 완결된 문장
- 핵심 키워드만 언급
- 절대 마크다운 서식(**, *, #, - 등) 사용 금지. 순수 텍스트만 작성

예시:
주요 공지: 2월 급여 지급일 안내 및 전시회 참관 안내가 있습니다.
주요 결재: LFON 계정 변경 신청 등 결재 확인이 필요합니다.
주요 메일: 위험성평가 설문 요청 등 메일 확인이 필요합니다.

[공지 {len(notice_texts)}건]
{chr(10).join(notice_texts) if notice_texts else "없음"}

[메일 {len(mail_texts)}건]
{chr(10).join(mail_texts) if mail_texts else "없음"}

[결재]
{chr(10).join(all_appr) if all_appr else "없음"}

요약:"""

    # ── 통합 조회 ─────────────────────────────────────────────

    async def get_all_notifications(self, employee_number: str) -> Dict[str, Any]:
        """5개 섹션 병렬 조회 + AI 요약 (개별 fail-safe)"""
        async def _safe_notices():
            try:
                return await self.get_today_notices()
            except Exception as e:
                logger.error(f"공지사항 조회 실패: {e}")
                return EMPTY_SECTION

        async def _safe_mail():
            try:
                return await self.get_unread_mail(employee_number)
            except Exception as e:
                logger.error(f"메일 조회 실패: {e}")
                return EMPTY_SECTION

        async def _safe_pending():
            try:
                return await self.get_pending_approvals(employee_number)
            except Exception as e:
                logger.error(f"결재 미결 조회 실패: {e}")
                return EMPTY_SECTION

        async def _safe_received():
            try:
                return await self.get_received_documents(employee_number)
            except Exception as e:
                logger.error(f"수신문서 조회 실패: {e}")
                return EMPTY_SECTION

        async def _safe_referenced():
            try:
                return await self.get_pending_references(employee_number)
            except Exception as e:
                logger.error(f"참조문서 조회 실패: {e}")
                return EMPTY_SECTION

        notices, mail, pending, received, referenced = await asyncio.gather(
            _safe_notices(),
            _safe_mail(),
            _safe_pending(),
            _safe_received(),
            _safe_referenced(),
        )

        approvals = {
            "pending": pending,
            "received": received,
            "referenced": referenced,
        }

        return {
            "notices": notices,
            "mail": mail,
            "approvals": approvals,
        }

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service

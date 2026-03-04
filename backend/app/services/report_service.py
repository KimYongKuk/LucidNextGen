# -*- coding: utf-8 -*-
"""Service report dashboard - data query service"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)

INTENT_LABEL = {
    "direct": "일반 대화",
    "web_search": "웹 검색",
    "corp_rag": "사내 문서",
    "user_files": "파일 검색",
    "youtube": "YouTube",
    "url_fetch": "URL 추출",
    "it_support": "IT 지원",
    "acct_support": "회계 지원",
    "visualization": "시각화",
    "ppt_generation": "PPT 생성",
    "xlsx": "엑셀",
    "mail": "메일",
    "approval": "전자결재",
    "board": "게시판",
}

# Reverse map: Korean label → intent DB key
LABEL_TO_INTENT = {v: k for k, v in INTENT_LABEL.items()}
LABEL_TO_INTENT["미분류"] = "unknown"

# 대시보드에서 제외할 사용자 목록 (관리자/테스터)
# 환경변수 REPORT_EXCLUDED_USERS로 쉼표 구분하여 설정 (예: "A2304013,A9999999")
EXCLUDED_USERS = [
    u.strip() for u in os.getenv("REPORT_EXCLUDED_USERS", "A2304013").split(",") if u.strip()
]
_EXCLUDED_USERS_SQL = " AND userId NOT IN ({})".format(
    ",".join(f"'{u}'" for u in EXCLUDED_USERS)
) if EXCLUDED_USERS else ""

# ─── 답변 실패 감지 로직 ───
# 실패 조건:
# 1) metadata에 is_error=true로 기록된 명시적 에러
# 2) 사내지식(corp_rag) / IT지원 / 회계지원 에이전트가 문서를 찾지 못한 경우
#    → 검색 기반 intent에서만 "찾을 수 없" 류 패턴 적용
# 주의: LENGTH < 10, 일반 대화의 "찾을 수 없" 등은 정상 응답이므로 제외

_RAG_INTENTS_SQL = "('corp_rag', 'it_support', 'acct_support', 'user_files')"

# SQL CASE fragment for failure detection
_FAILURE_CASE = f"""
    CASE WHEN (
        JSON_EXTRACT(metadata, '$.is_error') = true
        OR (
            intent IN {_RAG_INTENTS_SQL}
            AND (
                outputLog LIKE '%%찾을 수 없%%'
                OR outputLog LIKE '%%검색 결과가 없%%'
                OR outputLog LIKE '%%관련 정보를 찾지 못%%'
                OR outputLog LIKE '%%관련된 정보가 없%%'
                OR outputLog LIKE '%%관련 자료가 없%%'
                OR outputLog LIKE '%%조회 결과가 없%%'
                OR outputLog LIKE '%%해당하는 내용을 찾%%'
            )
        )
    ) THEN 1 ELSE 0 END
"""

# SQL WHERE fragment for failure rows
_FAILURE_WHERE = f"""
    (JSON_EXTRACT(metadata, '$.is_error') = true
     OR (
         intent IN {_RAG_INTENTS_SQL}
         AND (
             outputLog LIKE '%%찾을 수 없%%'
             OR outputLog LIKE '%%검색 결과가 없%%'
             OR outputLog LIKE '%%관련 정보를 찾지 못%%'
             OR outputLog LIKE '%%관련된 정보가 없%%'
             OR outputLog LIKE '%%관련 자료가 없%%'
             OR outputLog LIKE '%%조회 결과가 없%%'
             OR outputLog LIKE '%%해당하는 내용을 찾%%'
         )
     ))
"""

# Output directories
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
PDF_OUTPUT_DIR = _DATA_DIR / "pdf_output"
PPT_OUTPUT_DIR = _DATA_DIR / "ppt_output"
XLSX_OUTPUT_DIR = _DATA_DIR / "xlsx_output"


def _count_files_in_range(directory: Path, extension: str, date_from: str, date_to: str):
    """Count files in directory by modification time within date range. Returns (total, daily_dict)."""
    if not directory.exists():
        return 0, {}

    from_dt = datetime.strptime(date_from, "%Y-%m-%d")
    to_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    total = 0
    daily = {}
    for f in directory.glob(f"*{extension}"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if from_dt <= mtime <= to_dt:
                total += 1
                day_key = mtime.strftime("%m/%d")
                daily[day_key] = daily.get(day_key, 0) + 1
        except Exception:
            pass
    return total, daily


class ReportService:
    def __init__(self):
        self.db = get_database_connection()

    def get_overview(self, date_from: str, date_to: str) -> dict:
        """사용 현황 KPI + 일별 추이"""
        with self.db.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT session) as total_sessions,
                    COUNT(DISTINCT userId) as active_users
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
            """, (date_from, date_to))
            totals = cursor.fetchone()

            total_msg = totals["total_messages"] or 0
            total_sess = totals["total_sessions"] or 0

            cursor.execute(f"""
                SELECT
                    DATE_FORMAT(createDate, '%%m/%%d') as date,
                    COUNT(*) as messages,
                    COUNT(DISTINCT session) as sessions,
                    COUNT(DISTINCT userId) as users
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
                GROUP BY DATE(createDate)
                ORDER BY DATE(createDate)
            """, (date_from, date_to))
            daily_trend = cursor.fetchall()

        return {
            "total_messages": total_msg,
            "total_sessions": total_sess,
            "active_users": totals["active_users"] or 0,
            "daily_trend": [dict(r) for r in daily_trend],
        }

    def get_intents(self, date_from: str, date_to: str) -> dict:
        """의도 분류 분포"""
        with self.db.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    COALESCE(intent, 'unknown') as intent,
                    COUNT(*) as count
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
                GROUP BY intent
                ORDER BY count DESC
            """, (date_from, date_to))
            rows = cursor.fetchall()

        total = sum(r["count"] for r in rows)
        distribution = []
        for r in rows:
            intent_key = r["intent"]
            distribution.append({
                "name": INTENT_LABEL.get(intent_key, intent_key or "미분류"),
                "intentKey": intent_key,
                "count": r["count"],
                "ratio": round(r["count"] / total * 100, 1) if total > 0 else 0,
            })

        return {"distribution": distribution}

    def get_intent_detail(self, date_from: str, date_to: str, intent_key: str) -> dict:
        """특정 의도의 메시지 상세 리스트"""
        with self.db.get_cursor() as cursor:
            if intent_key == "unknown":
                where_clause = "AND (intent IS NULL OR intent = 'unknown')"
                params = (date_from, date_to)
            else:
                where_clause = "AND intent = %s"
                params = (date_from, date_to, intent_key)

            cursor.execute(f"""
                SELECT
                    DATE_FORMAT(createDate, '%%m/%%d %%H:%%i') as datetime,
                    userId,
                    LEFT(inputLog, 150) as question,
                    LEFT(outputLog, 200) as answer,
                    worker_name,
                    response_time_ms
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  {where_clause}
                  {_EXCLUDED_USERS_SQL}
                ORDER BY createDate DESC
                LIMIT 50
            """, params)
            rows = cursor.fetchall()

        messages = []
        for r in rows:
            messages.append({
                "datetime": r["datetime"],
                "userId": r["userId"],
                "question": r["question"],
                "answer": r["answer"],
                "workerName": r["worker_name"] or "",
                "responseTimeMs": r["response_time_ms"],
            })

        return {"messages": messages, "intentKey": intent_key}

    def get_quality(self, date_from: str, date_to: str) -> dict:
        """답변 품질 - 답변 실패율 + 카테고리별 실패율 + 실패 샘플"""
        with self.db.get_cursor() as cursor:
            # Overall failure count
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_messages,
                    SUM({_FAILURE_CASE}) as fail_count
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
            """, (date_from, date_to))
            totals = cursor.fetchone()

            total_msg = totals["total_messages"] or 0
            fail_count = int(totals["fail_count"] or 0)
            fail_rate = round(fail_count / total_msg * 100, 1) if total_msg > 0 else 0

            # Failure by intent (category)
            cursor.execute(f"""
                SELECT
                    COALESCE(intent, 'unknown') as intent,
                    COUNT(*) as total,
                    SUM({_FAILURE_CASE}) as failures
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
                GROUP BY intent
                ORDER BY failures DESC
            """, (date_from, date_to))
            by_intent_rows = cursor.fetchall()

            fail_by_category = []
            max_fail_rate = 0
            for r in by_intent_rows:
                intent_key = r["intent"]
                cat_total = r["total"] or 0
                cat_fails = int(r["failures"] or 0)
                cat_rate = round(cat_fails / cat_total * 100, 1) if cat_total > 0 else 0
                if cat_rate > max_fail_rate:
                    max_fail_rate = cat_rate
                fail_by_category.append({
                    "category": INTENT_LABEL.get(intent_key, intent_key or "미분류"),
                    "failRate": cat_rate,
                    "failCount": cat_fails,
                    "total": cat_total,
                    "isHighlight": False,
                })
            for item in fail_by_category:
                if item["failRate"] == max_fail_rate and max_fail_rate > 0:
                    item["isHighlight"] = True
                    break

            # Recent failure samples
            cursor.execute(f"""
                SELECT
                    DATE_FORMAT(createDate, '%%m/%%d %%H:%%i') as datetime,
                    userId,
                    LEFT(inputLog, 100) as question,
                    LEFT(outputLog, 150) as answer,
                    COALESCE(intent, 'unknown') as intent,
                    worker_name
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND {_FAILURE_WHERE}
                  {_EXCLUDED_USERS_SQL}
                ORDER BY createDate DESC
                LIMIT 20
            """, (date_from, date_to))
            failure_rows = cursor.fetchall()

            recent_failures = []
            for r in failure_rows:
                intent_key = r["intent"]
                recent_failures.append({
                    "datetime": r["datetime"],
                    "userId": r["userId"],
                    "question": r["question"],
                    "answer": r["answer"] or "",
                    "category": INTENT_LABEL.get(intent_key, intent_key or "미분류"),
                    "workerName": r["worker_name"] or "",
                })

        return {
            "failCount": fail_count,
            "failRate": fail_rate,
            "failByCategory": sorted(fail_by_category, key=lambda x: x["failRate"], reverse=True),
            "recentFailures": recent_failures,
        }

    def get_workspaces(self, date_from: str, date_to: str) -> dict:
        """워크스페이스 활용 현황"""
        with self.db.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT cs.workspace_id) as active_workspaces,
                    COUNT(DISTINCT cs.session_id) as workspace_sessions
                FROM chat_sessions cs
                JOIN chat_log_new cl ON cs.session_id = cl.session
                WHERE cs.workspace_id IS NOT NULL
                  AND cl.createDate >= %s AND cl.createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND cl.userId NOT IN ({",".join(f"'{u}'" for u in EXCLUDED_USERS)})
            """, (date_from, date_to))
            ws_totals = cursor.fetchone()

            cursor.execute("""
                SELECT COUNT(*) as memory_updates
                FROM workspace_memory
                WHERE last_summarized_at >= %s
                  AND last_summarized_at < DATE_ADD(%s, INTERVAL 1 DAY)
            """, (date_from, date_to))
            mem_row = cursor.fetchone()

            # Top workspaces with uuid for document count
            cursor.execute(f"""
                SELECT
                    cs.workspace_id as ws_uuid,
                    COALESCE(w.name, CONCAT('WS-', LEFT(cs.workspace_id, 8))) as name,
                    cs.user_id as user,
                    COUNT(cl.session) as messages,
                    DATE_FORMAT(MAX(cl.createDate), '%%m/%%d') as lastActive
                FROM chat_sessions cs
                JOIN chat_log_new cl ON cs.session_id = cl.session
                LEFT JOIN workspaces w ON cs.workspace_id = w.uuid COLLATE utf8mb4_general_ci
                WHERE cs.workspace_id IS NOT NULL
                  AND cl.createDate >= %s AND cl.createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND cl.userId NOT IN ({",".join(f"'{u}'" for u in EXCLUDED_USERS)})
                GROUP BY cs.workspace_id, w.name, cs.user_id
                ORDER BY messages DESC
                LIMIT 10
            """, (date_from, date_to))
            top_rows = cursor.fetchall()

        # Enrich with document count from ChromaDB
        top_workspaces = []
        for r in top_rows:
            doc_count = self._get_workspace_doc_count(r["ws_uuid"])
            top_workspaces.append({
                "name": r["name"],
                "user": r["user"],
                "messages": r["messages"],
                "documents": doc_count,
                "lastActive": r["lastActive"],
            })

        return {
            "activeWorkspaces": ws_totals["active_workspaces"] or 0,
            "totalSessions": ws_totals["workspace_sessions"] or 0,
            "memoryUpdates": mem_row["memory_updates"] or 0,
            "topWorkspaces": top_workspaces,
        }

    def _get_workspace_doc_count(self, workspace_uuid: str) -> int:
        """ChromaDB에서 워크스페이스의 고유 파일 수 조회"""
        try:
            from app.services.chromadb_service import get_chromadb_service
            chromadb = get_chromadb_service()
            collection_name = f"workspace_{workspace_uuid}"
            collection = chromadb.client.get_collection(
                collection_name,
                embedding_function=chromadb.embedding_function,
            )
            if collection.count() == 0:
                return 0
            records = collection.get(include=["metadatas"])
            file_ids = set()
            for meta in records.get("metadatas", []):
                if meta and meta.get("file_id"):
                    file_ids.add(meta["file_id"])
            return len(file_ids)
        except Exception:
            return 0

    def get_artifacts(self, date_from: str, date_to: str) -> dict:
        """파일 & 생성물 현황 - 디렉토리 스캔 + DB 기반"""
        # 1. Generated files from output directories
        pdf_count, pdf_daily = _count_files_in_range(PDF_OUTPUT_DIR, ".pdf", date_from, date_to)
        ppt_count, ppt_daily = _count_files_in_range(PPT_OUTPUT_DIR, ".pptx", date_from, date_to)
        xlsx_count, xlsx_daily = _count_files_in_range(XLSX_OUTPUT_DIR, ".xlsx", date_from, date_to)

        # 2. File uploads + image count from chat_log metadata
        with self.db.get_cursor() as cursor:
            # 파일/이미지를 업로드한 세션 수 (메시지 수가 아닌 세션 단위)
            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT CASE WHEN intent IN ('user_files', 'xlsx') THEN session END) as file_upload_sessions,
                    COUNT(DISTINCT CASE WHEN JSON_EXTRACT(metadata, '$.image_count') > 0 THEN session END) as image_upload_sessions
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
            """, (date_from, date_to))
            row = cursor.fetchone()

        # 3. Merge daily trends
        all_dates = sorted(set(list(pdf_daily.keys()) + list(ppt_daily.keys()) + list(xlsx_daily.keys())))
        daily_trend = []
        for d in all_dates:
            daily_trend.append({
                "date": d,
                "pdf": pdf_daily.get(d, 0),
                "xlsx": xlsx_daily.get(d, 0),
                "ppt": ppt_daily.get(d, 0),
            })

        return {
            "fileUploads": int(row["file_upload_sessions"] or 0),
            "imageUploads": int(row["image_upload_sessions"] or 0),
            "pdfCount": pdf_count,
            "xlsxCount": xlsx_count,
            "pptCount": ppt_count,
            "dailyTrend": daily_trend,
        }

    def get_performance(self, date_from: str, date_to: str) -> dict:
        """응답 성능 현황"""
        with self.db.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT response_time_ms
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND response_time_ms IS NOT NULL
                  {_EXCLUDED_USERS_SQL}
                ORDER BY response_time_ms
            """, (date_from, date_to))
            all_times = [r["response_time_ms"] for r in cursor.fetchall()]

            avg_ms = round(sum(all_times) / len(all_times)) if all_times else 0
            p95_ms = all_times[int(len(all_times) * 0.95)] if len(all_times) >= 2 else avg_ms

            cursor.execute(f"""
                SELECT
                    worker_name as worker,
                    ROUND(AVG(response_time_ms)) as avg_ms,
                    COUNT(*) as count
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND response_time_ms IS NOT NULL
                  AND worker_name IS NOT NULL
                  {_EXCLUDED_USERS_SQL}
                GROUP BY worker_name
                ORDER BY avg_ms DESC
            """, (date_from, date_to))
            worker_rows = cursor.fetchall()

            by_worker = []
            for wr in worker_rows:
                worker_name = wr["worker"]
                cursor.execute(f"""
                    SELECT response_time_ms
                    FROM chat_log_new
                    WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                      AND response_time_ms IS NOT NULL
                      AND worker_name = %s
                      {_EXCLUDED_USERS_SQL}
                    ORDER BY response_time_ms
                """, (date_from, date_to, worker_name))
                w_times = [r["response_time_ms"] for r in cursor.fetchall()]
                w_p95 = w_times[int(len(w_times) * 0.95)] if len(w_times) >= 2 else (w_times[0] if w_times else 0)
                by_worker.append({
                    "worker": worker_name,
                    "avgMs": int(wr["avg_ms"] or 0),
                    "p95Ms": w_p95,
                    "count": wr["count"],
                })

            cursor.execute(f"""
                SELECT
                    DATE_FORMAT(createDate, '%%m/%%d') as date,
                    ROUND(AVG(response_time_ms)) as avg_ms
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND response_time_ms IS NOT NULL
                  {_EXCLUDED_USERS_SQL}
                GROUP BY DATE(createDate)
                ORDER BY DATE(createDate)
            """, (date_from, date_to))
            daily_rows = cursor.fetchall()

            daily_trend = []
            for dr in daily_rows:
                day_date = dr["date"]
                cursor.execute(f"""
                    SELECT response_time_ms
                    FROM chat_log_new
                    WHERE DATE_FORMAT(createDate, '%%m/%%d') = %s
                      AND createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                      AND response_time_ms IS NOT NULL
                      {_EXCLUDED_USERS_SQL}
                    ORDER BY response_time_ms
                """, (day_date, date_from, date_to))
                day_times = [r["response_time_ms"] for r in cursor.fetchall()]
                day_p95 = day_times[int(len(day_times) * 0.95)] if len(day_times) >= 2 else (day_times[0] if day_times else 0)
                daily_trend.append({
                    "date": day_date,
                    "avgResponse": round(int(dr["avg_ms"] or 0) / 1000, 1),
                    "p95Response": round(day_p95 / 1000, 1),
                })

        return {
            "avgResponseMs": avg_ms,
            "p95ResponseMs": p95_ms,
            "byWorker": by_worker,
            "dailyTrend": daily_trend,
        }

    def get_user_ranking(self, date_from: str, date_to: str) -> dict:
        """사용자 랭킹 - 메시지 수 기준 상위 사용자"""
        with self.db.get_cursor() as cursor:
            # KPI totals
            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT userId) as total_users,
                    COUNT(*) as total_messages
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
            """, (date_from, date_to))
            totals = cursor.fetchone()

            # Top 30 users by message count
            cursor.execute(f"""
                SELECT
                    userId,
                    COUNT(*) as message_count,
                    COUNT(DISTINCT session) as session_count,
                    DATE_FORMAT(MAX(createDate), '%%m/%%d %%H:%%i') as last_active,
                    ROUND(AVG(response_time_ms)) as avg_response_ms
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                {_EXCLUDED_USERS_SQL}
                GROUP BY userId
                ORDER BY message_count DESC
                LIMIT 30
            """, (date_from, date_to))
            user_rows = cursor.fetchall()

            # Per-user favorite intent (unknown 제외, 없으면 fallback)
            ranking = []
            for idx, r in enumerate(user_rows):
                user_id = r["userId"]
                cursor.execute(f"""
                    SELECT COALESCE(intent, 'unknown') as intent, COUNT(*) as cnt
                    FROM chat_log_new
                    WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                      AND userId = %s
                      AND intent IS NOT NULL AND intent != 'unknown'
                    GROUP BY intent
                    ORDER BY cnt DESC
                    LIMIT 1
                """, (date_from, date_to, user_id))
                fav_row = cursor.fetchone()
                fav_key = fav_row["intent"] if fav_row else "unknown"

                ranking.append({
                    "rank": idx + 1,
                    "userId": user_id,
                    "messageCount": r["message_count"],
                    "sessionCount": r["session_count"],
                    "lastActive": r["last_active"],
                    "avgResponseMs": int(r["avg_response_ms"] or 0),
                    "favoriteIntent": INTENT_LABEL.get(fav_key, fav_key or "미분류"),
                })

        return {
            "totalUsers": totals["total_users"] or 0,
            "totalMessages": totals["total_messages"] or 0,
            "ranking": ranking,
        }

    def get_user_detail(self, date_from: str, date_to: str, user_id: str) -> dict:
        """특정 사용자의 메시지 상세 리스트"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    DATE_FORMAT(createDate, '%%m/%%d %%H:%%i') as datetime,
                    LEFT(inputLog, 150) as question,
                    LEFT(outputLog, 200) as answer,
                    COALESCE(intent, 'unknown') as intent,
                    worker_name,
                    response_time_ms
                FROM chat_log_new
                WHERE createDate >= %s AND createDate < DATE_ADD(%s, INTERVAL 1 DAY)
                  AND userId = %s
                ORDER BY createDate DESC
                LIMIT 50
            """, (date_from, date_to, user_id))
            rows = cursor.fetchall()

        messages = []
        for r in rows:
            intent_key = r["intent"]
            messages.append({
                "datetime": r["datetime"],
                "question": r["question"],
                "answer": r["answer"],
                "intent": INTENT_LABEL.get(intent_key, intent_key or "미분류"),
                "workerName": r["worker_name"] or "",
                "responseTimeMs": r["response_time_ms"],
            })

        return {"messages": messages, "userId": user_id}


_report_service: Optional[ReportService] = None


def get_report_service() -> ReportService:
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service

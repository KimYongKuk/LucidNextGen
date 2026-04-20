# -*- coding: utf-8 -*-
"""
관리자용 보안 관리 API (2026-04-20)

엔드포인트:
- GET  /v1/admin/security/events            - 이벤트 목록
- GET  /v1/admin/security/events/{id}       - 이벤트 상세
- GET  /v1/admin/security/blocks            - 차단 사용자 목록
- DELETE /v1/admin/security/blocks/{user_id} - 차단 해제
- GET  /v1/admin/security/stats             - 집계 통계
- POST /v1/admin/security/dry-run           - 판정 테스트
- GET  /v1/admin/security/llm-usage         - 오늘의 LLM 사용량
"""
import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Query, Body, HTTPException
from pydantic import BaseModel

from app.core.database import get_database_connection
from app.services.security_guard_service import get_security_guard_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/security", tags=["admin-security"])


# ────────────────────────────────────────────────────────
# 모델
# ────────────────────────────────────────────────────────
class UnblockRequest(BaseModel):
    admin_id: str
    reason: str = "관리자 수동 해제"


class DryRunRequest(BaseModel):
    message: str


# ────────────────────────────────────────────────────────
# 이벤트 목록
# ────────────────────────────────────────────────────────
@router.get("/events")
def list_events(
    user_id: Optional[str] = Query(None),
    threat_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    min_severity: Optional[int] = Query(None, ge=0, le=100),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    db = get_database_connection()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        try:
            where = []
            params = []

            if user_id:
                where.append("user_id = %s")
                params.append(user_id)
            if threat_type:
                where.append("threat_type = %s")
                params.append(threat_type)
            if action:
                where.append("action_taken = %s")
                params.append(action)
            if min_severity is not None:
                where.append("severity >= %s")
                params.append(min_severity)
            if date_from:
                where.append("created_at >= %s")
                params.append(f"{date_from} 00:00:00")
            if date_to:
                where.append("created_at <= %s")
                params.append(f"{date_to} 23:59:59")

            where_sql = f"WHERE {' AND '.join(where)}" if where else ""

            # 전체 카운트
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM user_security_events {where_sql}", params)
            total = int(cursor.fetchone()["cnt"])

            # 목록
            cursor.execute(f"""
                SELECT id, user_id, session_id, workspace_id,
                       threat_type, severity, action_taken, detection_layer,
                       LEFT(user_message, 200) AS user_message_snippet,
                       LEFT(reason, 300) AS reason_snippet,
                       created_at
                FROM user_security_events
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (*params, limit, offset))
            rows = cursor.fetchall()

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "events": [
                    {**r, "created_at": r["created_at"].isoformat() if r.get("created_at") else None}
                    for r in rows
                ],
            }
        finally:
            cursor.close()
    finally:
        conn.close()


@router.get("/events/{event_id}")
def get_event(event_id: int):
    db = get_database_connection()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM user_security_events WHERE id = %s
            """, (event_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Event not found")
            row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else None
            return row
        finally:
            cursor.close()
    finally:
        conn.close()


# ────────────────────────────────────────────────────────
# 차단 관리
# ────────────────────────────────────────────────────────
@router.get("/blocks")
def list_blocks(
    include_unblocked: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
):
    db = get_database_connection()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        try:
            if include_unblocked:
                cursor.execute("""
                    SELECT * FROM user_blocks
                    ORDER BY blocked_at DESC
                    LIMIT %s
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT * FROM user_blocks
                    WHERE unblocked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY blocked_at DESC
                    LIMIT %s
                """, (limit,))
            rows = cursor.fetchall()
            return {
                "blocks": [
                    {
                        **r,
                        "blocked_at": r["blocked_at"].isoformat() if r.get("blocked_at") else None,
                        "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
                        "unblocked_at": r["unblocked_at"].isoformat() if r.get("unblocked_at") else None,
                    }
                    for r in rows
                ]
            }
        finally:
            cursor.close()
    finally:
        conn.close()


@router.delete("/blocks/{user_id}")
async def unblock_user(user_id: str, body: UnblockRequest = Body(...)):
    guard = get_security_guard_service()
    success = await guard.unblock(user_id=user_id, admin_id=body.admin_id, reason=body.reason)
    if not success:
        raise HTTPException(status_code=500, detail="Unblock failed")
    return {"success": True, "user_id": user_id, "unblocked_by": body.admin_id}


# ────────────────────────────────────────────────────────
# 집계 통계 (대시보드용)
# ────────────────────────────────────────────────────────
@router.get("/stats")
def get_stats(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
):
    db = get_database_connection()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        try:
            df = f"{date_from} 00:00:00"
            dt = f"{date_to} 23:59:59"

            # 전체 카운트
            cursor.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN action_taken='WARNED' THEN 1 ELSE 0 END) AS warned,
                       SUM(CASE WHEN action_taken='BLOCKED_REQUEST' THEN 1 ELSE 0 END) AS blocked_req,
                       SUM(CASE WHEN action_taken='TEMP_BLOCKED' THEN 1 ELSE 0 END) AS temp_blocked,
                       SUM(CASE WHEN action_taken='PERM_BLOCKED' THEN 1 ELSE 0 END) AS perm_blocked
                FROM user_security_events
                WHERE created_at BETWEEN %s AND %s
            """, (df, dt))
            summary = cursor.fetchone() or {}
            for k, v in list(summary.items()):
                summary[k] = int(v) if v is not None else 0

            # 위협 타입별
            cursor.execute("""
                SELECT threat_type, COUNT(*) AS cnt
                FROM user_security_events
                WHERE created_at BETWEEN %s AND %s
                GROUP BY threat_type
                ORDER BY cnt DESC
            """, (df, dt))
            by_threat = [{"threat_type": r["threat_type"], "count": int(r["cnt"])} for r in cursor.fetchall()]

            # 일별 추이
            cursor.execute("""
                SELECT DATE(created_at) AS day, COUNT(*) AS cnt
                FROM user_security_events
                WHERE created_at BETWEEN %s AND %s
                GROUP BY DATE(created_at)
                ORDER BY day
            """, (df, dt))
            daily = [{"day": r["day"].isoformat(), "count": int(r["cnt"])} for r in cursor.fetchall()]

            # 상위 위반 사용자
            cursor.execute("""
                SELECT user_id, COUNT(*) AS cnt, MAX(severity) AS max_severity
                FROM user_security_events
                WHERE created_at BETWEEN %s AND %s
                GROUP BY user_id
                ORDER BY cnt DESC
                LIMIT 10
            """, (df, dt))
            top_users = [
                {"user_id": r["user_id"], "count": int(r["cnt"]), "max_severity": int(r["max_severity"])}
                for r in cursor.fetchall()
            ]

            # 현재 차단 사용자 수
            cursor.execute("""
                SELECT COUNT(*) AS cnt FROM user_blocks
                WHERE unblocked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
            """)
            active_blocks = int(cursor.fetchone()["cnt"])

            return {
                "summary": summary,
                "by_threat_type": by_threat,
                "daily": daily,
                "top_users": top_users,
                "active_blocks": active_blocks,
            }
        finally:
            cursor.close()
    finally:
        conn.close()


# ────────────────────────────────────────────────────────
# Dry-run 판정 테스트
# ────────────────────────────────────────────────────────
@router.post("/dry-run")
async def dry_run(body: DryRunRequest):
    """
    임의 메시지에 대한 판정 결과만 반환 (실제 차단 없음).
    패턴 튜닝 용도.
    """
    from app.services.security_guard_service import (
        SecurityGuardService, RULE_PATTERNS, ThreatType
    )
    svc = get_security_guard_service()
    rule_result = svc._rule_check(body.message)

    llm_result = None
    try:
        from app.agents.security_guard_agent import get_security_guard_agent
        agent = get_security_guard_agent()
        if agent.can_call_today():
            llm_result = await agent.classify(body.message)
    except Exception as e:
        llm_result = {"error": str(e)}

    return {
        "rule": {
            "suspicion_score": rule_result.suspicion_score,
            "threat_type": rule_result.threat_type.value if rule_result.threat_type else None,
            "matched_patterns": rule_result.matched_patterns,
        },
        "llm": llm_result,
    }


# ────────────────────────────────────────────────────────
# LLM 일일 사용량
# ────────────────────────────────────────────────────────
@router.get("/llm-usage")
def get_llm_usage():
    import os
    daily_limit = int(os.getenv("SECURITY_LLM_DAILY_LIMIT", "1000"))
    today = date.today().isoformat()

    db = get_database_connection()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT call_count FROM security_llm_daily_usage WHERE usage_date = %s",
                (today,)
            )
            row = cursor.fetchone()
            count = int(row["call_count"]) if row else 0

            # 최근 7일
            cursor.execute("""
                SELECT usage_date, call_count
                FROM security_llm_daily_usage
                WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY usage_date DESC
            """)
            recent = [
                {"date": r["usage_date"].isoformat(), "count": int(r["call_count"])}
                for r in cursor.fetchall()
            ]

            return {
                "today": {
                    "date": today,
                    "count": count,
                    "limit": daily_limit,
                    "remaining": max(0, daily_limit - count),
                    "pct": round(count / daily_limit * 100, 1) if daily_limit else 0,
                },
                "recent_7days": recent,
            }
        finally:
            cursor.close()
    finally:
        conn.close()

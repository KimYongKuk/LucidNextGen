# -*- coding: utf-8 -*-
"""
주간 리포트 관리자
- PDF 생성 → 이메일 발송 오케스트레이션
- 수신자/설정/이력 DB CRUD (MySQL)
- 이메일 본문 HTML 렌더링
"""
import json
import logging
from datetime import datetime
from typing import Optional

from app.core.database import get_database_connection
from app.services.email_service import get_email_service
from app.services.report_pdf_service import get_report_pdf_service
from app.services.report_service import get_report_service

logger = logging.getLogger(__name__)


class WeeklyReportManager:
    """주간 리포트 설정 관리 + 발송 오케스트레이션"""

    def __init__(self):
        self.db = get_database_connection()

    # ─── 발송 오케스트레이션 ───

    def send_weekly_report(self, date_from: str, date_to: str) -> dict:
        """
        주간 리포트 PDF 생성 → 이메일 발송 → 이력 저장

        Returns:
            {"success": bool, "message": str, "pdf_path": str, ...}
        """
        recipients = self.get_recipients()
        if not recipients:
            logger.warning("[WeeklyReport] No active recipients")
            return {"success": False, "message": "수신자가 없습니다"}

        # 1. PDF 생성
        try:
            pdf_service = get_report_pdf_service()
            pdf_path = pdf_service.generate(date_from, date_to)
        except Exception as e:
            logger.error(f"[WeeklyReport] PDF generation failed: {e}")
            self._save_history(date_from, date_to, recipients, None, "failed", str(e))
            return {"success": False, "message": f"PDF 생성 실패: {e}"}

        # 2. 이메일 본문 생성
        try:
            report_service = get_report_service()
            overview = report_service.get_overview(date_from, date_to)
            quality = report_service.get_quality(date_from, date_to)
            perf = report_service.get_performance(date_from, date_to)
        except Exception:
            overview = {"total_messages": 0, "total_sessions": 0, "active_users": 0}
            quality = {"failRate": 0, "failCount": 0}
            perf = {"avgResponseMs": 0}

        html_body = self._render_summary_html(date_from, date_to, overview, quality, perf)
        subject = f"[Lucid AI] 주간 서비스 리포트 ({date_from} ~ {date_to})"

        # 3. 이메일 발송
        email_service = get_email_service()
        to_list = [r["email"] for r in recipients]
        result = email_service.send_with_file(
            to=to_list,
            subject=subject,
            html_body=html_body,
            file_paths=[pdf_path],
            from_name="Lucid AI Weekly Report",
        )

        # 4. 이력 저장
        import os
        pdf_filename = os.path.basename(pdf_path)
        status = "success" if result["success"] else "failed"
        if result.get("sent_count", 0) > 0 and result["sent_count"] < len(to_list):
            status = "partial"

        self._save_history(date_from, date_to, recipients, pdf_filename, status,
                           result.get("message", ""))

        logger.info(f"[WeeklyReport] {status}: {result['message']}")
        return {
            "success": result["success"],
            "message": result["message"],
            "pdf_path": pdf_path,
            "sent_count": result.get("sent_count", 0),
            "total_recipients": len(to_list),
        }

    # ─── 설정 관리 ───

    def get_config(self) -> dict:
        """현재 설정 조회 (스케줄, 활성화, 수신자 포함)"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM report_email_config LIMIT 1")
            config = cursor.fetchone()

        if not config:
            return {
                "enabled": False,
                "send_day": "mon",
                "send_hour": 9,
                "recipients": [],
            }

        recipients = self.get_recipients()
        return {
            "enabled": bool(config["enabled"]),
            "send_day": config["send_day"],
            "send_hour": config["send_hour"],
            "recipients": recipients,
        }

    def update_config(self, enabled: bool = None, send_day: str = None, send_hour: int = None) -> dict:
        """설정 업데이트"""
        updates = []
        params = []
        if enabled is not None:
            updates.append("enabled = %s")
            params.append(enabled)
        if send_day is not None:
            valid_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            if send_day not in valid_days:
                return {"success": False, "message": f"Invalid day: {send_day}"}
            updates.append("send_day = %s")
            params.append(send_day)
        if send_hour is not None:
            if not (0 <= send_hour <= 23):
                return {"success": False, "message": f"Invalid hour: {send_hour}"}
            updates.append("send_hour = %s")
            params.append(send_hour)

        if not updates:
            return {"success": False, "message": "No updates provided"}

        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE report_email_config SET {', '.join(updates)} WHERE id = 1",
                params
            )

        return {"success": True, "message": "설정이 업데이트되었습니다"}

    # ─── 수신자 관리 ───

    def get_recipients(self) -> list:
        """활성 수신자 목록 조회"""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, email, name, active FROM report_email_recipients WHERE active = TRUE ORDER BY id"
            )
            return [dict(r) for r in cursor.fetchall()]

    def add_recipient(self, email: str, name: str = None) -> dict:
        """수신자 추가"""
        if not email or "@" not in email:
            return {"success": False, "message": "유효하지 않은 이메일입니다"}

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO report_email_recipients (email, name) VALUES (%s, %s)",
                    (email.strip(), (name or "").strip() or None)
                )
            return {"success": True, "message": f"수신자 추가: {email}"}
        except Exception as e:
            if "Duplicate" in str(e):
                return {"success": False, "message": "이미 등록된 이메일입니다"}
            raise

    def remove_recipient(self, email: str) -> dict:
        """수신자 삭제"""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM report_email_recipients WHERE email = %s",
                (email,)
            )
            if cursor.rowcount == 0:
                return {"success": False, "message": "해당 이메일을 찾을 수 없습니다"}
        return {"success": True, "message": f"수신자 삭제: {email}"}

    # ─── 이력 ───

    def get_history(self, limit: int = 20) -> list:
        """발송 이력 조회"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, sent_at, date_from, date_to, recipient_count,
                       pdf_filename, status, error_message
                FROM report_email_history
                ORDER BY sent_at DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()

        history = []
        for r in rows:
            history.append({
                "id": r["id"],
                "sentAt": r["sent_at"].strftime("%m/%d %H:%M") if r["sent_at"] else "",
                "dateFrom": str(r["date_from"]),
                "dateTo": str(r["date_to"]),
                "recipientCount": r["recipient_count"],
                "pdfFilename": r["pdf_filename"],
                "status": r["status"],
                "errorMessage": r["error_message"],
            })
        return history

    def _save_history(self, date_from, date_to, recipients, pdf_filename, status, error_msg=""):
        """발송 이력 저장"""
        try:
            recipients_snapshot = [{"email": r["email"], "name": r.get("name", "")} for r in recipients]
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO report_email_history
                    (date_from, date_to, recipient_count, recipients_json, pdf_filename, status, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    date_from, date_to, len(recipients),
                    json.dumps(recipients_snapshot, ensure_ascii=False),
                    pdf_filename, status, error_msg or None,
                ))
        except Exception as e:
            logger.error(f"[WeeklyReport] Failed to save history: {e}")

    # ─── 이메일 본문 ───

    def _render_summary_html(self, date_from, date_to, overview, quality, perf) -> str:
        """간결한 HTML 이메일 본문 (KPI 요약 + 대시보드 링크)"""
        avg_sec = perf.get("avgResponseMs", 0) / 1000
        dashboard_url = "https://your-domain.com/admin/report"

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background-color:#f8fafc; font-family:'맑은 고딕','Malgun Gothic',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc;">
<tr><td align="center" style="padding:40px 20px;">

<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

<!-- Header -->
<tr>
<td style="background:linear-gradient(135deg,#1e293b,#0f172a); padding:30px 40px; text-align:center;">
    <h1 style="margin:0; color:#f3f4f6; font-size:22px; font-weight:700; letter-spacing:1px;">LUCID AI</h1>
    <p style="margin:6px 0 0; color:#94a3b8; font-size:13px;">Weekly Service Report</p>
    <p style="margin:4px 0 0; color:#64748b; font-size:12px;">{date_from} ~ {date_to}</p>
</td>
</tr>

<!-- Summary -->
<tr>
<td style="padding:30px 40px;">
    <p style="margin:0 0 20px; color:#334155; font-size:14px; line-height:1.6;">
        안녕하세요, 지난 주 Lucid AI 서비스 현황을 알려드립니다.
    </p>

    <!-- KPI Cards -->
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td width="33%" style="padding:0 6px 12px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f9ff; border-radius:8px; border-top:3px solid #3b82f6;">
            <tr><td style="padding:16px;">
                <p style="margin:0; color:#64748b; font-size:11px; text-transform:uppercase;">총 메시지</p>
                <p style="margin:4px 0 0; color:#1e293b; font-size:24px; font-weight:700;">{overview['total_messages']:,}</p>
            </td></tr>
            </table>
        </td>
        <td width="33%" style="padding:0 3px 12px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4; border-radius:8px; border-top:3px solid #10b981;">
            <tr><td style="padding:16px;">
                <p style="margin:0; color:#64748b; font-size:11px; text-transform:uppercase;">활성 사용자</p>
                <p style="margin:4px 0 0; color:#1e293b; font-size:24px; font-weight:700;">{overview['active_users']:,}</p>
            </td></tr>
            </table>
        </td>
        <td width="33%" style="padding:0 0 12px 6px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fef2f2; border-radius:8px; border-top:3px solid #ef4444;">
            <tr><td style="padding:16px;">
                <p style="margin:0; color:#64748b; font-size:11px; text-transform:uppercase;">실패율</p>
                <p style="margin:4px 0 0; color:#1e293b; font-size:24px; font-weight:700;">{quality['failRate']}%</p>
            </td></tr>
            </table>
        </td>
    </tr>
    </table>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px;">
    <tr>
        <td width="50%" style="padding:0 6px 0 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#faf5ff; border-radius:8px; border-top:3px solid #8b5cf6;">
            <tr><td style="padding:16px;">
                <p style="margin:0; color:#64748b; font-size:11px; text-transform:uppercase;">평균 응답 시간</p>
                <p style="margin:4px 0 0; color:#1e293b; font-size:24px; font-weight:700;">{avg_sec:.1f}초</p>
            </td></tr>
            </table>
        </td>
        <td width="50%" style="padding:0 0 0 6px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdfa; border-radius:8px; border-top:3px solid #06b6d4;">
            <tr><td style="padding:16px;">
                <p style="margin:0; color:#64748b; font-size:11px; text-transform:uppercase;">총 세션</p>
                <p style="margin:4px 0 0; color:#1e293b; font-size:24px; font-weight:700;">{overview['total_sessions']:,}</p>
            </td></tr>
            </table>
        </td>
    </tr>
    </table>

    <!-- CTA -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
    <tr>
        <td style="background:#f1f5f9; border-radius:8px; padding:16px 20px;">
            <p style="margin:0; color:#475569; font-size:13px; line-height:1.6;">
                자세한 내용은 <strong>첨부된 PDF 리포트</strong>를 확인해주세요.<br>
                실시간 데이터는 <a href="{dashboard_url}" style="color:#3b82f6; text-decoration:none; font-weight:600;">대시보드</a>에서 확인할 수 있습니다.
            </p>
        </td>
    </tr>
    </table>
</td>
</tr>

<!-- Footer -->
<tr>
<td style="background:#f8fafc; border-top:1px solid #e2e8f0; padding:20px 40px; text-align:center;">
    <p style="margin:0; color:#94a3b8; font-size:11px;">
        Lucid AI Service &middot; L&F Corporation<br>
        이 메일은 자동 발송되었습니다
    </p>
</td>
</tr>

</table>
</td></tr></table>
</body>
</html>"""


# ─── 싱글턴 ───
_weekly_report_manager: Optional[WeeklyReportManager] = None


def get_weekly_report_manager() -> WeeklyReportManager:
    global _weekly_report_manager
    if _weekly_report_manager is None:
        _weekly_report_manager = WeeklyReportManager()
    return _weekly_report_manager

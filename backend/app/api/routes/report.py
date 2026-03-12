# -*- coding: utf-8 -*-
"""Service report dashboard API endpoints"""
import os
from datetime import date, timedelta

from fastapi import APIRouter, Query, Body
from fastapi.responses import FileResponse

from app.services.report_service import get_report_service
from app.services.weekly_report_service import get_weekly_report_manager
from app.services.report_pdf_service import REPORT_OUTPUT_DIR
from app.services.email_service import get_email_service

router = APIRouter(prefix="/v1/admin/report", tags=["report"])


@router.get("/overview")
def report_overview(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_overview(date_from, date_to)


@router.get("/intents")
def report_intents(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_intents(date_from, date_to)


@router.get("/intents/detail")
def report_intent_detail(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    intent_key: str = Query(..., description="Intent key (e.g. 'direct', 'corp_rag', 'unknown')"),
):
    return get_report_service().get_intent_detail(date_from, date_to, intent_key)


@router.get("/quality")
def report_quality(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_quality(date_from, date_to)


@router.get("/workspaces")
def report_workspaces(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_workspaces(date_from, date_to)


@router.get("/workspaces/detail")
def report_workspace_detail(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    workspace_id: str = Query(..., description="Workspace UUID"),
    tab: str = Query("messages", description="Tab: messages or documents"),
):
    return get_report_service().get_workspace_detail(date_from, date_to, workspace_id, tab)


@router.get("/artifacts")
def report_artifacts(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_artifacts(date_from, date_to)


@router.get("/performance")
def report_performance(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_performance(date_from, date_to)


@router.get("/token-usage")
def report_token_usage(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_token_usage(date_from, date_to)


@router.get("/users")
def report_users(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
):
    return get_report_service().get_user_ranking(date_from, date_to)


@router.get("/users/detail")
def report_user_detail(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    user_id: str = Query(..., description="User ID (e.g. 'A2304013')"),
):
    return get_report_service().get_user_detail(date_from, date_to, user_id)


# ─── 주간 리포트 이메일 관리 API ───


@router.get("/email/config")
def email_config_get():
    """이메일 설정 조회 (수신자, 스케줄, 활성화)"""
    manager = get_weekly_report_manager()
    config = manager.get_config()
    # SMTP 연결 상태도 포함
    smtp_status = get_email_service().test_connection()
    config["smtpConnected"] = smtp_status["success"]
    return config


@router.put("/email/config")
def email_config_update(
    enabled: bool = Body(None),
    send_day: str = Body(None),
    send_hour: int = Body(None),
):
    """이메일 설정 업데이트 (스케줄, 활성화)"""
    manager = get_weekly_report_manager()
    result = manager.update_config(enabled=enabled, send_day=send_day, send_hour=send_hour)

    # 스케줄 변경 시 스케줄러 재설정
    if result["success"] and (send_day is not None or send_hour is not None):
        try:
            from app.utils.report_email_scheduler import report_email_scheduler
            config = manager.get_config()
            report_email_scheduler.reschedule(config["send_day"], config["send_hour"])
        except Exception:
            pass  # 스케줄러 미시작 상태에서는 무시

    return result


@router.post("/email/recipients")
def email_recipient_add(
    email: str = Body(...),
    name: str = Body(None),
):
    """수신자 추가"""
    return get_weekly_report_manager().add_recipient(email, name)


@router.delete("/email/recipients")
def email_recipient_remove(
    email: str = Query(..., description="삭제할 이메일 주소"),
):
    """수신자 삭제"""
    return get_weekly_report_manager().remove_recipient(email)


@router.post("/email/preview")
def email_preview():
    """PDF 미리보기 생성 → 다운로드 URL 반환"""
    date_to = date.today().strftime("%Y-%m-%d")
    date_from = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    from app.services.report_pdf_service import get_report_pdf_service
    pdf_path = get_report_pdf_service().generate(date_from, date_to)
    filename = os.path.basename(pdf_path)

    return {
        "success": True,
        "filename": filename,
        "downloadUrl": f"/api/v1/admin/report/email/download/{filename}",
    }


@router.get("/email/download/{filename}")
def email_download(filename: str):
    """생성된 PDF 다운로드"""
    file_path = REPORT_OUTPUT_DIR / filename
    if not file_path.exists():
        return {"success": False, "message": "파일을 찾을 수 없습니다"}
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/pdf",
    )


@router.post("/email/send-now")
def email_send_now():
    """즉시 발송"""
    date_to = date.today().strftime("%Y-%m-%d")
    date_from = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    manager = get_weekly_report_manager()
    return manager.send_weekly_report(date_from, date_to)


@router.get("/email/history")
def email_history(
    limit: int = Query(20, description="조회 건수"),
):
    """발송 이력 조회"""
    return get_weekly_report_manager().get_history(limit)


@router.post("/email/test-smtp")
def email_test_smtp():
    """SMTP 연결 테스트"""
    return get_email_service().test_connection()


# ─── 일일 개발 요약 API ───


@router.post("/nightly-summary/run-now")
async def nightly_summary_run_now(
    target_date: str = Query(None, description="대상 날짜 YYYY-MM-DD (미지정 시 오늘)"),
):
    """일일 개발 요약 즉시 실행 (테스트/디버깅용)"""
    from app.utils.nightly_summary_scheduler import nightly_summary_scheduler
    return await nightly_summary_scheduler.run_now(target_date)

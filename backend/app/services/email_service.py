# -*- coding: utf-8 -*-
"""
범용 이메일 발송 서비스
- SMTP 기반 이메일 발송 인프라
- 프로젝트 전체에서 재사용 가능하도록 설계
- 향후 장애 알림, 공지 발송 등에서도 사용

사용 예시:
    from app.services.email_service import get_email_service

    email_service = get_email_service()
    result = email_service.send(
        to="admin@landf.co.kr",
        subject="[알림] 테스트",
        html_body="<h1>테스트</h1>"
    )
"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EmailService:
    """범용 SMTP 이메일 발송 서비스"""

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "")
        self.from_name = os.getenv("SMTP_FROM_NAME", "Lucid AI")

        if self.host:
            logger.info(f"[EmailService] Initialized: {self.host}:{self.port}, TLS={self.use_tls}")
        else:
            logger.warning("[EmailService] SMTP_HOST not configured")

    def is_configured(self) -> bool:
        """SMTP 설정이 완료되었는지 확인"""
        return bool(self.host and self.from_email)

    def send(
        self,
        to: str | list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
        from_name: str | None = None,
    ) -> dict:
        """
        이메일 발송

        Args:
            to: 수신자 이메일 (단일 또는 리스트)
            subject: 제목
            html_body: HTML 본문
            text_body: 텍스트 본문 (없으면 HTML만)
            attachments: [(filename, data_bytes, mime_type), ...] 첨부파일
            from_name: 발신자 이름 (기본: self.from_name)

        Returns:
            {"success": bool, "message": str, "sent_count": int}
        """
        if not self.is_configured():
            return {"success": False, "message": "SMTP not configured", "sent_count": 0}

        recipients = [to] if isinstance(to, str) else list(to)
        if not recipients:
            return {"success": False, "message": "No recipients", "sent_count": 0}

        sender_name = from_name or self.from_name

        try:
            msg = self._build_message(
                recipients=recipients,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachments=attachments,
                sender_name=sender_name,
            )

            sent_count = self._send_smtp(recipients, msg)

            logger.info(f"[EmailService] Sent '{subject}' to {sent_count}/{len(recipients)} recipients")
            return {
                "success": True,
                "message": f"Sent to {sent_count} recipients",
                "sent_count": sent_count,
            }

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[EmailService] SMTP auth failed: {e}")
            return {"success": False, "message": f"SMTP authentication failed: {e}", "sent_count": 0}
        except smtplib.SMTPException as e:
            logger.error(f"[EmailService] SMTP error: {e}")
            return {"success": False, "message": f"SMTP error: {e}", "sent_count": 0}
        except Exception as e:
            logger.error(f"[EmailService] Unexpected error: {e}")
            return {"success": False, "message": f"Error: {e}", "sent_count": 0}

    def send_with_file(
        self,
        to: str | list[str],
        subject: str,
        html_body: str,
        file_paths: list[str],
        text_body: str | None = None,
        from_name: str | None = None,
    ) -> dict:
        """
        파일 경로 기반 첨부 이메일 발송

        Args:
            to: 수신자
            subject: 제목
            html_body: HTML 본문
            file_paths: 첨부할 파일 경로 리스트
            text_body: 텍스트 본문
            from_name: 발신자 이름
        """
        attachments = []
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                logger.warning(f"[EmailService] Attachment not found: {fp}")
                continue
            data = path.read_bytes()
            # MIME type 추론
            ext = path.suffix.lower()
            mime_map = {
                ".pdf": "application/pdf",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".zip": "application/zip",
            }
            mime_type = mime_map.get(ext, "application/octet-stream")
            attachments.append((path.name, data, mime_type))

        return self.send(
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            from_name=from_name,
        )

    def _build_message(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str | None,
        attachments: list[tuple[str, bytes, str]] | None,
        sender_name: str,
    ) -> MIMEMultipart:
        """MIME 메시지 생성"""
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((sender_name, self.from_email))
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # 본문 (alternative: text + html)
        body_part = MIMEMultipart("alternative")
        if text_body:
            body_part.attach(MIMEText(text_body, "plain", "utf-8"))
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_part)

        # 첨부파일
        if attachments:
            for filename, data, mime_type in attachments:
                maintype, subtype = mime_type.split("/", 1)
                attachment = MIMEApplication(data, _subtype=subtype)
                attachment.add_header(
                    "Content-Disposition", "attachment", filename=filename
                )
                msg.attach(attachment)

        return msg

    def _send_smtp(self, recipients: list[str], msg: MIMEMultipart) -> int:
        """SMTP로 실제 발송, 성공한 수신자 수 반환"""
        server = smtplib.SMTP(self.host, self.port, timeout=30)
        try:
            server.ehlo()
            if self.use_tls:
                server.starttls()
                server.ehlo()
            if self.username and self.password:
                server.login(self.username, self.password)

            refused = server.sendmail(self.from_email, recipients, msg.as_string())
            sent_count = len(recipients) - len(refused)
            if refused:
                logger.warning(f"[EmailService] Refused recipients: {refused}")
            return sent_count
        finally:
            try:
                server.quit()
            except Exception:
                pass

    def test_connection(self) -> dict:
        """SMTP 연결 테스트"""
        if not self.is_configured():
            return {"success": False, "message": "SMTP not configured"}
        try:
            server = smtplib.SMTP(self.host, self.port, timeout=10)
            server.ehlo()
            if self.use_tls:
                server.starttls()
                server.ehlo()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.quit()
            return {"success": True, "message": f"Connected to {self.host}:{self.port}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# ─── 싱글턴 ───
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """EmailService 싱글턴 반환"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service

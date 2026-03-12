"""AWS Bedrock 리전 폴백 관리자

us-east-1 (cross-region) 쓰로틀링 시 us-west-2 (on-demand)로 자동 전환.
다음 날 자정(UTC)에 자동 복구 — AWS 일일 토큰 한도 리셋 시점.
(UTC 00:00 = KST 09:00)
"""

import os
import time
import threading
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# cross-region prefix → on-demand prefix 변환 매핑
_CROSS_REGION_PREFIXES = ("us.", "eu.", "apac.", "global.")

# KST
_KST = timezone(timedelta(hours=9))


def _next_midnight_utc() -> float:
    """다음 날 자정(UTC)의 Unix timestamp 반환 — AWS 일일 한도 리셋 시점"""
    now_utc = datetime.now(timezone.utc)
    tomorrow = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow.timestamp()


def _send_fallback_notification(event: str, primary: str, fallback: str, restore_at: str = ""):
    """리전 전환/복구 시 관리자에게 메일 발송 (별도 스레드)"""
    admin_email = os.getenv("ADMIN_ALERT_EMAIL", "")
    if not admin_email:
        logger.info("[REGION_FALLBACK] ADMIN_ALERT_EMAIL not set, skipping notification")
        return

    def _send():
        try:
            from app.services.email_service import get_email_service
            email_svc = get_email_service()
            if not email_svc.is_configured():
                return

            now_kst = datetime.now(_KST).strftime("%Y-%m-%d %H:%M KST")

            if event == "activated":
                subject = "[Lucid AI] Bedrock 리전 폴백 활성화"
                html_body = f"""
                <div style="font-family: 'Malgun Gothic', sans-serif; padding: 20px;">
                    <h2 style="color: #e74c3c;">Bedrock 리전 폴백 활성화</h2>
                    <table style="border-collapse: collapse; margin: 16px 0;">
                        <tr><td style="padding: 8px; font-weight: bold;">발생 시각</td>
                            <td style="padding: 8px;">{now_kst}</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">전환</td>
                            <td style="padding: 8px;">{primary} → {fallback}</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">원인</td>
                            <td style="padding: 8px;">일일 토큰 한도 쓰로틀링 (모든 모델/리트라이 소진)</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">복구 예정</td>
                            <td style="padding: 8px;">{restore_at}</td></tr>
                    </table>
                    <p style="color: #666;">이후 요청은 {fallback} 리전의 on-demand 모델을 사용합니다.</p>
                </div>
                """
            else:  # restored
                subject = "[Lucid AI] Bedrock 리전 복구 완료"
                html_body = f"""
                <div style="font-family: 'Malgun Gothic', sans-serif; padding: 20px;">
                    <h2 style="color: #27ae60;">Bedrock 리전 복구 완료</h2>
                    <table style="border-collapse: collapse; margin: 16px 0;">
                        <tr><td style="padding: 8px; font-weight: bold;">복구 시각</td>
                            <td style="padding: 8px;">{now_kst}</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">복구</td>
                            <td style="padding: 8px;">{fallback} → {primary}</td></tr>
                        <tr><td style="padding: 8px; font-weight: bold;">상태</td>
                            <td style="padding: 8px;">일일 한도 리셋, cross-region 모델 정상 사용</td></tr>
                    </table>
                </div>
                """

            email_svc.send(
                to=admin_email,
                subject=subject,
                html_body=html_body,
                from_name="Lucid AI Alert",
            )
            logger.info(f"[REGION_FALLBACK] Notification sent to {admin_email}: {event}")
        except Exception as e:
            logger.error(f"[REGION_FALLBACK] Failed to send notification: {e}")

    # 메일 발송은 별도 스레드 (메인 요청 지연 방지)
    threading.Thread(target=_send, daemon=True).start()


class RegionFallbackManager:
    """쓰로틀링 감지 시 리전 전환을 관리하는 싱글톤"""

    def __init__(self):
        self._primary_region = os.getenv("AWS_REGION", "us-east-1")
        self._fallback_region = os.getenv("AWS_FALLBACK_REGION", "us-west-2")
        self._using_fallback = False
        self._restore_at: float = 0  # 복구 예정 시각 (Unix timestamp)
        self._lock = threading.Lock()

    @property
    def primary_region(self) -> str:
        return self._primary_region

    @property
    def fallback_region(self) -> str:
        return self._fallback_region

    @property
    def is_fallback_active(self) -> bool:
        """현재 폴백 리전 사용 중인지 확인. 자정 지나면 자동 복구."""
        if not self._using_fallback:
            return False

        # 복구 시각 경과 시 자동 복구
        if time.time() >= self._restore_at:
            with self._lock:
                if self._using_fallback and time.time() >= self._restore_at:
                    self._using_fallback = False
                    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                    print(f"[REGION_FALLBACK] Daily quota reset ({now_utc}), "
                          f"restored to primary: {self._primary_region}")
                    _send_fallback_notification(
                        "restored", self._primary_region, self._fallback_region)
                    return False
        return self._using_fallback

    @property
    def current_region(self) -> str:
        """현재 사용해야 할 리전"""
        return self._fallback_region if self.is_fallback_active else self._primary_region

    def activate_fallback(self):
        """폴백 리전으로 전환 — 다음 날 자정(UTC, KST 09:00)까지 유지"""
        with self._lock:
            if not self._using_fallback:
                self._using_fallback = True
                self._restore_at = _next_midnight_utc()
                restore_utc = datetime.fromtimestamp(self._restore_at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                restore_kst = datetime.fromtimestamp(self._restore_at, _KST).strftime("%Y-%m-%d %H:%M KST")
                print(f"[REGION_FALLBACK] Activated! "
                      f"{self._primary_region} → {self._fallback_region} "
                      f"(restore at {restore_utc} / {restore_kst})")
                _send_fallback_notification(
                    "activated", self._primary_region, self._fallback_region,
                    restore_at=f"{restore_utc} ({restore_kst})")

    def reset_to_primary(self):
        """수동으로 primary 리전으로 복귀"""
        with self._lock:
            if self._using_fallback:
                self._using_fallback = False
                print(f"[REGION_FALLBACK] Manually reset to primary: {self._primary_region}")
                _send_fallback_notification(
                    "restored", self._primary_region, self._fallback_region)

    def convert_model_id_for_fallback(self, model_id: str) -> str:
        """cross-region model ID를 on-demand(리전 직접 호출)용으로 변환

        예: us.anthropic.claude-sonnet-4-6 → anthropic.claude-sonnet-4-6
        """
        for prefix in _CROSS_REGION_PREFIXES:
            if model_id.startswith(prefix):
                return model_id[len(prefix):]
        return model_id

    def get_model_id(self, original_model_id: str) -> str:
        """현재 리전 상태에 따라 적절한 model ID 반환"""
        if self.is_fallback_active:
            return self.convert_model_id_for_fallback(original_model_id)
        return original_model_id


# 싱글톤
_manager: RegionFallbackManager | None = None


def get_region_fallback_manager() -> RegionFallbackManager:
    global _manager
    if _manager is None:
        _manager = RegionFallbackManager()
    return _manager

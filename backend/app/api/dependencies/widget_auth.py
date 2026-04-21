"""그룹웨어 위젯용 암호화 토큰 인증 Dependency.

그룹웨어 JSP(custom_index_header.jsp)에서 생성한 AES 암호화 토큰을 검증한다.
토큰 평문 포맷: "{empNo}|{timestamp_ms}"
- empNo: 사번
- timestamp_ms: Java System.currentTimeMillis() — 밀리초 단위 Unix epoch

토큰은 발급 후 `WIDGET_TOKEN_VALID_SECONDS` 이내에만 유효 (replay 방지).

JSP 측 Java 코드와 `backend/app/utils/crypto.py`의 AES ECB + PKCS7 방식 100% 호환:
- Java: Cipher.getInstance("AES/ECB/PKCS5Padding")  # PKCS5 = PKCS7 (AES 블록사이즈 동일)
- Python: AES.new(key, AES.MODE_ECB) + unpad

환경변수:
- WIDGET_SHARED_KEY: JSP와 동일한 AES 키 (16자 AES-128 또는 32자 AES-256)
- WIDGET_TOKEN_VALID_SECONDS: 토큰 유효시간 (기본 300초 = 5분)
"""

import os
import time
import logging
from typing import Optional

from fastapi import Header, HTTPException, status

from app.utils.crypto import decrypt_empno

logger = logging.getLogger(__name__)

WIDGET_SHARED_KEY = os.getenv("WIDGET_SHARED_KEY", "")
WIDGET_TOKEN_VALID_SECONDS = int(os.getenv("WIDGET_TOKEN_VALID_SECONDS", "300"))


async def get_current_user_widget(
    x_widget_auth: Optional[str] = Header(None),
) -> dict:
    """위젯 암호화 토큰 검증 후 인증된 사번 반환.

    Raises:
        HTTPException(401): 토큰 없음 / 복호화 실패 / 포맷 오류 / 만료
        HTTPException(500): WIDGET_SHARED_KEY 미설정
    """
    if not WIDGET_SHARED_KEY:
        logger.error("[WIDGET_AUTH] WIDGET_SHARED_KEY is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Widget auth not configured on server",
        )

    if not x_widget_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Widget auth token required",
        )

    # 복호화 (기존 decrypt_empno 유틸 재사용 — 평문이 "empNo|ts" 포맷)
    try:
        payload = decrypt_empno(x_widget_auth, WIDGET_SHARED_KEY)
    except Exception as e:
        logger.warning(f"[WIDGET_AUTH] Token decrypt failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid widget token",
        )

    # 포맷 검증: "empNo|timestamp_ms"
    if "|" not in payload:
        logger.warning(f"[WIDGET_AUTH] Invalid payload format (no delimiter)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid widget token payload",
        )

    parts = payload.split("|", 1)
    empno = parts[0].strip()
    ts_str = parts[1].strip()

    if not empno:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty empno in widget token",
        )

    try:
        ts_ms = int(ts_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid timestamp in widget token",
        )

    # 타임스탬프 검증 (replay 방지 + 과도한 시계 오차 허용 범위)
    now_ms = int(time.time() * 1000)
    age_seconds = abs(now_ms - ts_ms) / 1000
    if age_seconds > WIDGET_TOKEN_VALID_SECONDS:
        logger.warning(
            f"[WIDGET_AUTH] Token expired: empno={empno}, age={age_seconds:.0f}s"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Widget token expired (age={int(age_seconds)}s)",
        )

    return {
        "empno": empno,
        "name": "",  # 위젯은 별도 이름 정보 없음
        "source": "widget",
    }

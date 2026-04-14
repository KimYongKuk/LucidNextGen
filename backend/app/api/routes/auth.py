"""인증 관련 API 라우터"""
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import jwt
import bcrypt
import asyncpg

from app.utils.crypto import decrypt_empno
from app.core.database import get_database_connection
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)
router = APIRouter()

# JWT 설정
SECRET_KEY = os.getenv("SECRET_KEY", "landf01234567890_fastapi_secret_key_change_in_production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24시간


# ── Request/Response 모델 ──

class DecryptRequest(BaseModel):
    encrypted_empno: str

class DecryptResponse(BaseModel):
    decrypted_empno: str

class LoginRequest(BaseModel):
    login_id: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    empno: str
    login_id: str
    name: str
    token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class RegisterRequest(BaseModel):
    empno: str
    login_id: str
    name: str
    password: str

class RequestSetupRequest(BaseModel):
    email: str

class SetupPasswordRequest(BaseModel):
    token: str
    password: str


# ── 헬퍼 함수 ──

def _hash_password(password: str) -> str:
    """비밀번호 bcrypt 해시"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """비밀번호 검증"""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(empno: str, name: str) -> str:
    """JWT 토큰 생성"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "empno": empno,
        "name": name,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _get_user_by_login_id(login_id: str) -> dict | None:
    """login_id로 사용자 조회"""
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT empno, login_id, name, password_hash, is_active FROM users WHERE login_id = %s",
            (login_id,)
        )
        return cursor.fetchone()


def _get_user_by_empno(empno: str) -> dict | None:
    """사번으로 사용자 조회"""
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT empno, login_id, name, password_hash, is_active FROM users WHERE empno = %s",
            (empno,)
        )
        return cursor.fetchone()


# ── 기존 SSO 엔드포인트 ──

@router.post("/auth/decrypt", response_model=DecryptResponse)
async def decrypt_empno_endpoint(request: DecryptRequest):
    """암호화된 사번 복호화"""
    try:
        aes_key = os.getenv("AES_KEY", "landf01234567890")

        # 특수 케이스: empty 처리
        if request.encrypted_empno == 'bvGTT8WkCqWnKkAs4IFN3w==':
            return DecryptResponse(decrypted_empno='empty')

        # 복호화
        decrypted = decrypt_empno(request.encrypted_empno, aes_key)
        return DecryptResponse(decrypted_empno=decrypted)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"복호화 실패: {str(e)}")


# ── 그룹웨어 user_id → 사번 변환 ──

@router.get("/auth/resolve-gw-user/{gw_user_id}")
async def resolve_gw_user(gw_user_id: str):
    """다우오피스 내부 go_users.id(숫자) → 사번 변환"""
    tims_url = os.getenv("TIMS_DATABASE_URL", "")
    if not tims_url:
        raise HTTPException(status_code=500, detail="TIMS DB 미설정")

    try:
        conn = await asyncpg.connect(tims_url)
        try:
            # go_users.id → login_id 조회, 그 뒤 v_user_info_mapping에서 사번 조회
            row = await conn.fetchrow(
                """
                SELECT m.employee_number, u.login_id, m.name
                FROM go_users u
                JOIN v_user_info_mapping m ON u.login_id = m.login_id
                WHERE u.id = $1
                LIMIT 1
                """,
                int(gw_user_id),
            )
        finally:
            await conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

        return {
            "empno": row["employee_number"],
            "login_id": row["login_id"],
            "name": row["name"],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 user_id 형식")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GW user resolve failed: {e}")
        raise HTTPException(status_code=500, detail="사용자 조회 실패")


# ── 자체 인증 엔드포인트 ──

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """자체 로그인 (ID + 비밀번호)"""
    user = _get_user_by_login_id(request.login_id)

    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다. 관리자에게 문의하세요.")

    if not _verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    token = _create_token(user["empno"], user["name"])

    logger.info(f"[AUTH] Login success: {user['empno']} ({user['name']})")
    return LoginResponse(
        success=True,
        empno=user["empno"],
        login_id=user["login_id"],
        name=user["name"],
        token=token,
    )


@router.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, empno: str = ""):
    """비밀번호 변경 (로그인된 사용자)"""
    if not empno:
        raise HTTPException(status_code=400, detail="사번이 필요합니다.")

    user = _get_user_by_empno(empno)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if not _verify_password(request.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")

    new_hash = _hash_password(request.new_password)
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE empno = %s",
            (new_hash, empno)
        )

    logger.info(f"[AUTH] Password changed: {empno}")
    return {"success": True, "message": "비밀번호가 변경되었습니다."}


@router.post("/auth/register")
async def register(request: RegisterRequest):
    """사용자 등록 (관리자용)"""
    # 중복 체크
    if _get_user_by_empno(request.empno):
        raise HTTPException(status_code=409, detail=f"이미 등록된 사번입니다: {request.empno}")
    if _get_user_by_login_id(request.login_id):
        raise HTTPException(status_code=409, detail=f"이미 등록된 로그인 ID입니다: {request.login_id}")

    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")

    password_hash = _hash_password(request.password)
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (empno, login_id, name, password_hash) VALUES (%s, %s, %s, %s)",
            (request.empno, request.login_id, request.name, password_hash)
        )

    logger.info(f"[AUTH] User registered: {request.empno} ({request.name})")
    return {"success": True, "message": f"사용자 등록 완료: {request.empno}"}


@router.post("/auth/verify-token")
async def verify_token(token: str = ""):
    """JWT 토큰 검증 (미들웨어용)"""
    if not token:
        raise HTTPException(status_code=401, detail="토큰이 필요합니다.")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "valid": True,
            "empno": payload["empno"],
            "name": payload.get("name", ""),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


# ── 셀프 비밀번호 설정 (초대 토큰) ──

TIMS_DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "")
SETUP_TOKEN_EXPIRE_HOURS = 24
SITE_URL = os.getenv("SITE_URL", "https://lucidai.landf.co.kr")


async def _lookup_employee_by_email(email: str) -> dict | None:
    """TIMS DB에서 이메일(login_id)로 사원 정보 조회"""
    if not TIMS_DATABASE_URL:
        return None

    # email에서 login_id 추출: wg0403@landf.co.kr → wg0403
    login_id = email.split("@")[0] if "@" in email else email

    conn = await asyncpg.connect(TIMS_DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT employee_number, name, login_id
            FROM v_user_info_mapping
            WHERE login_id = $1
            LIMIT 1
            """,
            login_id,
        )
        if row:
            return {
                "empno": row["employee_number"],
                "name": row["name"],
                "login_id": row["login_id"],
            }
        return None
    finally:
        await conn.close()


def _create_setup_token(empno: str, login_id: str, name: str, email: str) -> str:
    """1회용 설정 토큰 생성 후 DB 저장"""
    token = uuid.uuid4().hex
    expires_at = datetime.now() + timedelta(hours=SETUP_TOKEN_EXPIRE_HOURS)

    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO setup_tokens (token, empno, login_id, name, email, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (token, empno, login_id, name, email, expires_at)
        )
    return token


def _send_setup_email(email: str, name: str, token: str) -> bool:
    """비밀번호 설정 링크 이메일 발송"""
    setup_url = f"{SITE_URL}/setup?token={token}"

    html_body = f"""
    <div style="font-family: 'Malgun Gothic', sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
        <div style="text-align: center; margin-bottom: 32px;">
            <h2 style="color: #1a1a2e; margin: 0;">Lucid AI</h2>
            <p style="color: #666; font-size: 14px; margin-top: 4px;">사내 AI 어시스턴트</p>
        </div>

        <p style="font-size: 15px; color: #333;">안녕하세요, <strong>{name}</strong>님</p>
        <p style="font-size: 14px; color: #555; line-height: 1.6;">
            Lucid AI 계정 비밀번호를 설정해주세요.<br>
            아래 버튼을 클릭하면 비밀번호 설정 페이지로 이동합니다.
        </p>

        <div style="text-align: center; margin: 32px 0;">
            <a href="{setup_url}"
               style="display: inline-block; padding: 12px 32px; background-color: #1a1a2e; color: #fff;
                      text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 500;">
                비밀번호 설정하기
            </a>
        </div>

        <p style="font-size: 12px; color: #999; line-height: 1.5;">
            이 링크는 {SETUP_TOKEN_EXPIRE_HOURS}시간 동안 유효하며, 1회만 사용 가능합니다.<br>
            본인이 요청하지 않았다면 이 이메일을 무시해주세요.
        </p>
    </div>
    """

    service = get_email_service()
    result = service.send(
        to=email,
        subject="[Lucid AI] 비밀번호 설정 안내",
        html_body=html_body,
        from_name="Lucid AI",
    )
    return result.get("success", False)


@router.post("/auth/request-setup")
async def request_setup(request: RequestSetupRequest):
    """이메일로 비밀번호 설정 링크 발송"""
    email = request.email.strip().lower()

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="올바른 이메일 주소를 입력해주세요.")

    # TIMS DB에서 사원 정보 조회
    employee = await _lookup_employee_by_email(email)
    if not employee:
        raise HTTPException(status_code=404, detail="등록된 임직원 이메일이 아닙니다.")

    # 토큰 생성 및 이메일 발송
    token = _create_setup_token(
        empno=employee["empno"],
        login_id=employee["login_id"],
        name=employee["name"],
        email=email,
    )

    sent = _send_setup_email(email, employee["name"], token)
    if not sent:
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.")

    logger.info(f"[AUTH] Setup email sent: {employee['empno']} ({email})")
    return {"success": True, "message": "비밀번호 설정 링크가 이메일로 발송되었습니다."}


@router.post("/auth/setup-password")
async def setup_password(request: SetupPasswordRequest):
    """토큰으로 비밀번호 설정 (최초 등록)"""
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")

    # 토큰 조회
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM setup_tokens WHERE token = %s AND used = 0 AND expires_at > NOW()",
            (request.token,)
        )
        token_row = cursor.fetchone()

    if not token_row:
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 링크입니다.")

    # 기존 계정 여부에 따라 INSERT or UPDATE
    existing = _get_user_by_empno(token_row["empno"])
    password_hash = _hash_password(request.password)

    with db.get_cursor() as cursor:
        if existing:
            # 비밀번호 재설정
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE empno = %s",
                (password_hash, token_row["empno"])
            )
            logger.info(f"[AUTH] Password reset via setup: {token_row['empno']} ({token_row['name']})")
        else:
            # 신규 계정 생성
            cursor.execute(
                "INSERT INTO users (empno, login_id, name, password_hash) VALUES (%s, %s, %s, %s)",
                (token_row["empno"], token_row["login_id"], token_row["name"], password_hash)
            )
            logger.info(f"[AUTH] Account created via setup: {token_row['empno']} ({token_row['name']})")
        cursor.execute("UPDATE setup_tokens SET used = 1 WHERE token = %s", (request.token,))

    return {"success": True, "message": "비밀번호가 설정되었습니다. 로그인해주세요."}
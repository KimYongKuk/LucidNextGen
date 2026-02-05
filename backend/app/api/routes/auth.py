"""인증 관련 API 라우터"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.crypto import decrypt_empno

router = APIRouter()


class DecryptRequest(BaseModel):
    encrypted_empno: str


class DecryptResponse(BaseModel):
    decrypted_empno: str


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

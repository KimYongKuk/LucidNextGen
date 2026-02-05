"""사번 암호화 테스트 스크립트"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.utils.crypto import encrypt_empno, decrypt_empno

# AES 키
AES_KEY = "landf01234567890"

# 테스트할 사번
empno = "PA2601004"

# 암호화
encrypted = encrypt_empno(empno, AES_KEY)
print(f"원본 사번: {empno}")
print(f"암호화된 값: {encrypted}")
print(f"\nSSO 링크 예시:")
print(f"http://your-sso-server/auth?empno={encrypted}")

# 복호화 테스트 (검증)
decrypted = decrypt_empno(encrypted, AES_KEY)
print(f"\n복호화된 값: {decrypted}")
print(f"검증 결과: {'성공' if decrypted == empno else '실패'}")

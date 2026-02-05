"""AES 암호화/복호화 유틸리티"""
import urllib.parse
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def encrypt_empno(empno: str, key: str) -> str:
    """
    AES ECB 모드로 사번 암호화
    
    Args:
        empno: 사번 (예: PA2601004)
        key: AES 키 (16자리)
    
    Returns:
        URL 인코딩된 Base64 암호화 문자열
    """
    # 사번을 바이트로 변환
    empno_bytes = empno.encode('utf-8')
    
    # PKCS7 패딩
    padded = pad(empno_bytes, AES.block_size)
    
    # AES 암호화 (ECB 모드)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    encrypted_bytes = cipher.encrypt(padded)
    
    # Base64 인코딩
    base64_encoded = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    # URL 인코딩
    url_encoded = urllib.parse.quote(base64_encoded)
    
    return url_encoded


def decrypt_empno(encrypted_empno: str, key: str) -> str:
    """
    AES ECB 모드로 암호화된 사번 복호화

    Args:
        encrypted_empno: URL 인코딩된 Base64 암호화 문자열
        key: AES 키 (16자리)

    Returns:
        복호화된 사번
    """
    # URL 디코딩
    decoded_empno = urllib.parse.unquote(encrypted_empno)

    # Base64 디코딩
    encrypted_bytes = base64.b64decode(decoded_empno)

    # AES 복호화 (ECB 모드)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    decrypted_bytes = cipher.decrypt(encrypted_bytes)

    # PKCS7 언패딩
    unpadded = unpad(decrypted_bytes, AES.block_size)

    # 바이트를 문자열로 변환
    return unpadded.decode('utf-8')

"""OpenAI-compatible API Key 인증 미들웨어"""

import os
from dataclasses import dataclass
from typing import Dict

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class APIKeyInfo:
    key: str
    name: str


def _parse_api_keys() -> Dict[str, str]:
    """OPENAPI_KEYS 환경변수 파싱 → {api_key: service_name}"""
    raw = os.getenv("OPENAPI_KEYS", "")
    if not raw:
        return {}
    result = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        name, key = entry.split(":", 1)
        result[key.strip()] = name.strip()
    return result


# 모듈 로드 시 1회 파싱
_KEY_MAP: Dict[str, str] = _parse_api_keys()


def reload_keys():
    """서버 재시작 없이 키 리로드 (필요 시 호출)"""
    global _KEY_MAP
    _KEY_MAP = _parse_api_keys()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> APIKeyInfo:
    """FastAPI Depends용 — Bearer 토큰 검증 후 APIKeyInfo 반환"""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Missing API key. Include 'Authorization: Bearer sk-xxx' header.",
                    "type": "invalid_request_error",
                    "code": "missing_api_key",
                }
            },
        )

    token = credentials.credentials
    service_name = _KEY_MAP.get(token)
    if service_name is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid API key.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )

    return APIKeyInfo(key=token, name=service_name)

"""AWS Bedrock 모델 체인 및 재시도 설정"""
import os
from dataclasses import dataclass
from typing import List


@dataclass
class ModelConfig:
    """개별 모델 설정"""
    model_id: str
    display_name: str
    max_tokens: int = 8192


def _derive_display_name(model_id: str) -> str:
    """모델 ID에서 display name 자동 추출"""
    # 프리픽스 제거 (us., global., apac., anthropic.)
    name = model_id
    for prefix in ("us.anthropic.", "global.anthropic.", "apac.anthropic.", "anthropic."):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # 버전 접미사 제거 (-v1:0 등)
    import re
    name = re.sub(r'-v\d+:\d+$', '', name)
    # 날짜 제거 (-20250929 등)
    name = re.sub(r'-\d{8}', '', name)
    # claude- 제거, 하이픈→공백, 타이틀 케이스
    name = name.replace("claude-", "Claude ")
    return name


def get_model_chain() -> List[ModelConfig]:
    """
    모델 체인 반환 (Primary -> Fallback 순서)
    환경변수에서 모델 ID를 읽어옴
    """
    primary_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    fallback_id = os.getenv("BEDROCK_FALLBACK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    return [
        ModelConfig(
            model_id=primary_id,
            display_name=_derive_display_name(primary_id),
            max_tokens=32768
        ),
        ModelConfig(
            model_id=fallback_id,
            display_name=_derive_display_name(fallback_id),
            max_tokens=8192
        ),
    ]


# 재시도 설정
RETRY_CONFIG = {
    "max_retries": int(os.getenv("BEDROCK_RETRY_MAX", "3")),
    "initial_delay_ms": int(os.getenv("BEDROCK_RETRY_INITIAL_DELAY_MS", "500")),
    "max_delay_ms": int(os.getenv("BEDROCK_RETRY_MAX_DELAY_MS", "5000")),
    "backoff_multiplier": float(os.getenv("BEDROCK_RETRY_BACKOFF_MULTIPLIER", "2")),
}


# ============================================================================
# A2A (Agent-to-Agent) 아키텍처용 모델 설정
# ============================================================================

def get_orchestrator_config() -> ModelConfig:
    """
    Orchestrator Agent 모델 설정 (Intent 분류, Worker 라우팅)
    빠른 응답이 중요하므로 Haiku 사용 권장
    Global Inference로 최적 리전 자동 선택
    """
    return ModelConfig(
        model_id=os.getenv(
            "ORCHESTRATOR_MODEL_ID",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        ),
        display_name="Orchestrator (Haiku Global)",
        max_tokens=1024  # 라우팅용이므로 작은 토큰 제한
    )


def get_worker_config(use_sonnet: bool = False) -> ModelConfig:
    """
    Worker Agent 모델 설정
    Global Inference로 최적 리전 자동 선택

    Args:
        use_sonnet: True면 복잡한 추론용 Sonnet, False면 기본 Haiku
    """
    if use_sonnet:
        mid = os.getenv("WORKER_SONNET_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
        return ModelConfig(
            model_id=mid,
            display_name=f"Worker ({_derive_display_name(mid)})",
            max_tokens=32768
        )
    mid = os.getenv("WORKER_DEFAULT_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    return ModelConfig(
        model_id=mid,
        display_name=f"Worker ({_derive_display_name(mid)})",
        max_tokens=8192
    )


# A2A 활성화 여부
def is_hierarchical_agent_enabled() -> bool:
    """USE_HIERARCHICAL_AGENT 환경변수 확인"""
    return os.getenv("USE_HIERARCHICAL_AGENT", "false").lower() == "true"

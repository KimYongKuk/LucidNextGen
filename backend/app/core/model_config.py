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


def get_model_chain() -> List[ModelConfig]:
    """
    모델 체인 반환 (Primary -> Fallback 순서)
    환경변수에서 모델 ID를 읽어옴
    """
    return [
        ModelConfig(
            model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            display_name="Claude Sonnet 4.5",
            max_tokens=8192
        ),
        ModelConfig(
            model_id=os.getenv("BEDROCK_FALLBACK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
            display_name="Claude Haiku 4.5",
            max_tokens=4096
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
        return ModelConfig(
            model_id=os.getenv(
                "WORKER_SONNET_MODEL_ID",
                "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
            ),
            display_name="Worker (Sonnet Global)",
            max_tokens=8192
        )
    return ModelConfig(
        model_id=os.getenv(
            "WORKER_DEFAULT_MODEL_ID",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        ),
        display_name="Worker (Haiku Global)",
        max_tokens=4096
    )


# A2A 활성화 여부
def is_hierarchical_agent_enabled() -> bool:
    """USE_HIERARCHICAL_AGENT 환경변수 확인"""
    return os.getenv("USE_HIERARCHICAL_AGENT", "false").lower() == "true"

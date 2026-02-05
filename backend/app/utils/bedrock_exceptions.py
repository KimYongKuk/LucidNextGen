"""AWS Bedrock 쓰로틀링/레이트 리밋 예외 감지 유틸리티"""

# 쓰로틀링으로 간주할 예외 코드/이름 목록
THROTTLING_EXCEPTIONS = [
    "ThrottlingException",
    "RequestLimitExceededException",
    "ServiceUnavailableException",
    "ModelStreamErrorException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "ModelTimeoutException",
]


def is_throttling_error(exception: Exception) -> bool:
    """
    주어진 예외가 쓰로틀링/레이트 리밋 에러인지 확인

    Args:
        exception: 확인할 예외 객체

    Returns:
        True if 쓰로틀링 관련 에러, False otherwise
    """
    # 1. botocore ClientError 체크 (AWS SDK 표준)
    if hasattr(exception, 'response'):
        try:
            error_code = exception.response.get('Error', {}).get('Code', '')
            if error_code in THROTTLING_EXCEPTIONS:
                return True
        except (AttributeError, TypeError):
            pass

    # 2. 예외 타입명 체크
    error_type = type(exception).__name__
    if error_type in THROTTLING_EXCEPTIONS:
        return True

    # 3. 예외 메시지에서 키워드 검색 (폴백)
    error_str = str(exception).lower()
    throttle_keywords = [
        "throttl",           # throttling, throttle, throttled
        "too many request",  # TooManyRequests
        "rate limit",        # rate limited
        "request limit",     # request limit exceeded
        "service unavailable",
        "capacity",          # capacity exceeded
        "retry",             # retry after
    ]

    for keyword in throttle_keywords:
        if keyword in error_str:
            return True

    return False

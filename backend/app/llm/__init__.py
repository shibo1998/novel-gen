"""LLM 异常定义"""


class LLMError(Exception):
    """LLM 基础异常"""

    pass


class LLMTimeoutError(LLMError):
    """LLM API 超时"""

    pass


class LLMRateLimitError(LLMError):
    """LLM API 限流"""

    pass


class LLMQuotaExceededError(LLMError):
    """LLM API 配额超限"""

    pass


class LLMCircuitBreakerError(LLMError):
    """LLM 熔断器开启"""

    pass


class LLMValidationError(LLMError):
    """LLM 请求参数验证失败"""

    pass

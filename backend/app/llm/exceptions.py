"""LLM 相关异常"""


class LLMError(Exception):
    """LLM 基础异常"""
    pass


class LLMTimeoutError(LLMError):
    """LLM 请求超时"""
    pass


class LLMRateLimitError(LLMError):
    """LLM 速率限制"""
    pass


class LLMQuotaExceededError(LLMError):
    """LLM 配额超限"""
    pass


class LLMCircuitBreakerError(LLMError):
    """LLM circuit breaker is open."""
    pass

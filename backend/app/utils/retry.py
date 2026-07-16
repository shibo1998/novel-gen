import asyncio
import logging
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.llm.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def create_llm_retry_decorator(max_retries: int = None):
    """创建 LLM 专用重试装饰器

    Args:
        max_retries: 最大重试次数，默认使用配置值

    Returns:
        装饰器函数
    """
    if max_retries is None:
        from app.config import settings
        max_retries = settings.llm_max_retries

    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((LLMTimeoutError, LLMRateLimitError)),
        before_sleep=lambda retry_state: logger.warning(
            f"LLM call failed, retrying... "
            f"(attempt {retry_state.attempt_number}/{max_retries})"
        )
    )


def with_retry(func: Callable[P, T]) -> Callable[P, T]:
    """带重试的函数装饰器"""
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        decorator = create_llm_retry_decorator()
        retrying_func = decorator(func)
        try:
            return await retrying_func(*args, **kwargs)
        except RetryError as e:
            logger.error(f"LLM call failed after all retries: {e}")
            raise LLMError("LLM call failed after all configured retries") from e
    return wrapper


class RetryContext:
    """可管理的重试上下文"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt = 0

    async def __aenter__(self):
        self.attempt += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type in (LLMTimeoutError, LLMRateLimitError) and self.attempt < self.max_retries:
            delay = min(self.base_delay * (2 ** (self.attempt - 1)), self.max_delay)
            logger.warning(f"Retryable error, waiting {delay}s before retry...")
            await asyncio.sleep(delay)
            return True
        return False

    @property
    def should_retry(self) -> bool:
        return self.attempt < self.max_retries

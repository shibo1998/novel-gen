import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Optional

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI

from app.config import settings
from app.llm.exceptions import (
    LLMCircuitBreakerError,
    LLMError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


async def _retry_stream_before_first_token(factory) -> AsyncIterator[str]:
    """Retry only before output starts; partial streams must be recovered as whole scenes."""
    attempts = max(1, settings.llm_max_retries)
    for attempt in range(attempts):
        emitted = False
        try:
            async for chunk in factory():
                emitted = True
                yield chunk
            return
        except (LLMQuotaExceededError, LLMCircuitBreakerError):
            raise
        except LLMError:
            if emitted or attempt + 1 >= attempts:
                raise
            await asyncio.sleep(min(0.5 * (2**attempt), 4.0))


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    async def complete(
        self,
        prompt: str,
        system: str = "",
        json_schema: dict = None,
        max_tokens: int | None = None,
    ) -> str:
        """兼容旧调用方；底层仍强制使用流式请求并聚合完整文本。"""
        chunks = []
        async for chunk in self.complete_stream(prompt, system=system):
            chunks.append(chunk)
        return "".join(chunks)

    @abstractmethod
    async def complete_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        """流式完成，逐 token 产出"""
        pass


async def collect_stream_text(
    client: LLMClient,
    prompt: str,
    *,
    system: str = "",
) -> str:
    """通过流式 Provider 调用收集完整文本，供非 SSE 的业务流程复用。"""
    chunks = []
    async for chunk in client.complete_stream(prompt, system=system):
        chunks.append(chunk)
    return "".join(chunks)


class CircuitBreaker:
    """熔断器实现"""

    def __init__(self, threshold: int = 5, timeout: float = 60.0):
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.is_open = True
            import time
            self.last_failure_time = time.time()
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_attempt(self) -> bool:
        if not self.is_open:
            return True
        import time
        if self.last_failure_time and (time.time() - self.last_failure_time) > self.timeout:
            self.is_open = False
            self.failure_count = 0
            return True
        return False


class UnifiedOpenAIClient(LLMClient):
    """统一 OpenAI 兼容客户端（支持任意 base URL）"""

    def __init__(self):
        from openai import AsyncOpenAI
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> "AsyncOpenAI":
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url.rstrip("/")
            )
        return self._client

    def _build_messages(self, prompt: str, system: str = "") -> list[dict]:
        """构建消息列表"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def complete_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        async for chunk in _retry_stream_before_first_token(
            lambda: self._complete_stream_once(prompt, system)
        ):
            yield chunk

    async def _complete_stream_once(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        if not _circuit_breaker.can_attempt():
            raise LLMCircuitBreakerError("LLM circuit breaker is open; retry after the recovery timeout")
        try:
            async with asyncio.timeout(settings.llm_timeout_seconds):
                messages = self._build_messages(prompt, system)
                stream = await self.client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    max_tokens=getattr(settings, "llm_max_tokens", 8192),
                    stream=True,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
        except TimeoutError as exc:
            _circuit_breaker.record_failure()
            raise LLMTimeoutError(
                f"LLM API timed out after {settings.llm_timeout_seconds}s"
            ) from exc
        except Exception as exc:
            _circuit_breaker.record_failure()
            if "rate_limit" in str(exc).lower():
                raise LLMRateLimitError(f"Rate limit exceeded: {exc}") from exc
            if "quota" in str(exc).lower():
                raise LLMQuotaExceededError(f"Quota exceeded: {exc}") from exc
            raise LLMError(f"LLM API stream error: {exc}") from exc
        else:
            _circuit_breaker.record_success()


class AnthropicClient(LLMClient):
    """Anthropic Claude 客户端（原生 SDK）"""

    def __init__(self):
        from anthropic import AsyncAnthropic
        self._client: Optional[AsyncAnthropic] = None
        self._api_key = settings.anthropic_api_key or settings.llm_api_key

    @property
    def client(self) -> "AsyncAnthropic":
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        async for chunk in _retry_stream_before_first_token(
            lambda: self._complete_stream_once(prompt, system)
        ):
            yield chunk

    async def _complete_stream_once(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        if not _circuit_breaker.can_attempt():
            raise LLMCircuitBreakerError("LLM circuit breaker is open; retry after the recovery timeout")
        try:
            async with asyncio.timeout(settings.llm_timeout_seconds):
                async with self.client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=4096,
                    system=system or None,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
        except TimeoutError as exc:
            _circuit_breaker.record_failure()
            raise LLMTimeoutError(
                f"LLM API timed out after {settings.llm_timeout_seconds}s"
            ) from exc
        except Exception as exc:
            _circuit_breaker.record_failure()
            if "rate_limit" in str(exc).lower():
                raise LLMRateLimitError(f"Rate limit exceeded: {exc}") from exc
            if "quota" in str(exc).lower():
                raise LLMQuotaExceededError(f"Quota exceeded: {exc}") from exc
            raise LLMError(f"Anthropic API stream error: {exc}") from exc
        else:
            _circuit_breaker.record_success()


# 全局客户端实例
_client_cache: Optional[LLMClient] = None
_circuit_breaker = CircuitBreaker(
    threshold=settings.llm_circuit_breaker_threshold,
    timeout=settings.llm_timeout_seconds
)


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端单例"""
    global _client_cache
    if _client_cache is None:
        provider = settings.llm_provider.lower()
        if provider == "anthropic":
            _client_cache = AnthropicClient()
        else:
            # 默认使用统一的 OpenAI 兼容客户端（支持任意 base URL）
            _client_cache = UnifiedOpenAIClient()
    return _client_cache


def reset_llm_client() -> None:
    """重置 LLM 客户端（用于测试或配置变更后）"""
    global _client_cache
    _client_cache = None

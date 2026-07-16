"""Embedding 客户端 —— 语义召回链路的入口。

走 OpenAI 兼容接口（默认指向本地 Ollama 的 bge-m3，见 settings.embed_*），
把文本转成向量，供 pgvector 索引与语义检索使用。

设计要点：
- 与 LLM 客户端解耦：embedding 用独立的 base_url / api_key / model（embed_* 配置）；
- 批量优先：一次请求可嵌入多段文本，减少往返；
- 维度断言：返回向量维度必须等于 settings.embed_dim，否则说明模型/配置不匹配，
  提前抛错好过写进库后召回时才发现维度对不上；
- 失败可控：带超时与有限重试；调用方（memory 层）负责在失败时降级为"无语义分"，
  不因 embedding 挂掉而阻断正文生成。
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Embedding 调用失败（网络 / 超时 / 维度不匹配等）。"""


class EmbeddingClient:
    """OpenAI 兼容的 embedding 客户端（默认 Ollama bge-m3）。"""

    def __init__(self) -> None:
        self._client: Optional["AsyncOpenAI"] = None

    @property
    def client(self) -> "AsyncOpenAI":
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.embed_api_key or "not-needed",
                base_url=settings.embed_base_url.rstrip("/"),
            )
        return self._client

    async def embed_texts(
        self,
        texts: list[str],
        *,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> list[list[float]]:
        """把多段文本嵌入为向量。

        Args:
            texts: 待嵌入文本列表。空列表直接返回空。
            max_retries: 失败重试次数（指数退避）。
            timeout: 单次请求超时秒数。

        Returns:
            与输入等长、顺序一致的向量列表。

        Raises:
            EmbeddingError: 重试耗尽或返回维度与 embed_dim 不符。
        """
        if not texts:
            return []

        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    self.client.embeddings.create(
                        model=settings.embed_model,
                        input=texts,
                    ),
                    timeout=timeout,
                )
                vectors = [item.embedding for item in response.data]
                self._assert_dims(vectors)
                return vectors
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.warning("embedding timeout (attempt %d/%d)", attempt + 1, max_retries)
            except Exception as exc:  # provider / 网络错误
                last_exc = exc
                logger.warning("embedding failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if attempt + 1 < max_retries:
                await asyncio.sleep(min(0.5 * (2**attempt), 4.0))

        raise EmbeddingError(f"embedding failed after {max_retries} attempts: {last_exc}")

    async def embed_text(self, text: str, **kwargs) -> list[float]:
        """单段文本嵌入的便捷包装。"""
        vectors = await self.embed_texts([text], **kwargs)
        return vectors[0]

    @staticmethod
    def _assert_dims(vectors: list[list[float]]) -> None:
        expected = settings.embed_dim
        for vec in vectors:
            if len(vec) != expected:
                raise EmbeddingError(
                    f"embedding dim mismatch: got {len(vec)}, expected {expected} "
                    f"(检查 embed_model={settings.embed_model} 与 embed_dim 配置是否一致)"
                )


_client_cache: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """获取 embedding 客户端单例。"""
    global _client_cache
    if _client_cache is None:
        _client_cache = EmbeddingClient()
    return _client_cache


def reset_embedding_client() -> None:
    """重置单例（测试或配置变更后）。"""
    global _client_cache
    _client_cache = None

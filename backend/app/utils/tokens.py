"""统一的 token 计数工具。

背景：项目此前在成本/指标核算处用 `len(text) // 4` 估算 token 数。
该经验值针对英文，对中文会低估 4~8 倍（中文在 cl100k/o200k tokenizer 中约
1 汉字 ≈ 1~2 token），导致成本统计严重失真。

本模块提供基于真实 tiktoken 的计数：
- 已知 OpenAI 模型走对应 encoding；
- 未知模型（如 glm / deepseek / bge 等国产或兼容模型）——因主要处理中文，
  优先用 o200k_base（对中文切分优于 cl100k_base），最终回退 cl100k_base。
"""
from __future__ import annotations

from functools import lru_cache

import tiktoken

# 未知模型的默认 encoding：o200k_base 对中文切分更细，成本估算更接近真实
_DEFAULT_ENCODING = "o200k_base"
_FALLBACK_ENCODING = "cl100k_base"


@lru_cache(maxsize=32)
def _get_encoder(model: str | None) -> "tiktoken.Encoding":
    """按模型名解析 encoder，带缓存。

    解析顺序：
      1. tiktoken 能识别的模型名 → 其官方 encoding；
      2. 否则用 o200k_base（中文友好）；
      3. o200k_base 不可用时回退 cl100k_base。
    """
    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
    try:
        return tiktoken.get_encoding(_DEFAULT_ENCODING)
    except Exception:
        return tiktoken.get_encoding(_FALLBACK_ENCODING)


def count_tokens(text: str, model: str | None = None) -> int:
    """返回文本的真实 token 数。

    Args:
        text: 待计数文本。空字符串返回 0。
        model: 模型名，用于选择 encoding；缺省用中文友好的默认 encoding。
    """
    if not text:
        return 0
    return len(_get_encoder(model).encode(text))


def count_tokens_pair(prompt: str, completion: str, model: str | None = None) -> tuple[int, int]:
    """一次算出 prompt / completion 两段的 token 数，便于成本核算调用点复用。

    prompt 至少记 1（与既有 `max(1, ...)` 语义一致，避免 0 除或 0 成本误判）。
    """
    prompt_tokens = max(1, count_tokens(prompt, model))
    completion_tokens = count_tokens(completion, model)
    return prompt_tokens, completion_tokens


def truncate_tokens(
    text: str,
    max_tokens: int,
    model: str | None = None,
    *,
    keep_end: bool = False,
) -> str:
    """Truncate text on tokenizer boundaries, optionally retaining the ending."""
    if not text or max_tokens <= 0:
        return ""
    encoder = _get_encoder(model)
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    selected = tokens[-max_tokens:] if keep_end else tokens[:max_tokens]
    return encoder.decode(selected)

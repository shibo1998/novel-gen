"""Context Budget Manager —— Phase 10
令牌级别的上下文资源分配器。在 ContextBuilder 组装完全部候选内容后，
按优先级 + 配额裁剪，确保关键信息不被"lost in the middle"。
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import tiktoken

from app.services.context_priorities import CONTEXT_PRIORITIES

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Model window sizes
# ------------------------------------------------------------------
_MODEL_WINDOWS = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o-2024-08-06": 128000,
    "claude-3.5-sonnet": 200000,
    "claude-3.5-sonnet-20241022": 200000,
    "deepseek-v3": 128000,
    "deepseek-chat": 128000,
}


def _get_window_size(model: str) -> int:
    return _MODEL_WINDOWS.get(model.lower(), 128000)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------
@dataclass
class ContextSlice:
    """一个上下文片段"""
    category: str
    content: str
    priority: str           # critical / high / medium / low
    token_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.token_count == 0 and self.content:
            enc = tiktoken.get_encoding("cl100k_base")
            self.token_count = len(enc.encode(self.content))


@dataclass
class AllocationReport:
    """分配报告"""
    original_tokens: int
    allocated_tokens: int
    budget: int
    utilization: float
    dropped_categories: list[str]
    compressed_categories: list[str]
    critical_slices: list[str]
    high_slices: list[str]
    medium_slices: list[str]
    low_slices: list[str]

    def to_dict(self) -> dict:
        return {
            "original_tokens": self.original_tokens,
            "allocated_tokens": self.allocated_tokens,
            "budget": self.budget,
            "utilization": f"{self.utilization:.1%}",
            "dropped_categories": self.dropped_categories,
            "compressed_categories": self.compressed_categories,
            "slices_by_priority": {
                "critical": self.critical_slices,
                "high": self.high_slices,
                "medium": self.medium_slices,
                "low": self.low_slices,
            },
        }


# ------------------------------------------------------------------
# Budget Manager
# ------------------------------------------------------------------
class ContextBudgetManager:
    """
    上下文预算管理器。

    工作流程：
        1. 接收所有 ContextSlice（来自 ContextBuilder）
        2. 按优先级分组
        3. critical 全量注入
        4. high/medium 按配额注入，超出时压缩或截断
        5. low 仅在剩余空间充足时注入
        6. 返回裁剪后的切片列表 + 分配报告
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        enc_model = "gpt-4o" if "gpt-4o" in model else model
        try:
            self.encoder = tiktoken.encoding_for_model(enc_model)
        except KeyError:
            self.encoder = tiktoken.get_encoding("cl100k_base")

        self.model_window = _get_window_size(model)
        self.output_reserve = 4096
        self.prompt_overhead = 2000
        self.usable_budget = self.model_window - self.output_reserve - self.prompt_overhead

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def allocate(self, slices: list[ContextSlice], chapter_number: int) -> tuple[list[ContextSlice], AllocationReport]:
        """按优先级和配额分配上下文空间。"""
        groups: dict[str, list[ContextSlice]] = {"critical": [], "high": [], "medium": [], "low": []}
        for s in slices:
            if s.priority in groups:
                groups[s.priority].append(s)
            else:
                groups["low"].append(s)

        allocated: list[ContextSlice] = []
        remaining = self.usable_budget
        compressed: list[str] = []
        dropped: list[str] = []
        by_priority: dict[str, list[str]] = {"critical": [], "high": [], "medium": [], "low": []}

        # Critical → 全量注入
        for s in groups["critical"]:
            if s.content:
                allocated.append(s)
                remaining -= s.token_count
                by_priority["critical"].append(s.category)

        # High → 按配额注入，超出部分压缩
        for s in groups["high"]:
            if not s.content:
                continue
            cfg = CONTEXT_PRIORITIES.get(s.category, {})
            quota = cfg.get("quota", 3000)
            overflow_action = cfg.get("overflow_action", "summarize")

            if s.token_count <= quota and remaining >= s.token_count:
                allocated.append(s)
                remaining -= s.token_count
                by_priority["high"].append(s.category)
            else:
                compressed_s = self._compress(s, min(quota, max(0, remaining)), overflow_action)
                if compressed_s and compressed_s.content:
                    allocated.append(compressed_s)
                    remaining -= compressed_s.token_count
                    compressed.append(s.category)
                    by_priority["high"].append(s.category)
                else:
                    dropped.append(s.category)

        # Medium → 滚动窗口或相关性排序后注入
        for s in groups["medium"]:
            if not s.content:
                continue
            cfg = CONTEXT_PRIORITIES.get(s.category, {})
            strategy = cfg.get("strategy", "rolling_window")
            quota = cfg.get("quota", 4000)

            if strategy == "rolling_window":
                s = self._apply_rolling_window(s, chapter_number)
            elif strategy == "relevance_ranked":
                s = self._apply_relevance_rank(s, chapter_number)

            if s and s.content and remaining >= min(s.token_count, quota):
                if s.token_count > quota:
                    s = self._compress(s, quota, "truncate")
                if s and s.content:
                    allocated.append(s)
                    remaining -= s.token_count
                    by_priority["medium"].append(s.category)
            else:
                dropped.append(s.category)

        # Low → 仅在剩余空间充足时注入
        for s in groups["low"]:
            if not s.content:
                continue
            if remaining >= s.token_count and s.content:
                allocated.append(s)
                remaining -= s.token_count
                by_priority["low"].append(s.category)
            else:
                dropped.append(s.category)

        original_total = sum(s.token_count for s in slices)
        allocated_total = sum(s.token_count for s in allocated)

        report = AllocationReport(
            original_tokens=original_total,
            allocated_tokens=allocated_total,
            budget=self.usable_budget,
            utilization=allocated_total / max(self.usable_budget, 1),
            dropped_categories=dropped,
            compressed_categories=compressed,
            critical_slices=by_priority["critical"],
            high_slices=by_priority["high"],
            medium_slices=by_priority["medium"],
            low_slices=by_priority["low"],
        )
        return allocated, report

    def _compress(self, slice: ContextSlice, max_tokens: int, strategy: str) -> Optional[ContextSlice]:
        """压缩上下文片段到 max_tokens 以内"""
        if not slice.content or max_tokens <= 0:
            return None

        if strategy == "summarize":
            compressed_text = self._summarize_with_llm(slice.content, max_tokens)
        elif strategy == "truncate":
            compressed_text = self._naive_truncate(slice.content, max_tokens)
        elif strategy == "truncate_oldest":
            compressed_text = self._truncate_oldest(slice.content, max_tokens)
        else:
            return None

        return ContextSlice(
            category=slice.category,
            content=compressed_text,
            priority=slice.priority,
            token_count=self.count_tokens(compressed_text),
            metadata={**slice.metadata, "compressed": True, "original_tokens": slice.token_count},
        )

    def _summarize_with_llm(self, text: str, max_tokens: int) -> str:
        """Deterministically truncate summaries within the synchronous allocator."""
        return self._naive_truncate(text, max_tokens)

    def _naive_truncate(self, text: str, max_tokens: int) -> str:
        """简单截断到 max_tokens"""
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoder.decode(tokens[:max_tokens])

    def _truncate_oldest(self, text: str, max_tokens: int) -> str:
        """从最早的条目开始丢弃（适用于列表型内容）。单条目超限时也截断。"""
        entries = text.split("\n---\n")
        while len(entries) > 1 and self.count_tokens("\n---\n".join(entries)) > max_tokens:
            entries.pop(0)
        result = "\n---\n".join(entries)
        # 单条目仍超限时，直接截断
        if self.count_tokens(result) > max_tokens:
            result = self._naive_truncate(result, max_tokens)
        return result

    def _apply_rolling_window(self, slice: ContextSlice, current_chapter: int) -> ContextSlice:
        """
        滚动窗口策略：最近 3 章全量，其余每章 1 句。

        content 预期格式：第X章摘要：...\n---\n第Y章摘要：...
        """
        lines = re.split(r"\n---\n", slice.content)
        kept = []
        for line in lines:
            m = re.search(r"第(\d+)章", line)
            if m:
                ch = int(m.group(1))
                if current_chapter - ch <= 3:
                    kept.append(line.strip())
                else:
                    sents = line.strip().split("。")
                    first = sents[0] + "。" if sents else ""
                    kept.append(first)
            elif line.strip():
                kept.append(line.strip())

        content = "\n---\n".join(kept)
        return ContextSlice(
            category=slice.category,
            content=content,
            priority=slice.priority,
            token_count=self.count_tokens(content),
            metadata={**slice.metadata, "strategy": "rolling_window"},
        )

    def _apply_relevance_rank(self, slice: ContextSlice, current_chapter: int) -> ContextSlice:
        """相关性排序：按条目长度降序，取 Top N（简化实现）"""
        entries = re.split(r"\n\n+", slice.content)
        entries.sort(key=len, reverse=True)
        top = entries[:10]
        content = "\n\n".join(top)
        return ContextSlice(
            category=slice.category,
            content=content,
            priority=slice.priority,
            token_count=self.count_tokens(content),
            metadata={**slice.metadata, "strategy": "relevance_ranked"},
        )


# 全局单例（lazy）
_budget_manager: Optional[ContextBudgetManager] = None


def get_budget_manager(model: str = "gpt-4o-mini") -> ContextBudgetManager:
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = ContextBudgetManager(model=model)
    return _budget_manager


def reset_budget_manager() -> None:
    global _budget_manager
    _budget_manager = None

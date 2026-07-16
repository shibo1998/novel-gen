"""BudgetGuard —— Phase 12
成本预算护栏。在每章生成前检查预算，超限时阻止调用并告警。
"""
import logging
from typing import Optional

from app.config import settings
from app.services.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """预算超限异常"""
    pass


class BudgetGuard:
    """
    预算护栏。

    使用前需要通过 set_collector() 注入 MetricsCollector 实例。
    也可以直接通过构造函数传入。
    """

    def __init__(
        self,
        metrics_collector: Optional[MetricsCollector] = None,
        *,
        max_cost_per_chapter: float | None = None,
        max_cost_per_project: float | None = None,
        warn_threshold: float | None = None,
    ):
        self.metrics = metrics_collector
        self.max_cost_per_chapter = max_cost_per_chapter or settings.max_cost_per_chapter
        self.max_cost_per_project = max_cost_per_project or settings.max_cost_per_project
        self.warn_threshold = warn_threshold or settings.budget_warn_threshold

    def set_collector(self, collector: MetricsCollector) -> None:
        self.metrics = collector

    def _has_metrics(self) -> bool:
        if self.metrics is not None:
            return True
        message = "BudgetGuard has no metrics collector; cost limits cannot be enforced"
        if settings.budget_fail_closed_without_metrics:
            raise RuntimeError(message)
        logger.error(message)
        return False

    async def check_chapter_budget(
        self,
        project_id: str,
        chapter_number: int,
        estimated_cost: float = 0.0,
    ) -> None:
        """在每章生成前检查单章预算"""
        if not self._has_metrics():
            return

        chapter_cost = await self.metrics.get_chapter_cost(project_id, chapter_number)
        warn_at = self.max_cost_per_chapter * self.warn_threshold

        if chapter_cost > warn_at:
            logger.warning(
                "第%d章已消耗 $%.2f，接近单章上限 $%.2f（警戒线：%.0f%%）",
                chapter_number,
                chapter_cost,
                self.max_cost_per_chapter,
                self.warn_threshold * 100,
            )

        if chapter_cost + estimated_cost > self.max_cost_per_chapter:
            raise BudgetExceededError(
                f"第{chapter_number}章预计成本 ${chapter_cost + estimated_cost:.2f} 超过单章上限 "
                f"${self.max_cost_per_chapter:.2f}。建议检查审校循环是否触发过多重写。"
            )

    async def check_project_budget(self, project_id: str, estimated_cost: float = 0.0) -> None:
        """全书预算总检查"""
        if not self._has_metrics():
            return

        summary = await self.metrics.get_project_summary(project_id)
        total = summary.get("total_cost", 0)
        warn_at = self.max_cost_per_project * self.warn_threshold

        if total > warn_at:
            logger.warning(
                "全书成本已达 $%.2f，接近预算上限 $%.2f（警戒线：%.0f%%）",
                total,
                self.max_cost_per_project,
                self.warn_threshold * 100,
            )

        if total + estimated_cost > self.max_cost_per_project:
            raise BudgetExceededError(
                f"全书预计成本 ${total + estimated_cost:.2f} 超过预算上限 ${self.max_cost_per_project:.2f}"
            )

    async def check_call_budget(
        self,
        project_id: str,
        chapter_number: int | None,
        estimated_cost: float,
    ) -> None:
        """Preflight a single LLM call against project and optional chapter limits."""
        await self.check_project_budget(project_id, estimated_cost)
        if chapter_number is not None:
            await self.check_chapter_budget(project_id, chapter_number, estimated_cost)


# 全局单例（lazy）
_budget_guard: Optional[BudgetGuard] = None


def get_budget_guard() -> BudgetGuard:
    global _budget_guard
    if _budget_guard is None:
        _budget_guard = BudgetGuard()
    return _budget_guard

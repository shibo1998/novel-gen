"""MetricsCollector —— Phase 12
LLM 调用指标采集器。记录每次调用并提供聚合查询。
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class LLMCallMetrics:
    """单次 LLM 调用的指标"""
    timestamp: Union[str, datetime]
    agent: str
    chapter_number: int
    event_id: Optional[str]
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    retry_count: int
    cost_estimate: float
    success: bool
    error_type: Optional[str]
    project_id: Optional[str] = None
    call_type: str = "initial"
    context_snapshot_id: Optional[str] = None

    def _parsed_timestamp(self) -> datetime:
        """自动将 ISO 字符串转换为 naive datetime（DB column is TIMESTAMP, not TIMESTAMPTZ）"""
        if isinstance(self.timestamp, datetime):
            dt = self.timestamp
        elif isinstance(self.timestamp, str):
            ts = self.timestamp
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts)
        else:
            raise TypeError(f"timestamp must be str or datetime, got {type(self.timestamp)}")
        return dt.replace(tzinfo=None) if dt.tzinfo else dt


class MetricsCollector:
    """指标采集器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_call(self, m: LLMCallMetrics) -> None:
        """记录一次 LLM 调用"""
        await self.db.execute(
            text("""
                INSERT INTO llm_call_metrics
                    (project_id, timestamp, agent, chapter_number, event_id, model,
                     prompt_tokens, completion_tokens, total_tokens, latency_ms,
                     retry_count, cost_estimate, success, error_type, call_type,
                     context_snapshot_id)
                VALUES
                    (:project_id, :timestamp, :agent, :chapter_number, :event_id, :model,
                     :prompt_tokens, :completion_tokens, :total_tokens, :latency_ms,
                     :retry_count, :cost_estimate, :success, :error_type, :call_type,
                     :context_snapshot_id)
            """),
            {
                "project_id": m.project_id,
                "timestamp": m._parsed_timestamp(),
                "agent": m.agent,
                "chapter_number": m.chapter_number,
                "event_id": m.event_id,
                "model": m.model,
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "total_tokens": m.total_tokens,
                "latency_ms": m.latency_ms,
                "retry_count": m.retry_count,
                "cost_estimate": m.cost_estimate,
                "success": m.success,
                "error_type": m.error_type,
                "call_type": m.call_type,
                "context_snapshot_id": m.context_snapshot_id,
            },
        )
        logger.debug(
            "MetricsCollector.record_call: agent=%s model=%s tokens=%d cost=$%.6f success=%s",
            m.agent, m.model, m.total_tokens, m.cost_estimate, m.success,
        )

    async def get_project_summary(self, project_id: str) -> dict:
        """项目级汇总"""
        row = await self.db.execute(
            text("""
                SELECT
                    COUNT(*) AS total_calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cost_estimate), 0) AS total_cost,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    COUNT(*) FILTER (WHERE success = false) AS failures,
                    COUNT(*) FILTER (WHERE retry_count > 0) AS retried_calls
                FROM llm_call_metrics
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        )
        r = row.fetchone()
        if r is None:
            return {}
        return {
            "total_calls": r[0] or 0,
            "total_tokens": r[1] or 0,
            "total_cost": round(r[2], 6) if r[2] else 0.0,
            "avg_latency_ms": round(r[3], 1) if r[3] else 0.0,
            "failures": r[4] or 0,
            "retried_calls": r[5] or 0,
        }

    async def get_per_agent_breakdown(self, project_id: str) -> list[dict]:
        """按 Agent 维度的成本明细"""
        rows = await self.db.execute(
            text("""
                SELECT
                    agent,
                    COUNT(*) AS calls,
                    SUM(total_tokens) AS tokens,
                    SUM(cost_estimate) AS cost,
                    ROUND(AVG(latency_ms)) AS avg_latency_ms,
                    COUNT(*) FILTER (WHERE success = false) AS failures
                FROM llm_call_metrics
                WHERE project_id = :project_id
                GROUP BY agent
                ORDER BY cost DESC
            """),
            {"project_id": project_id},
        )
        return [
            {
                "agent": r[0],
                "calls": r[1] or 0,
                "tokens": r[2] or 0,
                "cost": round(r[3], 6) if r[3] else 0.0,
                "avg_latency_ms": r[4] or 0,
                "failures": r[5] or 0,
            }
            for r in rows.fetchall()
        ]

    async def get_per_chapter_breakdown(self, project_id: str) -> list[dict]:
        """按章节维度的成本明细"""
        rows = await self.db.execute(
            text("""
                SELECT
                    chapter_number,
                    COUNT(*) AS calls,
                    SUM(total_tokens) AS tokens,
                    SUM(cost_estimate) AS cost,
                    ROUND(AVG(latency_ms)) AS avg_latency_ms
                FROM llm_call_metrics
                WHERE project_id = :project_id AND chapter_number IS NOT NULL
                GROUP BY chapter_number
                ORDER BY chapter_number ASC
            """),
            {"project_id": project_id},
        )
        return [
            {
                "chapter": r[0] or 0,
                "calls": r[1] or 0,
                "tokens": r[2] or 0,
                "cost": round(r[3], 6) if r[3] else 0.0,
                "avg_latency_ms": r[4] or 0,
            }
            for r in rows.fetchall()
        ]

    async def get_chapter_cost(self, project_id: str, chapter_number: int) -> float:
        """单章成本（用于 BudgetGuard）"""
        row = await self.db.execute(
            text("""
                SELECT COALESCE(SUM(cost_estimate), 0)
                FROM llm_call_metrics
                WHERE project_id = :project_id AND chapter_number = :chapter
            """),
            {"project_id": project_id, "chapter": chapter_number},
        )
        r = row.scalar()
        return round(r, 6) if r else 0.0

    async def get_recovery_cost(self, context_snapshot_id: str) -> float:
        row = await self.db.execute(
            text("""
                SELECT COALESCE(SUM(cost_estimate), 0)
                FROM llm_call_metrics
                WHERE context_snapshot_id = :snapshot_id AND call_type = 'recovery'
            """),
            {"snapshot_id": context_snapshot_id},
        )
        value = row.scalar()
        return round(value, 6) if value else 0.0

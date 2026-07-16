"""Admin API —— Phase 12 可观测性端点"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Project
from app.services.budget_guard import get_budget_guard
from app.services.metrics_collector import MetricsCollector

router = APIRouter(prefix="/api/admin/metrics", tags=["管理"])


async def get_collector(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MetricsCollector:
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return MetricsCollector(db)


@router.get("/summary")
async def get_metrics_summary(
    project_id: UUID,
    collector: MetricsCollector = Depends(get_collector),
):
    """项目总览：总成本、总调用次数、失败率"""
    return await collector.get_project_summary(str(project_id))


@router.get("/by-agent")
async def get_metrics_by_agent(
    project_id: UUID,
    collector: MetricsCollector = Depends(get_collector),
):
    """按 Agent 明细：每个 Agent 花了多少钱"""
    return await collector.get_per_agent_breakdown(str(project_id))


@router.get("/by-chapter")
async def get_metrics_by_chapter(
    project_id: UUID,
    collector: MetricsCollector = Depends(get_collector),
):
    """按章节明细：每章的成本趋势"""
    return await collector.get_per_chapter_breakdown(str(project_id))


@router.get("/chapter-cost")
async def get_chapter_cost(
    project_id: UUID,
    chapter: int = Query(..., description="章号"),
    collector: MetricsCollector = Depends(get_collector),
):
    """单章成本查询"""
    cost = await collector.get_chapter_cost(str(project_id), chapter)
    guard = get_budget_guard()
    return {
        "chapter": chapter,
        "cost": cost,
        "max_allowed": guard.max_cost_per_chapter,
        "within_budget": cost <= guard.max_cost_per_chapter,
    }

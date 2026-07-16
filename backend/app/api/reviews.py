"""Human-in-the-loop review queue APIs."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import HumanReviewItem, Project

router = APIRouter(prefix="/api", tags=["人工审核"])


class ResolveReviewRequest(BaseModel):
    resolution: dict


@router.get("/projects/{project_id}/reviews")
async def list_reviews(
    project_id: UUID,
    review_status: str = "open",
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == UUID(current_user_id))
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    items = (
        await db.execute(
            select(HumanReviewItem)
            .where(
                HumanReviewItem.project_id == project_id,
                HumanReviewItem.status == review_status,
            )
            .order_by(HumanReviewItem.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(item.id),
            "chapter_id": str(item.chapter_id),
            "chapter_content_version_id": str(item.chapter_content_version_id),
            "type": item.item_type,
            "priority": item.priority,
            "status": item.status,
            "reason": item.reason_json,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/reviews/{review_id}/resolve")
async def resolve_review(
    review_id: UUID,
    payload: ResolveReviewRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (
        await db.execute(
            select(HumanReviewItem)
            .join(Project, HumanReviewItem.project_id == Project.id)
            .where(HumanReviewItem.id == review_id, Project.user_id == UUID(current_user_id))
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.status != "open":
        raise HTTPException(status_code=409, detail="Review item is already resolved")
    item.status = "resolved"
    item.assignee_id = UUID(current_user_id)
    item.resolution_json = payload.resolution
    item.resolved_at = datetime.utcnow()
    item.updated_at = item.resolved_at
    return {"status": "resolved"}

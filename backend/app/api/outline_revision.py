"""DHO candidate, diff, approval, and rejection APIs."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import DHOReplanCandidate, Project
from app.services.dho import DHOConflictError, DHOService

router = APIRouter(prefix="/api", tags=["大纲版本"])


class ReplanCandidateRequest(BaseModel):
    affected_from: int = Field(ge=1)
    trigger: dict
    candidate_snapshot: dict | None = None


async def _owned_project(db: AsyncSession, project_id: UUID, user_id: str) -> Project:
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == UUID(user_id))
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects/{project_id}/outline/replan")
async def create_replan_candidate(
    project_id: UUID,
    payload: ReplanCandidateRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    try:
        service = DHOService(db)
        if payload.candidate_snapshot is None:
            candidate = await service.generate_candidate(
                project,
                trigger=payload.trigger,
                affected_from=payload.affected_from,
                created_by=UUID(current_user_id),
            )
        else:
            candidate = await service.create_candidate(
                project,
                trigger=payload.trigger,
                candidate_snapshot=payload.candidate_snapshot,
                affected_from=payload.affected_from,
                created_by=UUID(current_user_id),
            )
    except DHOConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(candidate.id),
        "status": candidate.status,
        "diff": candidate.diff_json,
        "affected_from": candidate.affected_from,
    }


@router.get("/projects/{project_id}/outline/replan-candidates")
async def list_replan_candidates(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    items = (
        await db.execute(
            select(DHOReplanCandidate)
            .where(DHOReplanCandidate.project_id == project_id)
            .order_by(DHOReplanCandidate.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(item.id),
            "status": item.status,
            "trigger": item.trigger_json,
            "affected_from": item.affected_from,
            "affected_to": item.affected_to,
            "diff": item.diff_json,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/projects/{project_id}/outline/replan-candidates/{candidate_id}/approve")
async def approve_replan_candidate(
    project_id: UUID,
    candidate_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    candidate = (
        await db.execute(
            select(DHOReplanCandidate).where(
                DHOReplanCandidate.id == candidate_id,
                DHOReplanCandidate.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    try:
        version = await DHOService(db).approve(project, candidate, UUID(current_user_id))
    except DHOConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "approved", "outline_version_id": str(version.id)}


@router.post("/projects/{project_id}/outline/replan-candidates/{candidate_id}/reject")
async def reject_replan_candidate(
    project_id: UUID,
    candidate_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    candidate = (
        await db.execute(
            select(DHOReplanCandidate).where(
                DHOReplanCandidate.id == candidate_id,
                DHOReplanCandidate.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status != "pending_review":
        raise HTTPException(status_code=409, detail="Candidate is no longer pending review")
    candidate.status = "rejected"
    candidate.decided_by = UUID(current_user_id)
    candidate.decided_at = datetime.utcnow()
    return {"status": "rejected"}

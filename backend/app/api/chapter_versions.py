"""Compatibility APIs backed by the canonical OutlineVersion and DHO workflow."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import OutlineVersion, Project
from app.services.dho import DHOConflictError, DHOService

router = APIRouter(prefix="/api/projects", tags=["大纲版本"])


class OutlineVersionResponse(BaseModel):
    version: int
    outline: dict = Field(default_factory=dict)
    updated_at: str = ""


class UpdateOutlineRequest(BaseModel):
    version: int
    outline: dict


class RollbackRequest(BaseModel):
    snapshot_version: int


async def _owned_project(db: AsyncSession, project_id: UUID, user_id: str) -> Project:
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == UUID(user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _active_version(
    db: AsyncSession,
    project: Project,
    user_id: UUID,
) -> OutlineVersion:
    return await DHOService(db).capture_current_outline(project, created_by=user_id)


def _affected_from(old: dict, new: dict) -> int:
    diff = DHOService.diff(old, new)
    changed = [item["number"] for item in diff["chapters_added"]]
    changed.extend(item["number"] for item in diff["chapters_removed"])
    changed.extend(item["number"] for item in diff["chapters_modified"])
    if changed:
        return min(changed)
    numbers = [item.get("number", 0) for item in old.get("chapters", [])]
    return max(numbers, default=0) + 1


@router.get("/{project_id}/outline/version")
async def get_outline_version(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    version = await _active_version(db, project, UUID(current_user_id))
    return OutlineVersionResponse(
        version=version.version_number,
        outline=version.snapshot_json,
        updated_at=version.created_at.isoformat() if version.created_at else "",
    )


@router.put("/{project_id}/outline")
async def update_outline(
    project_id: UUID,
    request: UpdateOutlineRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    service = DHOService(db)
    base = await _active_version(db, project, UUID(current_user_id))
    if base.version_number != request.version:
        raise HTTPException(
            status_code=409,
            detail=f"大纲版本冲突：期望版本 {request.version}，当前版本 {base.version_number}。",
        )
    try:
        candidate = await service.create_candidate(
            project,
            trigger={"type": "manual_outline_update"},
            candidate_snapshot=request.outline,
            affected_from=_affected_from(base.snapshot_json, request.outline),
            created_by=UUID(current_user_id),
        )
        version = await service.approve(project, candidate, UUID(current_user_id))
    except DHOConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"version": version.version_number, "message": "Outline updated successfully"}


@router.get("/{project_id}/outline/snapshots")
async def get_outline_snapshots(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    await _active_version(db, project, UUID(current_user_id))
    versions = (
        await db.execute(
            select(OutlineVersion)
            .where(OutlineVersion.project_id == project_id)
            .order_by(OutlineVersion.version_number.desc())
        )
    ).scalars().all()
    return {
        "snapshots": [
            {
                "id": str(version.id),
                "version": version.version_number,
                "outline": version.snapshot_json,
                "reason": version.source,
                "status": version.status,
                "created_at": version.created_at.isoformat() if version.created_at else "",
            }
            for version in versions
        ]
    }


@router.post("/{project_id}/outline/snapshot")
async def create_outline_snapshot(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    version = await _active_version(db, project, UUID(current_user_id))
    return {
        "snapshot": {
            "id": str(version.id),
            "version": version.version_number,
            "outline": version.snapshot_json,
            "reason": version.source,
            "created_at": version.created_at.isoformat() if version.created_at else "",
        }
    }


@router.post("/{project_id}/outline/rollback")
async def rollback_outline(
    project_id: UUID,
    request: RollbackRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    service = DHOService(db)
    current = await _active_version(db, project, UUID(current_user_id))
    target = (
        await db.execute(
            select(OutlineVersion).where(
                OutlineVersion.project_id == project_id,
                OutlineVersion.version_number == request.snapshot_version,
            )
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        candidate = await service.create_candidate(
            project,
            trigger={"type": "outline_rollback", "target_version": target.version_number},
            candidate_snapshot=target.snapshot_json,
            affected_from=_affected_from(current.snapshot_json, target.snapshot_json),
            created_by=UUID(current_user_id),
        )
        version = await service.approve(project, candidate, UUID(current_user_id))
    except DHOConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "version": version.version_number,
        "message": f"Rolled back to version {request.snapshot_version}",
    }

"""Persistent plot-thread registry used by long-form context assembly."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import PlotThread, Project

router = APIRouter(prefix="/api", tags=["情节线"])


class PlotThreadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    start_chapter: int = Field(ge=1)
    end_chapter: int | None = Field(default=None, ge=1)
    priority: int = Field(default=1, ge=1, le=5)
    entity_id: UUID | None = None


class PlotThreadUpdate(BaseModel):
    description: str | None = None
    end_chapter: int | None = Field(default=None, ge=1)
    priority: int | None = Field(default=None, ge=1, le=5)
    status: str | None = None


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


async def _owned_thread(db: AsyncSession, thread_id: UUID, user_id: str) -> PlotThread:
    thread = (
        await db.execute(
            select(PlotThread)
            .join(Project, PlotThread.project_id == Project.id)
            .where(PlotThread.id == thread_id, Project.user_id == UUID(user_id))
        )
    ).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Plot thread not found")
    return thread


def _response(thread: PlotThread) -> dict:
    return {
        "id": str(thread.id),
        "project_id": str(thread.project_id),
        "entity_id": str(thread.entity_id) if thread.entity_id else None,
        "name": thread.name,
        "description": thread.description,
        "start_chapter": thread.start_chapter,
        "end_chapter": thread.end_chapter,
        "priority": thread.priority,
        "status": thread.status,
    }


@router.get("/projects/{project_id}/plot-threads")
async def list_plot_threads(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    rows = (
        await db.execute(
            select(PlotThread)
            .where(PlotThread.project_id == project_id)
            .order_by(PlotThread.priority.desc(), PlotThread.start_chapter)
        )
    ).scalars().all()
    return [_response(row) for row in rows]


@router.post("/projects/{project_id}/plot-threads")
async def create_plot_thread(
    project_id: UUID,
    payload: PlotThreadCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    if payload.end_chapter is not None and payload.end_chapter < payload.start_chapter:
        raise HTTPException(status_code=422, detail="end_chapter cannot precede start_chapter")
    row = PlotThread(project_id=project_id, status="active", **payload.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _response(row)


@router.put("/plot-threads/{thread_id}")
async def update_plot_thread(
    thread_id: UUID,
    payload: PlotThreadUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_thread(db, thread_id, current_user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ("active", "resolved", "abandoned"):
        raise HTTPException(status_code=422, detail="Invalid plot-thread status")
    for key, value in changes.items():
        setattr(row, key, value)
    if row.end_chapter is not None and row.end_chapter < row.start_chapter:
        raise HTTPException(status_code=422, detail="end_chapter cannot precede start_chapter")
    return _response(row)


@router.delete("/plot-threads/{thread_id}")
async def abandon_plot_thread(
    thread_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_thread(db, thread_id, current_user_id)
    row.status = "abandoned"
    return {"status": "abandoned", "thread_id": str(row.id)}

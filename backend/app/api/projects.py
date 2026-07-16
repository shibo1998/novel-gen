from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Entity, Project
from app.models.schemas import (
    EntityCreate,
    EntityResponse,
    EntityUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新项目"""
    project = Project(
        user_id=UUID(current_user_id),
        title=project_in.title,
        core_idea=project_in.core_idea,
        genre=project_in.genre,
        tone_style=project_in.tone_style,
        target_word_count=project_in.target_word_count,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """获取用户的所有项目"""
    query = select(Project).where(Project.user_id == UUID(current_user_id))

    if status_filter:
        query = query.where(Project.status == status_filter)

    query = query.order_by(Project.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取项目详情"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_in: ProjectUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新项目"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除项目"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    await db.delete(project)


@router.get("/{project_id}/entities", response_model=List[EntityResponse])
async def list_entities(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    entity_type: Optional[str] = Query(None),
):
    """获取项目的所有实体"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    query = select(Entity).where(Entity.project_id == project_id)
    if entity_type:
        query = query.where(Entity.type == entity_type)

    query = query.order_by(Entity.created_at.desc())
    result = await db.execute(query)
    entities = result.scalars().all()
    return entities


@router.post("/{project_id}/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    project_id: UUID,
    entity_in: EntityCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新实体"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    entity = Entity(
        project_id=project_id,
        type=entity_in.type,
        name=entity_in.name,
        display_name=entity_in.display_name,
        description=entity_in.description,
        data=entity_in.data or {},
    )
    db.add(entity)
    await db.flush()
    await db.refresh(entity)
    return entity


@router.get("/{project_id}/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(
    project_id: UUID,
    entity_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取实体详情"""
    result = await db.execute(
        select(Entity)
        .join(Project, Entity.project_id == Project.id)
        .where(
            Entity.id == entity_id,
            Entity.project_id == project_id,
            Project.user_id == UUID(current_user_id),
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )

    return entity


@router.put("/{project_id}/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(
    project_id: UUID,
    entity_id: UUID,
    entity_in: EntityUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新实体"""
    result = await db.execute(
        select(Entity)
        .join(Project, Entity.project_id == Project.id)
        .where(
            Entity.id == entity_id,
            Entity.project_id == project_id,
            Project.user_id == UUID(current_user_id),
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )

    update_data = entity_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity, field, value)

    entity.version += 1

    await db.flush()
    await db.refresh(entity)
    return entity

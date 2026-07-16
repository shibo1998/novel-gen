"""风格API"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Project, ProjectStyleVersion
from app.services.project_styles import ProjectStyleService
from app.services.style_analyzer import StyleAnalyzer, style_analyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["风格"])


class StyleSampleRequest(BaseModel):
    sample: str = Field(min_length=100)


async def _owned_project(db: AsyncSession, project_id: UUID, user_id: str) -> Project:
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == UUID(user_id))
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/analyze/style")
async def analyze_text_style(
    text: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分析文本风格"""
    if len(text) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text too short for style analysis (minimum 100 characters)"
        )

    analyzer = StyleAnalyzer()
    profile = await analyzer.analyze_text(text)

    return {
        "adjectives": profile.adjectives,
        "forbidden_words_found": profile.forbidden_words,
        "sentence_patterns": profile.sentence_patterns,
    }


@router.get("/style/profile")
async def get_default_style_profile(
    current_user_id: str = Depends(get_current_user),
):
    """获取默认风格配置"""
    profile = style_analyzer.default_profile
    return profile.to_dict()


@router.post("/projects/{project_id}/style-versions")
async def create_project_style(
    project_id: UUID,
    payload: StyleSampleRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    version = await ProjectStyleService(db).create_from_sample(
        project, payload.sample, UUID(current_user_id)
    )
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "profile": version.profile_json,
        "active": True,
    }


@router.get("/projects/{project_id}/style-versions")
async def list_project_styles(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    versions = (
        await db.execute(
            select(ProjectStyleVersion)
            .where(ProjectStyleVersion.project_id == project.id)
            .order_by(ProjectStyleVersion.version_number.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(version.id),
            "version_number": version.version_number,
            "profile": version.profile_json,
            "active": project.active_style_version_id == version.id,
            "created_at": version.created_at,
        }
        for version in versions
    ]


@router.post("/projects/{project_id}/style-versions/{version_id}/activate")
async def activate_project_style(
    project_id: UUID,
    version_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user_id)
    version = (
        await db.execute(
            select(ProjectStyleVersion).where(
                ProjectStyleVersion.id == version_id,
                ProjectStyleVersion.project_id == project.id,
            )
        )
    ).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Style version not found")
    await ProjectStyleService(db).activate(project, version)
    return {"status": "activated", "version_id": str(version.id)}

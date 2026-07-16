"""Chapter content version history and activation APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Chapter, ChapterContentVersion, Project
from app.services.chapter_content_versions import ChapterContentVersionService

router = APIRouter(prefix="/api", tags=["正文版本"])


async def _owned_chapter(db: AsyncSession, chapter_id: UUID, user_id: str) -> Chapter:
    chapter = (
        await db.execute(
            select(Chapter)
            .join(Project, Chapter.project_id == Project.id)
            .where(Chapter.id == chapter_id, Project.user_id == UUID(user_id))
        )
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.get("/chapters/{chapter_id}/content-versions")
async def list_content_versions(
    chapter_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chapter = await _owned_chapter(db, chapter_id, current_user_id)
    versions = (
        await db.execute(
            select(ChapterContentVersion)
            .where(ChapterContentVersion.chapter_id == chapter.id)
            .order_by(ChapterContentVersion.version_number.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(version.id),
            "version_number": version.version_number,
            "source": version.source,
            "change_summary": version.change_summary,
            "created_at": version.created_at,
            "is_active": chapter.active_content_version_id == version.id,
        }
        for version in versions
    ]


@router.post("/chapters/{chapter_id}/content-versions/{version_id}/activate")
async def activate_content_version(
    chapter_id: UUID,
    version_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chapter = await _owned_chapter(db, chapter_id, current_user_id)
    version = (
        await db.execute(
            select(ChapterContentVersion).where(
                ChapterContentVersion.id == version_id,
                ChapterContentVersion.chapter_id == chapter.id,
            )
        )
    ).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    await ChapterContentVersionService(db).activate(chapter, version)
    return {"status": "activated", "version_id": str(version.id)}

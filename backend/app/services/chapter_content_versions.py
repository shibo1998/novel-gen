"""Immutable chapter-content version creation and activation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Chapter, ChapterContentVersion, Scene
from app.services.versioning_base import VersionedSnapshot


class ChapterContentVersionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        chapter_id: UUID,
        source: str,
        created_by: UUID | None = None,
        context_snapshot_id: UUID | None = None,
        generation_task_id: UUID | None = None,
        change_summary: str | None = None,
    ) -> ChapterContentVersion:
        chapter = (
            await self.db.execute(select(Chapter).where(Chapter.id == chapter_id))
        ).scalar_one()
        scenes = (
            await self.db.execute(
                select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.scene_number)
            )
        ).scalars().all()
        next_number = await VersionedSnapshot.next_number(
            self.db,
            ChapterContentVersion,
            ChapterContentVersion.chapter_id,
            chapter_id,
        )
        scene_snapshot = [
            {
                "scene_id": str(scene.id),
                "scene_number": scene.scene_number,
                "title": scene.title,
                "content": scene.content or "",
                "status": scene.status,
            }
            for scene in scenes
        ]
        version = ChapterContentVersion(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            version_number=next_number,
            parent_version_id=chapter.active_content_version_id,
            source=source,
            scene_snapshot=scene_snapshot,
            compiled_content="\n\n".join(item["content"] for item in scene_snapshot if item["content"]),
            context_snapshot_id=context_snapshot_id,
            generation_task_id=generation_task_id,
            created_by=created_by,
            change_summary=change_summary,
        )
        self.db.add(version)
        await self.db.flush()
        chapter.active_content_version_id = version.id
        return version

    async def get_active(self, chapter_id: UUID) -> ChapterContentVersion | None:
        chapter = (
            await self.db.execute(select(Chapter).where(Chapter.id == chapter_id))
        ).scalar_one()
        if chapter.active_content_version_id is None:
            return None
        return (
            await self.db.execute(
                select(ChapterContentVersion).where(
                    ChapterContentVersion.id == chapter.active_content_version_id,
                    ChapterContentVersion.chapter_id == chapter_id,
                )
            )
        ).scalar_one_or_none()

    async def activate(self, chapter: Chapter, version: ChapterContentVersion) -> None:
        if version.chapter_id != chapter.id:
            raise ValueError("Version does not belong to chapter")
        scenes_by_id = {item["scene_id"]: item for item in version.scene_snapshot}
        scenes = (
            await self.db.execute(select(Scene).where(Scene.chapter_id == chapter.id))
        ).scalars().all()
        for scene in scenes:
            snapshot = scenes_by_id.get(str(scene.id))
            if snapshot:
                scene.content = snapshot["content"]
                scene.word_count = len(scene.content)
                scene.status = snapshot["status"]
        chapter.active_content_version_id = version.id

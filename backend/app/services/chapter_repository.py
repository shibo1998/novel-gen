"""Single write boundary for applying chapter outline snapshots."""

from sqlalchemy import select

from app.models.domain import Chapter


class ChapterRepository:
    def __init__(self, db):
        self.db = db

    async def apply_outline_snapshot(
        self,
        project_id,
        affected_from: int,
        snapshot_chapters: list[dict],
    ) -> None:
        by_number = {item["number"]: item for item in snapshot_chapters}
        chapters = list(
            (
                await self.db.execute(
                    select(Chapter).where(
                        Chapter.project_id == project_id,
                        Chapter.chapter_number >= affected_from,
                    )
                )
            ).scalars().all()
        )
        existing_numbers = {chapter.chapter_number for chapter in chapters}
        for chapter in chapters:
            replacement = by_number.get(chapter.chapter_number)
            if replacement is None:
                await self.db.delete(chapter)
                continue
            chapter.title = replacement.get("title", chapter.title)
            chapter.volume_number = replacement.get("volume", chapter.volume_number)
            chapter.outline = replacement
        for number in sorted(by_number.keys() - existing_numbers):
            if number < affected_from:
                continue
            replacement = by_number[number]
            self.db.add(
                Chapter(
                    project_id=project_id,
                    volume_number=replacement.get("volume", 1),
                    chapter_number=number,
                    title=replacement.get("title") or f"第{number}章",
                    outline=replacement,
                    status="planned",
                )
            )

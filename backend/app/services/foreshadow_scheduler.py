"""Deterministic foreshadowing scheduling for chapter planning."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Foreshadowing


class ForeshadowScheduler:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_schedule(self, project_id: str, chapter_number: int) -> dict[str, list[dict]]:
        rows = list(
            (
                await self.db.execute(
                    select(Foreshadowing)
                    .where(
                        Foreshadowing.project_id == project_id,
                        Foreshadowing.status != "resolved",
                    )
                    .order_by(Foreshadowing.sow_chapter, Foreshadowing.reap_chapter)
                )
            ).scalars().all()
        )

        active = [self._serialize(row) for row in rows if self._is_active(row, chapter_number)]
        due = [self._serialize(row) for row in rows if self._is_due(row, chapter_number)]
        return {"due": due, "active": active}

    @staticmethod
    def _is_active(row: Foreshadowing, chapter_number: int) -> bool:
        return row.sow_chapter is not None and row.sow_chapter <= chapter_number

    @staticmethod
    def _is_due(row: Foreshadowing, chapter_number: int) -> bool:
        return row.reap_chapter is not None and row.reap_chapter <= chapter_number

    @staticmethod
    def _serialize(row: Foreshadowing) -> dict:
        return {
            "id": str(row.id),
            "name": row.name,
            "description": row.description or "",
            "sow_chapter": row.sow_chapter,
            "reap_chapter": row.reap_chapter,
        }

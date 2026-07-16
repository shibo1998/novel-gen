from uuid import UUID

from sqlalchemy import select

from app.models.domain import Entity
from app.services.bible_version_manager import BibleVersionManager


async def apply_reviewed_bible_changes(
    db,
    *,
    project_id: UUID,
    chapter_number: int,
    scene_id: UUID,
    injected_bible: dict | None,
    requested_changes: list[dict],
) -> list[str]:
    allowed_names = set((injected_bible or {}).keys())
    changes = {
        item["entity_name"]: item
        for item in requested_changes
        if isinstance(item, dict) and item.get("entity_name") in allowed_names
    }
    if not changes:
        return []
    entities = (
        await db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.is_active.is_(True),
                Entity.name.in_(changes),
            )
        )
    ).scalars().all()
    manager = BibleVersionManager(db)
    versions = []
    for entity in entities:
        change = changes[entity.name]
        versions.append(
            await manager.apply_change(
                str(entity.id),
                change["updates"],
                chapter_number,
                event_id=f"scene:{scene_id}",
                change_summary=change.get("summary"),
            )
        )
    return versions

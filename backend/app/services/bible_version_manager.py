"""Temporal ORM-backed Story Bible version management."""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import BibleEntryVersion, Entity, Foreshadowing

logger = logging.getLogger(__name__)


class BibleVersionManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_snapshot(self, project_id: str, chapter_number: int) -> dict:
        snapshot = {
            "characters": {},
            "locations": {},
            "world_rules": {},
            "relationships": [],
        }
        entities = list(
            (
                await self.db.execute(
                    select(Entity).where(
                        Entity.project_id == UUID(project_id),
                        Entity.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        entry_ids = [entity.id for entity in entities]
        versions_by_entry: dict[UUID, BibleEntryVersion] = {}
        if entry_ids:
            versions = list(
                (
                    await self.db.execute(
                        select(BibleEntryVersion)
                        .where(
                            BibleEntryVersion.entry_id.in_(entry_ids),
                            BibleEntryVersion.chapter_applied <= chapter_number,
                        )
                        .order_by(
                            BibleEntryVersion.entry_id,
                            BibleEntryVersion.chapter_applied.desc(),
                            BibleEntryVersion.version_number.desc(),
                        )
                    )
                ).scalars().all()
            )
            for version in versions:
                versions_by_entry.setdefault(version.entry_id, version)

        for entity in entities:
            section = self._section(entity.type)
            if section is None:
                continue
            version = versions_by_entry.get(entity.id)
            data = version.json_snapshot if version else (entity.data or {})
            if section == "relationships":
                snapshot[section].append(data)
            else:
                snapshot[section][entity.name] = data
        return snapshot

    async def apply_change(
        self,
        entry_id: str,
        new_snapshot: dict,
        chapter_applied: int,
        event_id: Optional[str] = None,
        change_summary: Optional[str] = None,
    ) -> str:
        entry_uuid = UUID(entry_id)
        entity = (
            await self.db.execute(
                select(Entity).where(Entity.id == entry_uuid).with_for_update()
            )
        ).scalar_one()
        previous = (
            await self.db.execute(
                select(BibleEntryVersion)
                .where(BibleEntryVersion.entry_id == entry_uuid)
                .order_by(BibleEntryVersion.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        merged = {
            **(previous.json_snapshot if previous else (entity.data or {})),
            **new_snapshot,
        }
        version = BibleEntryVersion(
            entry_id=entry_uuid,
            version_number=(previous.version_number if previous else 0) + 1,
            json_snapshot=merged,
            chapter_applied=chapter_applied,
            event_applied=event_id,
            change_summary=change_summary,
            previous_version_id=previous.id if previous else None,
        )
        self.db.add(version)
        await self.db.flush()
        entity.current_version_id = version.id
        logger.info(
            "BibleVersionManager.apply_change: entry=%s v%d at ch%d, summary=%s",
            entry_id,
            version.version_number,
            chapter_applied,
            change_summary,
        )
        return str(version.id)

    async def get_change_log(self, entry_id: str) -> list[dict]:
        versions = list(
            (
                await self.db.execute(
                    select(BibleEntryVersion)
                    .where(BibleEntryVersion.entry_id == UUID(entry_id))
                    .order_by(BibleEntryVersion.version_number)
                )
            ).scalars().all()
        )
        return [
            {
                "version_number": version.version_number,
                "chapter_applied": version.chapter_applied,
                "event_applied": version.event_applied,
                "change_summary": version.change_summary,
                "created_at": version.created_at.isoformat() if version.created_at else None,
            }
            for version in versions
        ]

    async def initialize_version(
        self,
        entry_id: str,
        initial_snapshot: Optional[dict] = None,
    ) -> str:
        entry_uuid = UUID(entry_id)
        entity = (
            await self.db.execute(
                select(Entity).where(Entity.id == entry_uuid).with_for_update()
            )
        ).scalar_one()
        existing = (
            await self.db.execute(
                select(BibleEntryVersion)
                .where(BibleEntryVersion.entry_id == entry_uuid)
                .order_by(BibleEntryVersion.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing:
            entity.current_version_id = existing.id
            return str(existing.id)
        version = BibleEntryVersion(
            entry_id=entry_uuid,
            version_number=1,
            json_snapshot=initial_snapshot or entity.data or {},
            chapter_applied=0,
            event_applied="init",
            change_summary="初始版本",
            previous_version_id=None,
        )
        self.db.add(version)
        await self.db.flush()
        entity.current_version_id = version.id
        return str(version.id)

    async def resolve_foreshadowing(
        self,
        project_id: str,
        foreshadowing_id: str,
        chapter_resolved: int,
        event_id: Optional[str] = None,
    ) -> bool:
        result = await self.db.execute(
            update(Foreshadowing)
            .where(
                Foreshadowing.id == UUID(foreshadowing_id),
                Foreshadowing.project_id == UUID(project_id),
                Foreshadowing.status != "resolved",
            )
            .values(
                status="resolved",
                resolved_chapter=chapter_resolved,
                resolved_event=event_id,
                resolved_at=datetime.utcnow(),
            )
            .returning(Foreshadowing.id)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _section(entry_type: str) -> str | None:
        return {
            "character": "characters",
            "location": "locations",
            "world_rule": "world_rules",
            "relationship": "relationships",
        }.get(entry_type)

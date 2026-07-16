"""Story Bible存储 - 从PostgreSQL检索角色/地点/规则等设定"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Entity


class BibleStore:
    """Story Bible存储"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_characters(self, project_id: str, names: List[str]) -> dict:
        """Resolve requested names through canonical name, display name, and aliases."""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "character",
            )
        )
        entities = result.scalars().all()
        resolved = {}
        for requested in names:
            entity = self._match_character(entities, requested)
            if entity:
                resolved[requested] = entity.data
        return resolved

    async def get_all_characters(self, project_id: str) -> List[dict]:
        """获取项目所有角色"""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "character"
            )
        )
        entities = result.scalars().all()
        return [
            {
                "name": e.name,
                "display_name": e.display_name,
                "description": e.description,
                "data": e.data,
            }
            for e in entities
        ]

    async def get_locations(self, project_id: str) -> List[dict]:
        """获取所有地点设定"""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "location"
            )
        )
        entities = result.scalars().all()
        return [
            {
                "name": e.name,
                "display_name": e.display_name,
                "description": e.description,
                "data": e.data,
            }
            for e in entities
        ]

    async def get_rules(self, project_id: str) -> List[dict]:
        """获取世界规则（hard constraints）"""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "rule"
            )
        )
        entities = result.scalars().all()
        return [
            {
                "name": e.name,
                "description": e.description,
                "data": e.data,
            }
            for e in entities
        ]

    async def get_character(self, project_id: str, name: str) -> Optional[dict]:
        """获取单个角色档案，支持 display_name 与 data.aliases。"""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "character",
            )
        )
        entity = self._match_character(result.scalars().all(), name)
        if entity:
            return {
                "name": entity.name,
                "display_name": entity.display_name,
                "description": entity.description,
                "data": entity.data,
            }
        return None

    @staticmethod
    def _match_character(entities, requested: str):
        target = requested.strip().casefold()
        for entity in entities:
            aliases = (entity.data or {}).get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            candidates = [entity.name, entity.display_name, *aliases]
            if target in {str(candidate).strip().casefold() for candidate in candidates if candidate}:
                return entity
        return None

    async def get_entity(self, project_id: str, entity_id: str) -> Optional[dict]:
        """获取单个实体"""
        from uuid import UUID
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.id == UUID(entity_id)
            )
        )
        entity = result.scalar_one_or_none()
        if entity:
            return {
                "id": str(entity.id),
                "name": entity.name,
                "type": entity.type,
                "display_name": entity.display_name,
                "description": entity.description,
                "data": entity.data,
            }
        return None

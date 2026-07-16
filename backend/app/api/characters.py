"""Character card CRUD, AI expansion, dialogue simulation, and memory timeline."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.character import CharacterAgent
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Entity, MemoryRecord, Project
from app.schemas.character import CharacterProfile
from app.services.bible_version_manager import BibleVersionManager

router = APIRouter(prefix="/api", tags=["角色卡"])


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = ""
    profile: CharacterProfile = Field(default_factory=CharacterProfile)


class CharacterUpdate(BaseModel):
    description: str | None = None
    profile: CharacterProfile
    chapter_applied: int = Field(default=0, ge=0)
    change_summary: str = "Character profile updated"


class CharacterSimulationRequest(BaseModel):
    context: dict


async def _owned_project(db: AsyncSession, project_id: UUID, user_id: str) -> Project:
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == UUID(user_id))
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _owned_character(db: AsyncSession, character_id: UUID, user_id: str) -> Entity:
    character = (
        await db.execute(
            select(Entity)
            .join(Project, Entity.project_id == Project.id)
            .where(
                Entity.id == character_id,
                Entity.type == "character",
                Project.user_id == UUID(user_id),
            )
        )
    ).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _response(entity: Entity) -> dict:
    return {
        "id": str(entity.id),
        "project_id": str(entity.project_id),
        "name": entity.name,
        "display_name": entity.display_name,
        "description": entity.description,
        "profile": entity.data or {},
        "current_version_id": str(entity.current_version_id) if entity.current_version_id else None,
    }


@router.post("/projects/{project_id}/characters")
async def create_character(
    project_id: UUID,
    payload: CharacterCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    entity = Entity(
        project_id=project_id,
        type="character",
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        data=payload.profile.model_dump(mode="json"),
    )
    db.add(entity)
    await db.flush()
    await BibleVersionManager(db).apply_change(
        str(entity.id), entity.data, chapter_applied=0, change_summary="Character created"
    )
    return _response(entity)


@router.get("/projects/{project_id}/characters")
async def list_characters(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(db, project_id, current_user_id)
    characters = (
        await db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type == "character",
                Entity.is_active.is_(True),
            )
        )
    ).scalars().all()
    return [_response(item) for item in characters]


@router.get("/characters/{character_id}")
async def get_character(
    character_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _response(await _owned_character(db, character_id, current_user_id))


@router.put("/characters/{character_id}")
async def update_character(
    character_id: UUID,
    payload: CharacterUpdate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await _owned_character(db, character_id, current_user_id)
    profile = payload.profile.model_dump(mode="json")
    if payload.description is not None:
        character.description = payload.description
    version_id = await BibleVersionManager(db).apply_change(
        str(character.id),
        profile,
        chapter_applied=payload.chapter_applied,
        change_summary=payload.change_summary,
    )
    character.data = profile
    return {**_response(character), "current_version_id": version_id}


@router.delete("/characters/{character_id}")
async def delete_character(
    character_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a character while preserving versions and historical memories."""
    character = await _owned_character(db, character_id, current_user_id)
    character.is_active = False
    return {"status": "deleted", "character_id": str(character.id)}


@router.post("/characters/{character_id}/extend")
async def extend_character(
    character_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await _owned_character(db, character_id, current_user_id)
    profile = await CharacterAgent().extend_profile(
        character.display_name,
        character.description or "",
        character.data or {},
        project_id=str(character.project_id),
    )
    CharacterProfile.model_validate(profile)
    version_id = await BibleVersionManager(db).apply_change(
        str(character.id), profile, chapter_applied=0, change_summary="AI profile expansion"
    )
    character.data = profile
    return {**_response(character), "current_version_id": version_id}


@router.post("/characters/{character_id}/simulate")
async def simulate_character(
    character_id: UUID,
    payload: CharacterSimulationRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await _owned_character(db, character_id, current_user_id)
    memories = (
        await db.execute(
            select(MemoryRecord)
            .where(MemoryRecord.entity_id == character.id)
            .order_by(MemoryRecord.chapter_number.desc())
            .limit(10)
        )
    ).scalars().all()
    return await CharacterAgent().simulate(
        {"display_name": character.display_name, **(character.data or {})},
        payload.context,
        [
            {
                "chapter_number": item.chapter_number,
                "event_summary": item.summary or item.content,
                "emotional_impact": item.emotional_intensity,
            }
            for item in memories
        ],
        project_id=str(character.project_id),
    )


@router.get("/characters/{character_id}/memories")
async def character_memories(
    character_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await _owned_character(db, character_id, current_user_id)
    records = (
        await db.execute(
            select(MemoryRecord)
            .where(MemoryRecord.entity_id == character.id)
            .order_by(MemoryRecord.chapter_number, MemoryRecord.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(item.id),
            "chapter_number": item.chapter_number,
            "type": item.memory_type,
            "content": item.content,
            "summary": item.summary,
            "salience": item.salience,
        }
        for item in records
    ]

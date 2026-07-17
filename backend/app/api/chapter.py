"""章节API"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chapter import ChapterAgent
from app.core.security import get_current_user
from app.db.session import async_session_maker, get_db
from app.models.domain import Chapter, Entity, Project, Scene
from app.pipeline.context_builder import ContextBuilder
from app.pipeline.task_queue import task_manager
from app.services.bible_version_manager import BibleVersionManager
from app.services.consistency_checker import check_due_foreshadowing_coverage
from app.services.foreshadow_scheduler import ForeshadowScheduler
from app.services.word_budget import CHAPTER_WORD_BUDGET, distribute_scene_word_budgets

logger = __import__("logging").getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["章节"])


class ExpandChapterRequest(BaseModel):
    regenerate: bool = False


class ExpandChapterResponse(BaseModel):
    task_id: str | None
    status: str


def _planning_characters(characters: list[Entity], bible_snapshot: dict) -> list[dict]:
    versioned = bible_snapshot.get("characters", {})
    result = []
    for character in characters:
        fallback = dict(character.data or {})
        current = dict(versioned.get(character.name) or fallback)
        result.append(
            {
                "name": character.name,
                "personality_traits": current.get("personality_traits", ""),
                "speech_style": current.get("speech_style", ""),
                "quirks": current.get("quirks", ""),
                "current_state": current,
            }
        )
    return result


@router.post("/{project_id}/chapters/{chapter_id}/expand", response_model=ExpandChapterResponse)
async def expand_chapter(
    project_id: UUID,
    chapter_id: UUID,
    request: ExpandChapterRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    existing_scenes = (
        await db.execute(select(Scene).where(Scene.chapter_id == chapter_id))
    ).scalars().all()
    if existing_scenes and not request.regenerate:
        return ExpandChapterResponse(task_id=None, status="completed")
    if request.regenerate and any(
        scene.content or scene.status in ("confirmed", "completed") for scene in existing_scenes
    ):
        raise HTTPException(status_code=409, detail="Written scenes cannot be regenerated from outline")

    expansion_payload = {
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "project_data": dict(project.data or {}),
        "chapter_word_budget": CHAPTER_WORD_BUDGET,
        "chapter": {
            "number": chapter.chapter_number,
            "title": chapter.title or f"第{chapter.chapter_number}章",
            "outline": dict(chapter.outline or {}),
        },
    }

    async def run_expansion(task_id: str):
        async with async_session_maker() as session:
            agent = ChapterAgent()
            project_uuid = UUID(expansion_payload["project_id"])
            chapter_uuid = UUID(expansion_payload["chapter_id"])

            char_result = await session.execute(
                select(Entity).where(Entity.project_id == project_uuid, Entity.type == "character")
            )
            characters = char_result.scalars().all()
            chapter_number = expansion_payload["chapter"]["number"]
            bible_snapshot = await BibleVersionManager(session).get_snapshot(
                str(project_uuid), max(0, chapter_number - 1)
            )
            char_list = _planning_characters(characters, bible_snapshot)

            project_data = expansion_payload["project_data"]
            hard_constraints = project_data.get("constraints", {}).get("hard", [])
            soft_constraints = project_data.get("constraints", {}).get("soft", [])

            outline = expansion_payload["chapter"].get("outline", {}) or {}
            chapter_data = {
                "number": expansion_payload["chapter"]["number"],
                "title": expansion_payload["chapter"]["title"],
                "goal": outline.get("goal", ""),
                "key_events": outline.get("key_events", []),
                "pov_character": outline.get("pov_character", ""),
            }

            event_text = " ".join(
                " ".join(str(value) for value in event.values())
                if isinstance(event, dict)
                else str(event)
                for event in chapter_data["key_events"]
            )
            planning_query = " ".join(
                [chapter_data["title"], chapter_data["goal"], event_text]
            ).strip()
            schedule = await ForeshadowScheduler(session).get_schedule(
                str(project_uuid), chapter_data["number"]
            )
            planning_context = await ContextBuilder(session).get_planning_context(
                str(project_uuid), chapter_data["number"], planning_query
            )

            result = await agent.run({
                "project_id": str(project_uuid),
                "chapter_number": expansion_payload["chapter"]["number"],
                "chapter": chapter_data,
                "chapter_word_budget": expansion_payload["chapter_word_budget"],
                "characters": char_list,
                "hard_constraints": hard_constraints,
                "soft_constraints": soft_constraints,
                "due_foreshadowings": schedule["due"],
                "chapter_summaries": planning_context["chapter_summaries"],
                "relevant_memories": planning_context["relevant_memories"],
                "relationships": bible_snapshot.get("relationships", []),
            })

            scenes = result if isinstance(result, list) else [result]
            scenes = distribute_scene_word_budgets(
                scenes,
                expansion_payload["chapter_word_budget"],
            )
            warnings = check_due_foreshadowing_coverage(schedule["due"], scenes)
            if warnings:
                logger.warning(
                    "chapter expansion omitted %d due foreshadowings: chapter=%s",
                    len(warnings),
                    chapter_data["number"],
                )
                task_manager.update_meta(
                    task_id,
                    warnings=warnings,
                    warning_count=len(warnings),
                )
            if expansion_payload.get("regenerate"):
                old_scenes = (
                    await session.execute(select(Scene).where(Scene.chapter_id == chapter_uuid))
                ).scalars().all()
                for old_scene in old_scenes:
                    await session.delete(old_scene)
                await session.flush()
            for scene_data in scenes:
                scene = Scene(
                    chapter_id=chapter_uuid,
                    project_id=project_uuid,
                    scene_number=scene_data.get("scene_number", 1),
                    title=scene_data.get("scene_title", ""),
                    constraint_card=scene_data,
                    status="planned"
                )
                session.add(scene)

            ch_result = await session.execute(
                select(Chapter).where(Chapter.id == chapter_uuid)
            )
            ch = ch_result.scalar_one_or_none()
            if ch:
                ch.status = "expanded"
            await session.commit()
            return {"scenes": len(scenes), "warnings": warnings}

    expansion_payload["regenerate"] = request.regenerate
    task_id = task_manager.create_task(
        coroutine_factory=run_expansion,
        meta={
            "project_id": str(project_id),
            "chapter_id": str(chapter_id),
            "phase": "chapter-expand",
        },
    )
    return ExpandChapterResponse(task_id=task_id, status="pending")


@router.get("/{project_id}/chapters/{chapter_id}/scenes", response_model=List)
async def list_chapter_scenes(
    project_id: UUID,
    chapter_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Chapter not found")

    result = await db.execute(
        select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.scene_number)
    )
    scenes = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "chapter_id": str(s.chapter_id),
            "scene_number": s.scene_number,
            "title": s.title,
            "constraint_card": s.constraint_card,
            "content": s.content,
            "word_count": s.word_count,
            "status": s.status,
            "review_result": s.review_result,
        }
        for s in scenes
    ]

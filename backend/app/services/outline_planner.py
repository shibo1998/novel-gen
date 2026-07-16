import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.agents.append_outline import AppendVolumeAgent
from app.agents.outline import OutlineChapterBatchAgent, OutlineSkeletonAgent
from app.db.session import async_session_maker
from app.models.domain import Chapter, Foreshadowing, Project, Scene, Volume
from app.pipeline.task_queue import task_manager
from app.services.dho import DHOService
from app.services.outline_rolling import (
    ChapterBatchPlan,
    OutlineStateError,
    allocate_chapter_ranges,
    select_next_batch,
    validate_generated_batch,
)

logger = logging.getLogger(__name__)


def _update_progress(task_id: str, phase: str, message: str, **details: Any) -> None:
    task_manager.update_meta(task_id, phase=phase, message=message, **details)


def _bind_foreshadowing_seeds(
    chapter: dict,
    foreshadowings_by_name: dict[str, Foreshadowing],
) -> list[dict]:
    """Copy chapter seeds and attach the canonical foreshadowing row ID."""
    bound_seeds = []
    for raw_seed in chapter.get("foreshadowing_seeds", []):
        seed = dict(raw_seed) if isinstance(raw_seed, dict) else {"name": str(raw_seed)}
        name = seed.get("name")
        foreshadowing = foreshadowings_by_name.get(name)
        if foreshadowing is None:
            logger.warning(
                "Chapter %s references unknown foreshadowing seed %r",
                chapter["number"],
                name,
            )
        else:
            seed["foreshadowing_id"] = str(foreshadowing.id)
        bound_seeds.append(seed)
    return bound_seeds


def _normalize_skeleton(skeleton: dict, target_chapter_count: int) -> list[dict]:
    raw_volumes = skeleton.get("volumes")
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("Outline skeleton returned no volumes")
    if not 3 <= len(raw_volumes) <= 6:
        raise ValueError("Outline skeleton must contain 3-6 volumes")

    ranges = allocate_chapter_ranges(target_chapter_count, len(raw_volumes))
    normalized: list[dict] = []
    required_contract_fields = (
        "opening_state",
        "ending_state",
        "handoff_hook",
        "must_resolve",
    )
    for index, (raw, chapter_range) in enumerate(zip(raw_volumes, ranges), start=1):
        missing = [field for field in required_contract_fields if not raw.get(field)]
        if missing:
            raise ValueError(f"Volume {index} contract missing: {', '.join(missing)}")
        normalized.append(
            {
                **raw,
                "number": index,
                "chapter_start": chapter_range.chapter_start,
                "chapter_end": chapter_range.chapter_end,
                "contract": {
                    "opening_state": raw["opening_state"],
                    "ending_state": raw["ending_state"],
                    "handoff_hook": raw["handoff_hook"],
                    "must_resolve": raw["must_resolve"],
                },
            }
        )
    return normalized


async def generate_outline(project_id: UUID, task_id: str) -> dict:
    _update_progress(task_id, "skeleton", "正在生成完整卷契约...")
    async with async_session_maker() as session:
        project = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")
        project_data = dict(project.data or {})
        setting_document = project_data.get("setting_document")
        constraints = project_data.get("constraints")
        if not setting_document or not constraints:
            raise ValueError("Worldbuilding must be completed before outline generation")
        project_snapshot = {
            "project_id": str(project.id),
            "core_idea": project.core_idea,
            "tone_style": project.tone_style or "严肃",
            "target_chapter_count": project.target_chapter_count or 90,
            "setting_document": setting_document,
            "constraints": constraints,
        }

    skeleton_result = await OutlineSkeletonAgent().run(project_snapshot)
    volumes = _normalize_skeleton(
        skeleton_result,
        project_snapshot["target_chapter_count"],
    )
    global_foreshadowings = skeleton_result.get("foreshadowing_registry", [])

    _update_progress(
        task_id,
        "persisting_skeleton",
        f"正在保存 {len(volumes)} 个完整卷契约...",
        target_chapter_count=project_snapshot["target_chapter_count"],
        completed_chapter_count=0,
    )
    async with async_session_maker() as session:
        project = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        await session.execute(delete(Foreshadowing).where(Foreshadowing.project_id == project_id))
        await session.execute(delete(Scene).where(Scene.project_id == project_id))
        await session.execute(delete(Chapter).where(Chapter.project_id == project_id))
        await session.execute(delete(Volume).where(Volume.project_id == project_id))

        for volume in volumes:
            session.add(
                Volume(
                    project_id=project_id,
                    volume_number=volume["number"],
                    title=volume.get("title", f"第{volume['number']}卷"),
                    core_conflict=volume.get("core_conflict", ""),
                    character_arc_stage=volume.get("character_arc_stage", ""),
                    status="planned",
                    chapter_start=volume["chapter_start"],
                    chapter_end=volume["chapter_end"],
                    summary=volume.get("volume_summary", ""),
                    contract=volume["contract"],
                )
            )

        for item in global_foreshadowings:
            if not item.get("name"):
                continue
            session.add(
                Foreshadowing(
                    project_id=project_id,
                    name=item["name"],
                    description=item.get("description", ""),
                    sow_chapter=item.get("sow_chapter_hint"),
                    reap_chapter=item.get("reap_chapter_hint"),
                    status="pending",
                )
            )

        project.status = "outlined"
        data = dict(project.data or {})
        data["volumes"] = volumes
        project.data = data
        await session.commit()

    batch_result = await generate_next_batch(project_id, task_id)
    return {
        "volume_count": len(volumes),
        "target_chapter_count": project_snapshot["target_chapter_count"],
        "batch": batch_result,
    }


async def _load_batch_snapshot(project_id: UUID) -> tuple[dict, list[Volume], list[Chapter], ChapterBatchPlan | None]:
    async with async_session_maker() as session:
        project = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")
        volumes = list(
            (
                await session.execute(
                    select(Volume)
                    .where(Volume.project_id == project_id)
                    .order_by(Volume.volume_number)
                )
            ).scalars().all()
        )
        chapters = list(
            (
                await session.execute(
                    select(Chapter)
                    .where(Chapter.project_id == project_id)
                    .order_by(Chapter.chapter_number)
                )
            ).scalars().all()
        )
        plan = select_next_batch(volumes, chapters)
        data = dict(project.data or {})
        snapshot = {
            "project_id": str(project.id),
            "core_idea": project.core_idea,
            "tone_style": project.tone_style or "严肃",
            "target_chapter_count": project.target_chapter_count or 90,
            "setting_document": data.get("setting_document", ""),
            "constraints": data.get("constraints") or {"hard": [], "soft": []},
        }
        return snapshot, volumes, chapters, plan


async def get_next_batch_plan(project_id: UUID) -> ChapterBatchPlan | None:
    _, _, _, plan = await _load_batch_snapshot(project_id)
    return plan


async def generate_next_batch(project_id: UUID, task_id: str) -> dict:
    project, volumes, chapters, plan = await _load_batch_snapshot(project_id)
    if plan is None:
        _update_progress(
            task_id,
            "completed",
            "全部目标章节均已规划完成",
            completed_chapter_count=len(chapters),
            target_chapter_count=project["target_chapter_count"],
        )
        return {"complete": True, "chapter_count": 0}

    volume = next(item for item in volumes if item.volume_number == plan.volume_number)
    recent = [
        {
            "number": item.chapter_number,
            "title": item.title or "",
            "goal": (item.outline or {}).get("goal", ""),
        }
        for item in chapters[-3:]
    ]
    async with async_session_maker() as session:
        global_foreshadowings = [
            {
                "name": item.name,
                "description": item.description or "",
            }
            for item in (
                await session.execute(
                    select(Foreshadowing).where(Foreshadowing.project_id == project_id)
                )
            ).scalars().all()
        ]

    _update_progress(
        task_id,
        "chapter_batch",
        f"正在规划第 {plan.chapter_start}-{plan.chapter_end} 章...",
        active_volume=plan.volume_number,
        batch_start=plan.chapter_start,
        batch_end=plan.chapter_end,
        completed_chapter_count=len(chapters),
        target_chapter_count=project["target_chapter_count"],
    )
    volume_input = {
        "number": volume.volume_number,
        "title": volume.title or f"第{volume.volume_number}卷",
        "core_conflict": volume.core_conflict or "",
        "character_arc_stage": volume.character_arc_stage or "",
        "chapter_start": volume.chapter_start,
        "chapter_end": volume.chapter_end,
        "contract": dict(volume.contract or {}),
    }
    result = await OutlineChapterBatchAgent(volume_number=plan.volume_number).run(
        {
            **project,
            "volume": volume_input,
            "batch_start": plan.chapter_start,
            "batch_end": plan.chapter_end,
            "planned_chapter_count": len(
                [item for item in chapters if item.volume_number == plan.volume_number]
            ),
            "recent_chapters": recent,
            "global_foreshadowings": global_foreshadowings,
        }
    )
    generated_chapters = validate_generated_batch(result, plan)

    async with async_session_maker() as session:
        locked_volumes = list(
            (
                await session.execute(
                    select(Volume)
                    .where(Volume.project_id == project_id)
                    .order_by(Volume.volume_number)
                    .with_for_update()
                )
            ).scalars().all()
        )
        current_chapters = list(
            (
                await session.execute(
                    select(Chapter)
                    .where(Chapter.project_id == project_id)
                    .order_by(Chapter.chapter_number)
                )
            ).scalars().all()
        )
        current_plan = select_next_batch(locked_volumes, current_chapters)
        if current_plan != plan:
            return {
                "complete": current_plan is None,
                "chapter_count": 0,
                "message": "Batch was already planned by another task",
            }

        locked_volume = next(
            item for item in locked_volumes if item.volume_number == plan.volume_number
        )
        existing_foreshadowings = {
            item.name: item
            for item in (
                await session.execute(
                    select(Foreshadowing).where(Foreshadowing.project_id == project_id)
                )
            ).scalars().all()
        }
        for item in result.get("foreshadowing_additions", []):
            name = item.get("name")
            if not name:
                continue
            if name in existing_foreshadowings:
                row = existing_foreshadowings[name]
                row.description = item.get("description") or row.description
                row.reap_chapter = item.get("reap_chapter") or row.reap_chapter
            else:
                row = Foreshadowing(
                    project_id=project_id,
                    name=name,
                    description=item.get("description", ""),
                    sow_chapter=item.get("sow_chapter"),
                    reap_chapter=item.get("reap_chapter"),
                    status="pending",
                )
                session.add(row)
                existing_foreshadowings[name] = row

        await session.flush()
        for chapter in generated_chapters:
            bound_seeds = _bind_foreshadowing_seeds(chapter, existing_foreshadowings)

            session.add(
                Chapter(
                    project_id=project_id,
                    volume_id=locked_volume.id,
                    volume_number=plan.volume_number,
                    chapter_number=chapter["number"],
                    title=chapter.get("title", ""),
                    outline={
                        "goal": chapter.get("goal", ""),
                        "key_events": chapter.get("key_events", []),
                        "pov_character": chapter.get("pov_character", ""),
                        "foreshadowing_seeds": bound_seeds,
                    },
                    status="planned",
                )
            )

        locked_volume.status = (
            "detailed" if plan.chapter_end == locked_volume.chapter_end else "planning"
        )
        project_row = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        await DHOService(session).refresh_official_outline(
            project_row, source="rolling_planner"
        )
        await session.commit()

    completed_count = len(chapters) + len(generated_chapters)
    _update_progress(
        task_id,
        "batch_completed",
        f"第 {plan.chapter_start}-{plan.chapter_end} 章规划完成",
        active_volume=plan.volume_number,
        batch_start=plan.chapter_start,
        batch_end=plan.chapter_end,
        completed_chapter_count=completed_count,
        target_chapter_count=project["target_chapter_count"],
    )
    return {
        "complete": completed_count >= project["target_chapter_count"],
        "volume_number": plan.volume_number,
        "chapter_start": plan.chapter_start,
        "chapter_end": plan.chapter_end,
        "chapter_count": len(generated_chapters),
    }


async def append_volume_contract(
    project_id: UUID,
    task_id: str,
    intent: str,
    target_chapters: int,
) -> dict:
    async with async_session_maker() as session:
        project = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")
        volumes = list(
            (
                await session.execute(
                    select(Volume)
                    .where(Volume.project_id == project_id)
                    .order_by(Volume.volume_number)
                )
            ).scalars().all()
        )
        if not volumes:
            raise ValueError("Outline must be generated before appending a volume")
        last_volume = volumes[-1]
        if last_volume.status != "detailed":
            raise OutlineStateError("Current final volume must be fully planned before appending")
        data = dict(project.data or {})
        snapshot = {
            "project_id": str(project.id),
            "core_idea": project.core_idea,
            "constraints": data.get("constraints") or {"hard": [], "soft": []},
        }
        previous_volume = {
            "number": last_volume.volume_number,
            "title": last_volume.title or f"第{last_volume.volume_number}卷",
            "core_conflict": last_volume.core_conflict or "",
            "contract": dict(last_volume.contract or {}),
        }
        next_volume_number = last_volume.volume_number + 1
        chapter_start = (last_volume.chapter_end or 0) + 1
        chapter_end = chapter_start + target_chapters - 1

    _update_progress(
        task_id,
        "append_contract",
        f"正在设计第 {next_volume_number} 卷完整契约...",
        active_volume=next_volume_number,
        batch_start=chapter_start,
        batch_end=min(chapter_start + 4, chapter_end),
    )
    result = await AppendVolumeAgent().run(
        {
            **snapshot,
            "previous_volume": previous_volume,
            "next_volume_number": next_volume_number,
            "chapter_start": chapter_start,
            "chapter_end": chapter_end,
            "user_intent": intent,
        }
    )
    volume = result["volume"]
    contract = {
        "opening_state": volume["opening_state"],
        "ending_state": volume["ending_state"],
        "handoff_hook": volume["handoff_hook"],
        "must_resolve": volume["must_resolve"],
    }

    async with async_session_maker() as session:
        project = (
            await session.execute(select(Project).where(Project.id == project_id).with_for_update())
        ).scalar_one()
        last_volume = (
            await session.execute(
                select(Volume)
                .where(Volume.project_id == project_id)
                .order_by(Volume.volume_number.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one()
        if last_volume.volume_number + 1 != next_volume_number:
            raise OutlineStateError("Another volume was appended concurrently")
        session.add(
            Volume(
                project_id=project_id,
                volume_number=next_volume_number,
                title=volume["title"],
                core_conflict=volume["core_conflict"],
                character_arc_stage=volume["character_arc_stage"],
                status="planned",
                chapter_start=chapter_start,
                chapter_end=chapter_end,
                summary=volume["volume_summary"],
                contract=contract,
            )
        )
        project.target_chapter_count = chapter_end
        await session.commit()

    batch = await generate_next_batch(project_id, task_id)
    return {
        "next_volume_number": next_volume_number,
        "chapter_start": chapter_start,
        "chapter_end": chapter_end,
        "batch": batch,
    }

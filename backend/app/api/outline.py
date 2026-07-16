from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Chapter, Foreshadowing, Project, Scene, Volume
from app.models.schemas import (
    AppendVolumeRequest,
    AppendVolumeResponse,
    ExpandVolumeResponse,
    OutlineRequest,
    OutlineResponse,
    OutlineResult,
)
from app.pipeline.task_queue import task_manager
from app.services.outline_planner import (
    append_volume_contract,
    generate_next_batch,
    generate_outline,
    get_next_batch_plan,
)

router = APIRouter(prefix="/api/projects", tags=["大纲"])


# ═══════════════════════════════════════════════════════
#  POST /projects/{id}/outline — 生成完整卷契约 + 首批五章
# ═══════════════════════════════════════════════════════
@router.post("/{project_id}/outline", response_model=OutlineResponse)
async def trigger_outline(
    project_id: UUID,
    request: OutlineRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成完整卷契约，并只展开第一批至多五章。"""
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_data = dict(project.data or {})
    if not project_data.get("setting_document") or not project_data.get("constraints"):
        raise HTTPException(
            status_code=400,
            detail="Worldbuilding must be completed before outline generation",
        )

    active_task = task_manager.find_active_task(
        project_id=str(project_id),
        kind="outline_generation",
    )
    if active_task:
        raise HTTPException(
            status_code=409,
            detail={"message": "Outline generation is already running", "task_id": active_task.id},
        )

    existing_volumes = list(
        (
            await db.execute(select(Volume).where(Volume.project_id == project_id))
        ).scalars().all()
    )
    existing_chapters = list(
        (
            await db.execute(select(Chapter).where(Chapter.project_id == project_id))
        ).scalars().all()
    )
    if (existing_volumes or existing_chapters) and not request.regenerate:
        raise HTTPException(
            status_code=409,
            detail="Outline already exists; set regenerate=true to replace it",
        )
    if request.regenerate and existing_chapters:
        writing_started = any(
            chapter.word_count > 0 or chapter.status in ("writing", "completed")
            for chapter in existing_chapters
        )
        has_scenes = False
        if not writing_started:
            has_scenes = (
                await db.execute(
                    select(Scene.id).where(Scene.project_id == project_id).limit(1)
                )
            ).scalar_one_or_none() is not None
        if writing_started or has_scenes:
            raise HTTPException(
                status_code=409,
                detail="Cannot regenerate outline after chapter writing has started",
            )

    task_id = task_manager.create_task(
        coroutine_factory=lambda allocated_id: generate_outline(project_id, allocated_id),
        meta={
            "project_id": str(project_id),
            "phase": "queued",
            "message": "大纲任务已排队",
            "completed_chapter_count": 0,
            "target_chapter_count": project.target_chapter_count or 90,
            "regenerate": request.regenerate,
            "kind": "outline_generation",
        },
    )
    return OutlineResponse(task_id=task_id, status="pending")


# ═══════════════════════════════════════════════════════
#  GET /projects/{id}/outline — 获取大纲（含按卷分组的章节）
# ═══════════════════════════════════════════════════════
@router.get("/{project_id}/outline", response_model=OutlineResult)
async def get_outline(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取大纲：聚合 volumes 表 + chapters 表"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 读 volumes 表
    volumes_result = await db.execute(
        select(Volume).where(Volume.project_id == project_id).order_by(Volume.volume_number)
    )
    volumes_rows = volumes_result.scalars().all()

    # 读 chapters 表
    chapters_result = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
    )
    chapters_rows = chapters_result.scalars().all()

    if not volumes_rows and not chapters_rows:
        return OutlineResult(
            volumes=[],
            chapters=[],
            foreshadowing_registry=[],
        )

    # 按卷号分组章节
    chapters_by_volume: dict[int, list] = {}
    for ch in chapters_rows:
        vn = ch.volume_number
        if vn not in chapters_by_volume:
            chapters_by_volume[vn] = []
        chapters_by_volume[vn].append({
            "volume": vn,
            "number": ch.chapter_number,
            "title": ch.title,
            "goal": (ch.outline or {}).get("goal", ""),
            "key_events": (ch.outline or {}).get("key_events", []),
            "pov_character": (ch.outline or {}).get("pov_character", ""),
            "foreshadowing_seeds": (ch.outline or {}).get("foreshadowing_seeds", []),
        })

    volumes_out = []
    for v in volumes_rows:
        planned_chapter_count = len(chapters_by_volume.get(v.volume_number, []))
        target_chapter_count = (
            v.chapter_end - v.chapter_start + 1
            if v.chapter_start is not None and v.chapter_end is not None
            else 0
        )
        volumes_out.append({
            "number": v.volume_number,
            "title": v.title or f"第{v.volume_number}卷",
            "core_conflict": v.core_conflict or "",
            "character_arc_stage": v.character_arc_stage or "",
            "status": v.status,
            "chapter_start": v.chapter_start,
            "chapter_end": v.chapter_end,
            "summary": v.summary or "",
            "contract": dict(v.contract or {}),
            "planned_chapter_count": planned_chapter_count,
            "target_chapter_count": target_chapter_count,
            "is_complete": bool(target_chapter_count and planned_chapter_count >= target_chapter_count),
            "has_detail": planned_chapter_count > 0,
        })

    # 读伏笔
    fs_result = await db.execute(
        select(Foreshadowing).where(Foreshadowing.project_id == project_id)
    )
    foreshadowings = [
        {
            "name": fs.name,
            "description": fs.description,
            "sow_chapter": fs.sow_chapter,
            "reap_chapter": fs.reap_chapter,
        }
        for fs in fs_result.scalars().all()
    ]

    all_chapters = []
    for vn in sorted(chapters_by_volume.keys()):
        all_chapters.extend(chapters_by_volume[vn])

    return OutlineResult(
        volumes=volumes_out,
        chapters=all_chapters,
        foreshadowing_registry=foreshadowings,
    )


# ═══════════════════════════════════════════════════════
#  GET /projects/{id}/volumes — 列出所有卷
# ═══════════════════════════════════════════════════════
@router.get("/{project_id}/volumes", response_model=list)
async def list_volumes(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目的所有卷（含展开状态）"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    rows = (await db.execute(
        select(Volume).where(Volume.project_id == project_id).order_by(Volume.volume_number)
    )).scalars().all()
    chapter_rows = (
        await db.execute(select(Chapter).where(Chapter.project_id == project_id))
    ).scalars().all()
    planned_counts: dict[int, int] = {}
    for chapter in chapter_rows:
        planned_counts[chapter.volume_number] = planned_counts.get(chapter.volume_number, 0) + 1

    return [
        {
            "id": str(v.id),
            "project_id": str(v.project_id),
            "volume_number": v.volume_number,
            "title": v.title,
            "core_conflict": v.core_conflict,
            "character_arc_stage": v.character_arc_stage,
            "status": v.status,
            "chapter_start": v.chapter_start,
            "chapter_end": v.chapter_end,
            "summary": v.summary,
            "contract": dict(v.contract or {}),
            "planned_chapter_count": planned_counts.get(v.volume_number, 0),
            "target_chapter_count": (
                v.chapter_end - v.chapter_start + 1
                if v.chapter_start is not None and v.chapter_end is not None
                else 0
            ),
            "is_complete": (
                v.status in ("detailed", "writing", "completed")
                or (
                    v.chapter_start is not None
                    and v.chapter_end is not None
                    and planned_counts.get(v.volume_number, 0)
                    >= v.chapter_end - v.chapter_start + 1
                )
            ),
        }
        for v in rows
    ]


# ═══════════════════════════════════════════════════════
#  POST /projects/{id}/outline/expand-next — 规划下一批章节
# ═══════════════════════════════════════════════════════
async def _start_next_batch(
    project_id: UUID,
    current_user_id: str,
    db: AsyncSession,
    requested_volume: int | None = None,
) -> ExpandVolumeResponse:
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    plan = await get_next_batch_plan(project_id)
    if plan is None:
        raise HTTPException(status_code=409, detail="All target chapters are already planned")
    if requested_volume is not None and requested_volume != plan.volume_number:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Chapters must be planned sequentially",
                "active_volume": plan.volume_number,
            },
        )

    active_task = task_manager.find_active_task(
        project_id=str(project_id),
        kind="outline_batch",
    )
    if active_task:
        raise HTTPException(
            status_code=409,
            detail={"message": "A chapter batch is already running", "task_id": active_task.id},
        )

    task_id = task_manager.create_task(
        coroutine_factory=lambda allocated_id: generate_next_batch(project_id, allocated_id),
        meta={
            "project_id": str(project_id),
            "phase": "queued",
            "message": f"等待规划第 {plan.chapter_start}-{plan.chapter_end} 章",
            "active_volume": plan.volume_number,
            "batch_start": plan.chapter_start,
            "batch_end": plan.chapter_end,
            "kind": "outline_batch",
        },
    )
    return ExpandVolumeResponse(
        task_id=task_id,
        status="pending",
        volume_number=plan.volume_number,
        chapter_start=plan.chapter_start,
        chapter_end=plan.chapter_end,
    )


@router.post("/{project_id}/outline/expand-next", response_model=ExpandVolumeResponse)
async def expand_next_chapters(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _start_next_batch(project_id, current_user_id, db)


# 兼容旧客户端：路径保留，但每次同样只规划下一批至多五章。
@router.post("/{project_id}/volumes/expand/{vol_num}", response_model=ExpandVolumeResponse)
async def expand_volume(
    project_id: UUID,
    vol_num: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _start_next_batch(project_id, current_user_id, db, requested_volume=vol_num)


# ═══════════════════════════════════════════════════════
#  GET /projects/{id}/chapters — 章节列表（兼容）
# ═══════════════════════════════════════════════════════
@router.get("/{project_id}/chapters")
async def list_chapters(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目章节列表"""
    if not (await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == UUID(current_user_id))
    )).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    chapters = (
        await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_number)
        )
    ).scalars().all()
    scenes = (
        await db.execute(
            select(Scene).where(Scene.project_id == project_id).order_by(Scene.scene_number)
        )
    ).scalars().all()
    scene_counts: dict[UUID, int] = {}
    for scene in scenes:
        scene_counts[scene.chapter_id] = scene_counts.get(scene.chapter_id, 0) + 1
    return [
        {
            "id": str(chapter.id),
            "chapter_number": chapter.chapter_number,
            "volume_number": chapter.volume_number,
            "title": chapter.title,
            "status": chapter.status,
            "word_count": chapter.word_count,
            "scene_count": scene_counts.get(chapter.id, 0),
            "is_locked": chapter.is_locked,
            "active_content_version_id": (
                str(chapter.active_content_version_id)
                if chapter.active_content_version_id
                else None
            ),
        }
        for chapter in chapters
    ]


# ═══════════════════════════════════════════════════════
#  POST /projects/{id}/volumes/append — 追加完整卷契约 + 首批五章
# ═══════════════════════════════════════════════════════
@router.post("/{project_id}/volumes/append", response_model=AppendVolumeResponse)
async def append_volume(
    project_id: UUID,
    request: AppendVolumeRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    volumes = list(
        (
            await db.execute(
                select(Volume)
                .where(Volume.project_id == project_id)
                .order_by(Volume.volume_number)
            )
        ).scalars().all()
    )
    if not volumes:
        raise HTTPException(status_code=400, detail="Outline must be generated first")
    if volumes[-1].status != "detailed":
        raise HTTPException(
            status_code=409,
            detail="Current final volume must be fully planned before appending",
        )

    target_chapters = request.target_chapters or max(
        8,
        round((project.target_chapter_count or 90) / len(volumes)),
    )
    active_task = task_manager.find_active_task(
        project_id=str(project_id),
        kind="outline_append",
    )
    if active_task:
        raise HTTPException(
            status_code=409,
            detail={"message": "A volume append task is already running", "task_id": active_task.id},
        )
    task_id = task_manager.create_task(
        coroutine_factory=lambda allocated_id: append_volume_contract(
            project_id,
            allocated_id,
            request.intent or "",
            target_chapters,
        ),
        meta={
            "project_id": str(project_id),
            "phase": "queued",
            "message": "追加卷契约任务已排队",
            "active_volume": volumes[-1].volume_number + 1,
            "kind": "outline_append",
        },
    )
    return AppendVolumeResponse(task_id=task_id, status="pending")

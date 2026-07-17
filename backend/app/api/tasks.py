"""Authenticated project task query route."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.task_errors import (
    public_error_code_for_status,
    public_error_for_status,
)
from app.db.session import async_session_maker, get_db
from app.models.constraints import SceneConstraint
from app.models.domain import ContextSnapshot, GenerationTask, Project, Scene
from app.models.schemas import TaskStatus
from app.pipeline.coordinator import coordinator
from app.pipeline.task_queue import task_manager
from app.services.chapter_content_versions import ChapterContentVersionService
from app.services.generation_task_store import GenerationTaskStore
from app.services.metrics_collector import MetricsCollector
from app.services.prose_compliance import apply_scene_compliance
from app.services.quality_workflow import QualityWorkflow
from app.services.reviewed_bible_changes import apply_reviewed_bible_changes

router = APIRouter(prefix="/api", tags=["任务"])


@router.get("/projects/{project_id}/tasks")
async def list_project_tasks(
    project_id: UUID,
    limit: int = 50,
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
    tasks = (
        await db.execute(
            select(GenerationTask)
            .where(GenerationTask.project_id == project_id)
            .order_by(GenerationTask.updated_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).scalars().all()
    return [
        {
            "task_id": task.task_id,
            "scene_id": str(task.scene_id) if task.scene_id else None,
            "context_snapshot_id": (
                str(task.context_snapshot_id) if task.context_snapshot_id else None
            ),
            "task_type": task.task_type,
            "phase": task.phase,
            "status": task.status,
            "error": public_error_for_status(task.status),
            "error_code": public_error_code_for_status(task.status),
            "recovery_attempt_count": task.recovery_attempt_count,
            "max_recovery_attempts": task.max_recovery_attempts,
            "recovery_allowance": task.recovery_allowance,
            "spent_cost": task.spent_cost,
            "can_recover": (
                task.status in ("failed", "interrupted", "orphaned")
                and task.scene_id is not None
                and task.context_snapshot_id is not None
                and task.recovery_attempt_count < task.max_recovery_attempts
            ),
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
        }
        for task in tasks
    ]


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(
    task_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    durable_task = (
        await db.execute(
            select(GenerationTask)
            .join(Project, GenerationTask.project_id == Project.id)
            .where(
                GenerationTask.task_id == task_id,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if durable_task:
        live_info = task_manager.get_task_status(task_id) or {}
        meta = dict(live_info.get("meta") or {})
        meta.update(
            {
                "project_id": str(durable_task.project_id),
                "scene_id": str(durable_task.scene_id) if durable_task.scene_id else None,
                "phase": durable_task.phase,
                "context_snapshot_id": (
                    str(durable_task.context_snapshot_id)
                    if durable_task.context_snapshot_id
                    else None
                ),
            }
        )
        return TaskStatus(
            task_id=durable_task.task_id,
            status=durable_task.status,
            result=live_info.get("result"),
            error=public_error_for_status(durable_task.status),
            error_code=public_error_code_for_status(durable_task.status),
            meta=meta,
        )

    status_info = task_manager.get_task_status(task_id)
    if not status_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project_id = (status_info.get("meta") or {}).get("project_id")
    if not project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    try:
        project_uuid = UUID(project_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from None
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_uuid,
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    status_info = dict(status_info)
    status_info["error"] = public_error_for_status(status_info.get("status"))
    status_info["error_code"] = public_error_code_for_status(status_info.get("status"))
    return TaskStatus(**status_info)


@router.post("/tasks/{task_id}/recover")
async def recover_task(
    task_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    original = (
        await db.execute(
            select(GenerationTask)
            .join(Project, GenerationTask.project_id == Project.id)
            .where(
                GenerationTask.task_id == task_id,
                Project.user_id == UUID(current_user_id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not original or not original.scene_id or not original.context_snapshot_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if original.status not in ("failed", "interrupted", "orphaned"):
        raise HTTPException(status_code=409, detail="Task is not recoverable")
    if original.recovery_attempt_count >= original.max_recovery_attempts:
        raise HTTPException(status_code=409, detail="Recovery attempt limit reached")

    recovery_cost = await MetricsCollector(db).get_recovery_cost(str(original.context_snapshot_id))
    if recovery_cost >= original.recovery_allowance:
        raise HTTPException(status_code=409, detail="Recovery budget exhausted")

    project_id = original.project_id
    scene_id = original.scene_id
    snapshot_id = original.context_snapshot_id
    next_attempt = original.recovery_attempt_count + 1
    recovery_task_id = str(uuid4())
    original.recovery_attempt_count = next_attempt
    original.status = "recovering"
    await GenerationTaskStore(db).start(
        task_id=recovery_task_id,
        project_id=project_id,
        scene_id=scene_id,
        context_snapshot_id=snapshot_id,
        task_type="recovery",
        idempotency_key=f"recovery:{original.id}:{next_attempt}",
    )
    await db.commit()

    async def run(recovery_task_id: str):
        async with async_session_maker() as task_db:
            source = (
                await task_db.execute(select(GenerationTask).where(GenerationTask.id == original.id))
            ).scalar_one()
            snapshot = (
                await task_db.execute(select(ContextSnapshot).where(ContextSnapshot.id == snapshot_id))
            ).scalar_one()
            scene = (await task_db.execute(select(Scene).where(Scene.id == scene_id))).scalar_one()
            constraint = SceneConstraint(**snapshot.snapshot_json["constraint_card_snapshot"])
            store = GenerationTaskStore(task_db)
            durable = await store.start(
                task_id=recovery_task_id,
                project_id=project_id,
                scene_id=scene_id,
                context_snapshot_id=snapshot_id,
                task_type="recovery",
                idempotency_key=f"recovery:{source.id}:{next_attempt}",
            )
            await task_db.commit()
            try:
                result = await coordinator.run_writing_flow(
                    constraint=constraint,
                    project_id=str(project_id),
                    chapter_number=constraint.chapter_number,
                    db=task_db,
                    context_snapshot_id=str(snapshot_id),
                    call_type="recovery",
                )
                scene.content = result["content"]
                scene.word_count = len(result["content"])
                review_result = apply_scene_compliance(
                    scene,
                    result["content"],
                    review_passed=result["passed"],
                    review_result={
                    "passed": result["passed"],
                    "issues": result["issues"],
                    "revision_count": result["revision_count"],
                    "style_review": result.get("style_review", {}),
                    },
                )
                effective_passed = review_result["passed"]
                content_version = await ChapterContentVersionService(task_db).create(
                    chapter_id=scene.chapter_id,
                    source="recovery",
                    context_snapshot_id=snapshot_id,
                    generation_task_id=durable.id,
                    change_summary="Full-scene recovery regeneration",
                )
                await QualityWorkflow(task_db).evaluate_if_chapter_complete(
                    scene.chapter_id, content_version
                )
                if effective_passed:
                    review_result["bible_version_ids"] = await apply_reviewed_bible_changes(
                        task_db,
                        project_id=project_id,
                        chapter_number=constraint.chapter_number,
                        scene_id=scene_id,
                        injected_bible=constraint.injected_bible,
                        requested_changes=result.get("entity_changes", []),
                    )
                await store.save_attempt(
                    durable,
                    result["content"],
                    status="completed" if effective_passed else "needs_review",
                    call_type="recovery",
                    attempt_number=1,
                )
                await store.complete(durable)
                source.status = "superseded"
                await task_db.commit()
                return {"scene_id": str(scene_id), "passed": effective_passed}
            except Exception as exc:
                await store.fail(durable, exc)
                source.status = "failed"
                await task_db.commit()
                raise

    task_manager.create_task(
        coroutine_factory=run,
        task_id=recovery_task_id,
        meta={
            "project_id": str(project_id),
            "scene_id": str(scene_id),
            "phase": "recovery",
            "context_snapshot_id": str(snapshot_id),
        },
    )
    return {"task_id": recovery_task_id, "status": "pending", "recovery_attempt": next_attempt}

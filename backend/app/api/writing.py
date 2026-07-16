"""写作API —— Phase 9 增强版"""
import hashlib
import json
import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.reviewer import ReviewerAgent
from app.agents.writer import WriterAgent
from app.core.security import get_current_user
from app.core.task_errors import PUBLIC_TASK_ERROR, TASK_EXECUTION_FAILED
from app.db.session import async_session_maker, get_db
from app.models.constraints import SceneConstraint
from app.models.domain import Chapter, Foreshadowing, GenerationTask, Project, Scene
from app.pipeline.context_builder import ContextBuilder
from app.pipeline.coordinator import coordinator
from app.pipeline.task_queue import STREAM_EVENT_STATUS, StreamEvent, task_manager
from app.services.bible_version_manager import BibleVersionManager
from app.services.chapter_content_versions import ChapterContentVersionService
from app.services.context_snapshot_store import ContextSnapshotStore
from app.services.generation_task_store import GenerationTaskStore
from app.services.llm_observability import LLMCallObserver
from app.services.prose_compliance import apply_scene_compliance
from app.services.quality_workflow import QualityWorkflow
from app.services.reviewed_bible_changes import apply_reviewed_bible_changes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/scenes", tags=["写作"])


def _chapter_idempotency_key(
    project_id: UUID,
    chapter_number: int,
    snapshot_ids: list[UUID],
) -> str:
    payload = ":".join(str(snapshot_id) for snapshot_id in snapshot_ids)
    signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"write-chapter:{project_id}:{chapter_number}:{signature}"


class StreamWriteRequest(BaseModel):
    last_received_offset: int = 0


class SaveContentRequest(BaseModel):
    content: str


async def _enrich_constraint_for_writing(
    db: AsyncSession,
    project_id: UUID,
    constraint: SceneConstraint,
) -> SceneConstraint:
    """Build the budgeted context once, then pass an enriched constraint to the writer."""
    enriched, _, _ = await _build_writing_context(db, project_id, constraint)
    return enriched


async def _build_writing_context(
    db: AsyncSession,
    project_id: UUID,
    constraint: SceneConstraint,
) -> tuple[SceneConstraint, dict, dict]:
    """Build an enriched constraint together with its frozen source data."""
    builder = ContextBuilder(db)
    context, report = await builder.build_context_with_budget(str(project_id), constraint)
    logger.info(
        "writing context built: project=%s chapter=%d scene=%d utilization=%s dropped=%s",
        project_id,
        constraint.chapter_number,
        constraint.scene_number,
        report.get("utilization"),
        report.get("dropped_categories", []),
    )
    return builder.enrich_constraint(constraint, context), context, report


async def _get_owned_scene(
    db: AsyncSession,
    scene_id: UUID,
    current_user_id: str,
) -> Scene:
    """Return a scene only when it belongs to the authenticated user's project."""
    result = await db.execute(
        select(Scene)
        .join(Project, Scene.project_id == Project.id)
        .where(Scene.id == scene_id, Project.user_id == UUID(current_user_id))
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


async def _resolve_reviewed_foreshadowings(
    db: AsyncSession,
    project_id: UUID,
    chapter_number: int,
    foreshadowing_ids: list[str],
) -> list[str]:
    """Resolve only pending foreshadowings owned by the current project."""
    valid_ids = []
    for item in foreshadowing_ids:
        try:
            valid_ids.append(UUID(str(item)))
        except (TypeError, ValueError):
            logger.warning("Ignored invalid foreshadowing id from reviewer: %r", item)
    if not valid_ids:
        return []

    rows = list(
        (
            await db.execute(
                select(Foreshadowing).where(
                    Foreshadowing.id.in_(valid_ids),
                    Foreshadowing.project_id == project_id,
                    Foreshadowing.status != "resolved",
                )
            )
        ).scalars().all()
    )
    manager = BibleVersionManager(db)
    for row in rows:
        await manager.resolve_foreshadowing(
            str(project_id), str(row.id), chapter_number
        )
    return [str(row.id) for row in rows]


# ═══════════════════════════════════════════════════════════
#  POST /{scene_id}/write  — 手动流式写作（用户分步控制）
# ═══════════════════════════════════════════════════════════
@router.post("/{scene_id}/write")
async def stream_write_scene(
    scene_id: UUID,
    payload: StreamWriteRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE流式生成场景正文（手动模式）。
    用户自己控制：生成 → 审校 → 保存 的节奏。
    每20 token归档一次部分草稿；断线恢复会明确地重新生成整个场景。
    """
    manual_task_id = str(uuid4())

    async def generate():
        last_offset = payload.last_received_offset
        call_type = "recovery" if last_offset > 0 else "initial"
        accumulated_content = ""
        durable_task = None
        store = GenerationTaskStore(db)

        try:
            if last_offset > 0:
                yield f"data: {json.dumps({'type': 'recovering', 'message': '重新生成整个场景', 'offset': 0})}\n\n"
                last_offset = 0

            try:
                scene = await _get_owned_scene(db, scene_id, current_user_id)
            except HTTPException:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Scene not found'})}\n\n"
                return

            constraint_card = scene.constraint_card or {}
            constraint = SceneConstraint(**constraint_card)
            constraint, context, allocation = await _build_writing_context(
                db, scene.project_id, constraint
            )
            snapshot_store = ContextSnapshotStore(db)
            snapshot = await snapshot_store.create_or_get(
                scene.project_id,
                scene.id,
                snapshot_store.build_payload(constraint, context, allocation),
            )
            durable_task = await store.start(
                task_id=manual_task_id,
                project_id=scene.project_id,
                scene_id=scene.id,
                context_snapshot_id=snapshot.id,
                task_type="write-stream",
                idempotency_key=f"write-stream:{manual_task_id}",
            )
            await db.commit()

            agent = WriterAgent()
            token_count = 0
            await LLMCallObserver.check_budget(
                str(scene.project_id),
                constraint.chapter_number,
                prompt=agent._build_prompt(constraint),
                expected_output_tokens=constraint.word_budget,
            )
            writer_started = time.perf_counter()

            try:
                async for token in agent.iter_scene_stream(constraint):
                    token_count += 1
                    accumulated_content += token

                    if token_count % 20 == 0:
                        await store.archive_partial_draft(durable_task, accumulated_content)
                        await db.commit()
                        yield f"data: {json.dumps({'type': 'progress', 'offset': last_offset + token_count})}\n\n"

                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            except Exception as exc:
                await LLMCallObserver.record(
                    project_id=str(scene.project_id),
                    agent="WriterAgent",
                    prompt=constraint.model_dump_json(),
                    output=accumulated_content,
                    started=writer_started,
                    chapter_number=constraint.chapter_number,
                    call_type=call_type,
                    context_snapshot_id=str(snapshot.id),
                    error=exc,
                )
                raise
            await LLMCallObserver.record(
                project_id=str(scene.project_id),
                agent="WriterAgent",
                prompt=constraint.model_dump_json(),
                output=accumulated_content,
                started=writer_started,
                chapter_number=constraint.chapter_number,
                call_type=call_type,
                context_snapshot_id=str(snapshot.id),
            )

            scene.content = accumulated_content
            scene.word_count = len(accumulated_content)
            apply_scene_compliance(
                scene, accumulated_content, review_passed=False
            )
            content_version = await ChapterContentVersionService(db).create(
                chapter_id=scene.chapter_id,
                source="ai",
                context_snapshot_id=snapshot.id,
                generation_task_id=durable_task.id,
                change_summary="Manual streaming generation",
            )
            await QualityWorkflow(db).evaluate_if_chapter_complete(
                scene.chapter_id, content_version
            )
            await store.save_attempt(
                durable_task,
                accumulated_content,
                status="completed",
                call_type=call_type,
                attempt_number=1,
            )
            await store.complete(durable_task)
            await db.commit()

            yield f"data: {json.dumps({'type': 'done', 'total_tokens': last_offset + token_count, 'word_count': scene.word_count})}\n\n"

        except Exception as e:
            logger.exception("Manual writing stream failed for scene %s", scene_id)
            if durable_task is not None:
                await store.save_attempt(
                    durable_task,
                    accumulated_content,
                    status="interrupted",
                    call_type=call_type,
                    attempt_number=1,
                )
                await store.fail(durable_task, e)
                await db.commit()
            yield f"data: {json.dumps({'type': 'error', 'message': PUBLIC_TASK_ERROR, 'error_code': TASK_EXECUTION_FAILED})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════
#  POST /{scene_id}/write-auto  — 自动写作-审校-重试-保存（Phase 9）
# ═══════════════════════════════════════════════════════════
@router.post("/{scene_id}/write-auto")
async def write_scene_auto(
    scene_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    全自动写作流程（Phase 9）。

    流程：Coordinator.run_writing_flow()
      1. WriterAgent 生成正文
      2. ReviewerAgent 审校（含 AI 味检测）
      3. 若有问题 → 注入反馈 → 重写（最多3次）
      4. 全部通过 → 毛刺注入（每5章强制 + 重写后强制）
      5. 落库（scene.content + scene.status=confirmed）

    返回 task_id，前端轮询状态或订阅 SSE。
    """
    scene = await _get_owned_scene(db, scene_id, current_user_id)

    project_result = await db.execute(
        select(Project).where(Project.id == scene.project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    constraint_card = scene.constraint_card or {}
    constraint = SceneConstraint(**constraint_card)
    constraint, context, allocation_report = await _build_writing_context(db, scene.project_id, constraint)
    snapshot_store = ContextSnapshotStore(db)
    snapshot = await snapshot_store.create_or_get(
        scene.project_id,
        scene.id,
        snapshot_store.build_payload(constraint, context, allocation_report),
    )
    idempotency_key = f"write:{scene_id}:{snapshot.id}"
    existing_task = await GenerationTaskStore(db).get_by_idempotency(
        scene.project_id, idempotency_key
    )

    if existing_task:
        return {"task_id": existing_task.task_id, "status": existing_task.status}

    project_id = scene.project_id
    snapshot_id = snapshot.id
    reserved_task_id = str(uuid4())
    await GenerationTaskStore(db).start(
        task_id=reserved_task_id,
        project_id=project_id,
        scene_id=scene_id,
        context_snapshot_id=snapshot_id,
        task_type="write-auto",
        idempotency_key=idempotency_key,
    )
    await db.commit()

    async def run(task_id: str):

        async def emit(event: str, data: dict):
            if task_id and task_id in task_manager._tasks:
                task = task_manager._tasks[task_id]
                for q in list(task._subscribers):
                    try:
                        q.put_nowait(StreamEvent(event, data))
                    except Exception:
                        pass

        await emit(STREAM_EVENT_STATUS, {
            "phase": "write",
            "scene_id": str(scene_id),
            "message": "正在生成场景正文...",
        })

        async with async_session_maker() as task_db:
            store = GenerationTaskStore(task_db)
            durable_task = await store.start(
                task_id=task_id,
                project_id=project_id,
                scene_id=scene_id,
                context_snapshot_id=snapshot_id,
                task_type="write-auto",
                idempotency_key=idempotency_key,
            )
            await task_db.commit()

            try:
                flow_result = await coordinator.run_writing_flow(
                    constraint=constraint,
                    project_id=str(project_id),
                    chapter_number=constraint.chapter_number,
                    db=task_db,
                    context_snapshot_id=str(snapshot_id),
                )

                content = flow_result["content"]
                revision_count = flow_result["revision_count"]
                issues = flow_result["issues"]

                scene_result = await task_db.execute(select(Scene).where(Scene.id == scene_id))
                scene_row = scene_result.scalar_one_or_none()
                effective_passed = False
                if scene_row:
                    scene_row.content = content
                    scene_row.word_count = len(content)
                    review_result = apply_scene_compliance(
                        scene_row,
                        content,
                        review_passed=flow_result["passed"],
                        review_result={
                        "passed": flow_result["passed"],
                        "issues": flow_result["issues"],
                        "revision_count": flow_result["revision_count"],
                        },
                    )
                    effective_passed = review_result["passed"]
                    content_version = await ChapterContentVersionService(task_db).create(
                        chapter_id=scene_row.chapter_id,
                        source="ai",
                        context_snapshot_id=snapshot_id,
                        generation_task_id=durable_task.id,
                        change_summary="Automatic scene generation",
                    )
                    await QualityWorkflow(task_db).evaluate_if_chapter_complete(
                        scene_row.chapter_id, content_version
                    )
                    if effective_passed:
                        await _resolve_reviewed_foreshadowings(
                            task_db,
                            project_id,
                            constraint.chapter_number,
                            flow_result.get("resolved_foreshadowing_ids", []),
                        )
                        review_result["bible_version_ids"] = await apply_reviewed_bible_changes(
                            task_db,
                            project_id=project_id,
                            chapter_number=constraint.chapter_number,
                            scene_id=scene_id,
                            injected_bible=constraint.injected_bible,
                            requested_changes=flow_result.get("entity_changes", []),
                        )
                await store.save_attempt(
                    durable_task,
                    content,
                    status="completed" if effective_passed else "needs_review",
                    call_type="initial",
                    attempt_number=1,
                )
                await store.complete(durable_task)
                await task_db.commit()

                await emit(STREAM_EVENT_STATUS, {
                "phase": "write_done",
                "scene_id": str(scene_id),
                "revision_count": revision_count,
                "passed": effective_passed,
                "issues_count": len(issues),
                "word_count": len(content),
                "message": f"完成（重写{revision_count}次）",
            })

                return {
                "scene_id": str(scene_id),
                "content": content,
                "revision_count": revision_count,
                "passed": effective_passed,
                "issues": issues,
                "word_count": len(content),
                }

            except Exception as e:
                logger.exception("write-auto failed for scene %s", scene_id)
                await store.fail(durable_task, e)
                await task_db.commit()
                await emit(STREAM_EVENT_STATUS, {
                    "phase": "write_error",
                    "scene_id": str(scene_id),
                    "error": PUBLIC_TASK_ERROR,
                    "error_code": TASK_EXECUTION_FAILED,
                })
                raise

    task_id = task_manager.create_task(
        coroutine_factory=run,
        task_id=reserved_task_id,
        meta={
            "scene_id": str(scene_id),
            "project_id": str(scene.project_id),
            "phase": "write-auto",
            "context_snapshot_id": str(snapshot.id),
        },
    )
    return {"task_id": task_id, "status": "pending"}


# ═══════════════════════════════════════════════════════════
#  POST /{scene_id}/write-chapter  — 整章生成（所有场景串行）
# ═══════════════════════════════════════════════════════════
@router.post("/{scene_id}/write-chapter")
async def write_chapter_auto(
    scene_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    整章自动写作：对该场景所属章节的所有场景依次执行 write-auto。
    用户触发一次，章节内所有场景依次完成。
    """
    scene = await _get_owned_scene(db, scene_id, current_user_id)

    project_id = scene.project_id
    chapter = (
        await db.execute(
            select(Chapter).where(
                Chapter.id == scene.chapter_id,
                Chapter.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter_num = chapter.chapter_number

    all_scenes_result = await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id, Scene.chapter_id == scene.chapter_id)
        .order_by(Scene.scene_number)
    )
    scenes = list(all_scenes_result.scalars().all())

    jobs = []
    snapshot_store = ContextSnapshotStore(db)
    for item in scenes:
        if item.status in ("completed", "confirmed"):
            continue
        raw_constraint = SceneConstraint(**(item.constraint_card or {}))
        frozen_constraint, context, allocation = await _build_writing_context(
            db, project_id, raw_constraint
        )
        snapshot = await snapshot_store.create_or_get(
            project_id,
            item.id,
            snapshot_store.build_payload(frozen_constraint, context, allocation),
        )
        jobs.append(
            {
                "scene_id": item.id,
                "constraint": frozen_constraint,
                "snapshot_id": snapshot.id,
            }
        )
    await db.commit()

    if not jobs:
        return {"task_id": None, "status": "completed", "scene_count": 0}

    chapter_idempotency_key = _chapter_idempotency_key(
        project_id,
        chapter_num,
        [job["snapshot_id"] for job in jobs],
    )
    durable_store = GenerationTaskStore(db)
    existing_chapter_task = await durable_store.get_by_idempotency(
        project_id, chapter_idempotency_key
    )
    if existing_chapter_task and existing_chapter_task.status not in (
        "failed",
        "interrupted",
        "orphaned",
    ):
        return {
            "task_id": existing_chapter_task.task_id,
            "status": existing_chapter_task.status,
            "scene_count": len(jobs),
        }

    if existing_chapter_task:
        reserved_chapter_task_id = existing_chapter_task.task_id
        await durable_store.restart(existing_chapter_task)
    else:
        reserved_chapter_task_id = str(uuid4())
        await durable_store.start(
            task_id=reserved_chapter_task_id,
            project_id=project_id,
            scene_id=jobs[0]["scene_id"],
            context_snapshot_id=jobs[0]["snapshot_id"],
            task_type="write-chapter",
            idempotency_key=chapter_idempotency_key,
        )
    await db.commit()

    async def run(parent_task_id: str):
        results = []
        async with async_session_maker() as task_db:
            store = GenerationTaskStore(task_db)
            durable = await store.start(
                task_id=parent_task_id,
                project_id=project_id,
                scene_id=jobs[0]["scene_id"],
                context_snapshot_id=jobs[0]["snapshot_id"],
                task_type="write-chapter",
                idempotency_key=chapter_idempotency_key,
            )
            await task_db.commit()
            for attempt_number, job in enumerate(jobs, 1):
                sid = job["scene_id"]
                s_result = await task_db.execute(select(Scene).where(Scene.id == sid))
                s_scene = s_result.scalar_one_or_none()
                if not s_scene or s_scene.status in ("completed", "confirmed"):
                    continue

                constraint = job["constraint"]
                try:
                    flow_result = await coordinator.run_writing_flow(
                        constraint=constraint,
                        project_id=str(project_id),
                        chapter_number=chapter_num,
                        db=task_db,
                        context_snapshot_id=str(job["snapshot_id"]),
                    )
                    s_scene.content = flow_result["content"]
                    s_scene.word_count = len(flow_result["content"])
                    review_result = apply_scene_compliance(
                        s_scene,
                        flow_result["content"],
                        review_passed=flow_result["passed"],
                        review_result={
                        "passed": flow_result["passed"],
                        "issues": flow_result["issues"],
                        "revision_count": flow_result["revision_count"],
                        },
                    )
                    effective_passed = review_result["passed"]
                    content_version = await ChapterContentVersionService(task_db).create(
                        chapter_id=s_scene.chapter_id,
                        source="ai",
                        context_snapshot_id=job["snapshot_id"],
                        generation_task_id=durable.id,
                        change_summary="Automatic chapter generation",
                    )
                    await QualityWorkflow(task_db).evaluate_if_chapter_complete(
                        s_scene.chapter_id, content_version
                    )
                    if effective_passed:
                        await _resolve_reviewed_foreshadowings(
                            task_db,
                            project_id,
                            constraint.chapter_number,
                            flow_result.get("resolved_foreshadowing_ids", []),
                        )
                        review_result["bible_version_ids"] = await apply_reviewed_bible_changes(
                            task_db,
                            project_id=project_id,
                            chapter_number=constraint.chapter_number,
                            scene_id=sid,
                            injected_bible=constraint.injected_bible,
                            requested_changes=flow_result.get("entity_changes", []),
                        )
                    await store.save_attempt(
                        durable,
                        flow_result["content"],
                        status="completed" if effective_passed else "needs_review",
                        call_type="initial",
                        attempt_number=attempt_number,
                        scene_id=sid,
                        context_snapshot_id=job["snapshot_id"],
                    )
                    await task_db.commit()
                    results.append({
                        "scene_id": str(sid),
                        "word_count": len(flow_result["content"]),
                        "passed": effective_passed,
                        "revisions": flow_result["revision_count"],
                    })
                except Exception as e:
                    logger.exception("write-chapter failed for scene %s", sid)
                    await task_db.rollback()
                    results.append({
                        "scene_id": str(sid),
                        "error": PUBLIC_TASK_ERROR,
                        "error_code": TASK_EXECUTION_FAILED,
                    })
                    durable = (
                        await task_db.execute(
                            select(GenerationTask).where(GenerationTask.task_id == parent_task_id)
                        )
                    ).scalar_one()
                    await store.fail(durable, e)
                    await task_db.commit()
                    raise

            await store.complete(durable)
            await task_db.commit()
        return results

    task_id = task_manager.create_task(
        coroutine_factory=run,
        task_id=reserved_chapter_task_id,
        meta={"project_id": str(project_id), "chapter": chapter_num, "phase": "write-chapter"},
    )
    return {"task_id": task_id, "status": "pending", "scene_count": len(jobs)}


# ═══════════════════════════════════════════════════════════
#  POST /{scene_id}/save  — 保存正文（手动模式）
# ═══════════════════════════════════════════════════════════
@router.post("/{scene_id}/save")
async def save_scene_content(
    scene_id: UUID,
    payload: SaveContentRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存确认后的场景正文"""
    scene = await _get_owned_scene(db, scene_id, current_user_id)

    scene.content = payload.content
    scene.word_count = len(payload.content)
    review_result = apply_scene_compliance(
        scene, payload.content, review_passed=False
    )
    content_version = await ChapterContentVersionService(db).create(
        chapter_id=scene.chapter_id,
        source="manual",
        created_by=UUID(current_user_id),
        change_summary="Manual scene save",
    )
    await QualityWorkflow(db).evaluate_if_chapter_complete(scene.chapter_id, content_version)

    return {
        "message": "Scene saved as draft",
        "word_count": scene.word_count,
        "compliance": review_result["compliance"],
    }


# ═══════════════════════════════════════════════════════════
#  POST /{scene_id}/review  — 手动审校
# ═══════════════════════════════════════════════════════════
@router.post("/{scene_id}/review")
async def review_scene(
    scene_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """审校单个场景"""
    scene = await _get_owned_scene(db, scene_id, current_user_id)

    if not scene.content:
        raise HTTPException(status_code=400, detail="Scene content is empty")

    constraint_card = scene.constraint_card or {}
    constraint = SceneConstraint(**constraint_card)

    reviewer = ReviewerAgent()
    review_result = await reviewer.review(
        content=scene.content,
        constraint=constraint,
    )

    review_result = apply_scene_compliance(
        scene,
        scene.content,
        review_passed=review_result.get("status") == "pass",
        review_result=review_result,
    )
    if review_result["passed"]:
        review_result["resolved_foreshadowing_ids"] = await _resolve_reviewed_foreshadowings(
            db,
            scene.project_id,
            constraint.chapter_number,
            review_result.get("resolved_foreshadowing_ids", []),
        )
        review_result["bible_version_ids"] = await apply_reviewed_bible_changes(
            db,
            project_id=scene.project_id,
            chapter_number=constraint.chapter_number,
            scene_id=scene.id,
            injected_bible=constraint.injected_bible,
            requested_changes=review_result.get("entity_changes", []),
        )
        active_version = await ChapterContentVersionService(db).get_active(scene.chapter_id)
        if active_version is not None:
            await QualityWorkflow(db).evaluate_if_chapter_complete(
                scene.chapter_id, active_version
            )
    return review_result

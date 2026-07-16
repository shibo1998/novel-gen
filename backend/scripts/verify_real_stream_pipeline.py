"""Run the real novel-generation API pipeline with streaming LLM calls only.

This script is intentionally opt-in because it uses the configured paid provider.
It creates isolated data, exercises the formal FastAPI routes, validates persisted
artifacts, and removes the temporary user/project unless KEEP_REAL_ACCEPTANCE_DATA=1.
"""

import asyncio
import json
import os
from datetime import datetime
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, select, text

from app.config import settings
from app.core.security import get_current_user
from app.db.session import async_session_maker
from app.main import app
from app.models.domain import (
    Chapter,
    ChapterContentVersion,
    ContextSnapshot,
    DHOReplanCandidate,
    GenerationTask,
    HumanReviewItem,
    LLMCallMetric,
    MemoryRecord,
    Project,
    QualityReport,
    Scene,
    SceneDraftAttempt,
    User,
    Volume,
)
from app.pipeline.context_builder import ContextBuilder
from app.pipeline.task_queue import task_manager


def _emit(stage: str, **data) -> None:
    print(json.dumps({"stage": stage, **data}, ensure_ascii=False), flush=True)


async def _wait_task(task_id: str, stage: str) -> dict:
    task = task_manager.get_task(task_id)
    if task is None or task._future is None:
        raise RuntimeError(f"{stage}: task {task_id} is not available in memory")
    await task._future
    status = task_manager.get_task_status(task_id)
    if not status or status["status"] != "completed":
        raise RuntimeError(f"{stage} failed: {status}")
    _emit(stage, task_id=task_id, status="completed")
    return status


async def _assert_database_ready() -> None:
    async with async_session_maker() as db:
        await db.execute(text("SELECT 1"))


async def _validate_artifacts(project_id: UUID, chapter_id: UUID) -> dict:
    async with async_session_maker() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        volumes = list(
            (
                await db.execute(
                    select(Volume).where(Volume.project_id == project_id)
                )
            ).scalars()
        )
        chapters = list(
            (
                await db.execute(
                    select(Chapter).where(Chapter.project_id == project_id)
                )
            ).scalars()
        )
        scenes = list(
            (
                await db.execute(
                    select(Scene)
                    .where(Scene.chapter_id == chapter_id)
                    .order_by(Scene.scene_number)
                )
            ).scalars()
        )
        snapshots = list(
            (
                await db.execute(
                    select(ContextSnapshot).where(
                        ContextSnapshot.project_id == project_id
                    )
                )
            ).scalars()
        )
        tasks = list(
            (
                await db.execute(
                    select(GenerationTask).where(
                        GenerationTask.project_id == project_id
                    )
                )
            ).scalars()
        )
        attempts = list(
            (
                await db.execute(
                    select(SceneDraftAttempt).join(
                        GenerationTask,
                        SceneDraftAttempt.task_id == GenerationTask.id,
                    ).where(GenerationTask.project_id == project_id)
                )
            ).scalars()
        )
        versions = list(
            (
                await db.execute(
                    select(ChapterContentVersion).where(
                        ChapterContentVersion.chapter_id == chapter_id
                    )
                )
            ).scalars()
        )
        memories = list(
            (
                await db.execute(
                    select(MemoryRecord).where(MemoryRecord.project_id == project_id)
                )
            ).scalars()
        )
        reports = list(
            (
                await db.execute(
                    select(QualityReport).where(QualityReport.chapter_id == chapter_id)
                )
            ).scalars()
        )
        reviews = list(
            (
                await db.execute(
                    select(HumanReviewItem).where(
                        HumanReviewItem.chapter_id == chapter_id
                    )
                )
            ).scalars()
        )
        dho_candidates = list(
            (
                await db.execute(
                    select(DHOReplanCandidate).where(
                        DHOReplanCandidate.project_id == project_id
                    )
                )
            ).scalars()
        )
        metrics = list(
            (
                await db.execute(
                    select(LLMCallMetric).where(LLMCallMetric.project_id == project_id)
                )
            ).scalars()
        )

        assert project.status == "outlined", project.status
        assert (project.data or {}).get("setting_document")
        assert volumes and chapters and scenes
        assert all(scene.content for scene in scenes)
        assert all(scene.word_count == len(scene.content) for scene in scenes)
        assert all(scene.status == "confirmed" for scene in scenes), [
            scene.status for scene in scenes
        ]
        assert all((scene.review_result or {}).get("passed") is True for scene in scenes)
        assert len(snapshots) >= len(scenes)
        completed_chapter_tasks = [
            task
            for task in tasks
            if task.task_type == "write-chapter" and task.status == "completed"
        ]
        assert completed_chapter_tasks, [
            (task.task_type, task.status, task.error_message) for task in tasks
        ]
        assert len(attempts) >= len(scenes)
        assert all(attempt.status == "completed" for attempt in attempts)
        assert versions and versions[-1].compiled_content
        assert len(memories) >= len(scenes) + 1
        assert all(memory.index_status == "indexed" for memory in memories)
        assert all(memory.embedding is not None for memory in memories)
        assert reports and reports[-1].evaluation_status == "completed"
        report = reports[-1]
        assert report.overall_score is not None and 1 <= report.overall_score <= 5
        if report.needs_human_review:
            assert any(item.status == "open" for item in reviews)
        else:
            assert not any(item.status == "open" for item in reviews)
        if report.overall_score < 2.5:
            assert len(dho_candidates) == 1

        successful_agents = {
            metric.agent for metric in metrics if metric.success and metric.total_tokens > 0
        }
        assert {"writer", "reviewer", "QualityEvaluator"} <= successful_agents

        planning_context = await ContextBuilder(db).get_planning_context(
            str(project_id),
            2,
            scenes[0].title or chapters[0].title or "第一章事件",
        )
        assert planning_context["chapter_summaries"]
        assert planning_context["relevant_memories"]

        return {
            "project_status": project.status,
            "volumes": len(volumes),
            "chapters": len(chapters),
            "scenes": len(scenes),
            "scene_chars": sum(scene.word_count for scene in scenes),
            "snapshots": len(snapshots),
            "durable_tasks": len(tasks),
            "draft_attempts": len(attempts),
            "content_versions": len(versions),
            "memory_records": len(memories),
            "recalled_memories": len(planning_context["relevant_memories"]),
            "quality_score": report.overall_score,
            "needs_human_review": report.needs_human_review,
            "dho_candidates": len(dho_candidates),
            "llm_calls": len(metrics),
            "llm_agents": sorted(successful_agents),
            "total_tokens": sum(metric.total_tokens for metric in metrics),
            "estimated_cost": round(sum(metric.cost_estimate for metric in metrics), 6),
        }


async def main() -> None:
    if os.getenv("RUN_REAL_STREAM_ACCEPTANCE") != "1":
        raise SystemExit("Set RUN_REAL_STREAM_ACCEPTANCE=1 to authorize real LLM usage")
    if not settings.llm_api_key or not settings.llm_model or not settings.llm_base_url:
        raise RuntimeError("LLM base URL, model, or API key is not configured")

    await _assert_database_ready()
    _emit(
        "configuration",
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key_configured=True,
        transport="stream",
    )

    resume_project = os.getenv("REAL_ACCEPTANCE_PROJECT_ID")
    project_id = UUID(resume_project) if resume_project else None
    keep_data = os.getenv("KEEP_REAL_ACCEPTANCE_DATA") == "1"
    if project_id is not None:
        async with async_session_maker() as db:
            project = (
                await db.execute(select(Project).where(Project.id == project_id))
            ).scalar_one_or_none()
            if project is None:
                raise RuntimeError(f"Resume project does not exist: {project_id}")
            user_id = project.user_id
        _emit("resume", user_id=str(user_id), project_id=str(project_id))
    else:
        user_id = uuid4()
        async with async_session_maker() as db:
            db.add(
                User(
                    id=user_id,
                    email=f"real-stream-{user_id}@example.com",
                    username=f"stream-{str(user_id)[:8]}",
                    password_hash="acceptance-only",
                )
            )
            await db.commit()

    app.dependency_overrides[get_current_user] = lambda: str(user_id)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://real-stream-acceptance",
            timeout=60,
        ) as client:
            if project_id is None:
                suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
                response = await client.post(
                    "/api/projects",
                    json={
                        "title": f"真实流式全链路验收-{suffix}",
                        "core_idea": "边城守夜人发现失踪多年的兄长留下会改变记忆的铜铃，并追查城中旧案。",
                        "genre": "悬疑奇幻",
                        "tone_style": "克制、具体、重行动",
                        "target_word_count": 30000,
                        "target_chapter_count": 10,
                    },
                )
                assert response.status_code == 201, response.text
                project_id = UUID(response.json()["id"])
                _emit("project_created", project_id=str(project_id))

                response = await client.post(
                    f"/api/projects/{project_id}/worldbuilding", json={}
                )
                assert response.status_code == 200, response.text
                await _wait_task(response.json()["task_id"], "worldbuilding")

                response = await client.post(
                    f"/api/projects/{project_id}/outline", json={}
                )
                assert response.status_code == 200, response.text
                await _wait_task(response.json()["task_id"], "outline")

            response = await client.get(f"/api/projects/{project_id}/chapters")
            assert response.status_code == 200, response.text
            chapters = response.json()
            assert chapters
            chapter = chapters[0]

            response = await client.get(
                f"/api/projects/{project_id}/chapters/{chapter['id']}/scenes"
            )
            assert response.status_code == 200, response.text
            scenes = response.json()
            if not scenes:
                response = await client.post(
                    f"/api/projects/{project_id}/chapters/{chapter['id']}/expand",
                    json={"regenerate": False},
                )
                assert response.status_code == 200, response.text
                if response.json()["task_id"]:
                    await _wait_task(response.json()["task_id"], "chapter_expand")
                response = await client.get(
                    f"/api/projects/{project_id}/chapters/{chapter['id']}/scenes"
                )
                assert response.status_code == 200, response.text
                scenes = response.json()
            assert scenes

            response = await client.post(
                f"/api/v1/scenes/{scenes[0]['id']}/write-chapter"
            )
            assert response.status_code == 200, response.text
            if response.json()["task_id"]:
                await _wait_task(response.json()["task_id"], "chapter_write")
            else:
                assert response.json()["status"] == "completed"
                _emit("chapter_write", status="already_completed")

        report = await _validate_artifacts(project_id, UUID(chapter["id"]))
        _emit("acceptance_passed", project_id=str(project_id), **report)
    finally:
        app.dependency_overrides.clear()
        if not keep_data:
            async with async_session_maker() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            _emit("cleanup", user_id=str(user_id), project_id=str(project_id))
        else:
            _emit("cleanup_skipped", user_id=str(user_id), project_id=str(project_id))


if __name__ == "__main__":
    asyncio.run(main())

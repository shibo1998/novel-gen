"""PostgreSQL integration test for the durable long-form writing state."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from app.db.session import async_session_maker
from app.models.constraints import SceneConstraint
from app.models.domain import Chapter, Entity, PlotThread, Project, Scene, User
from app.pipeline.context_builder import ContextBuilder
from app.services.bible_version_manager import BibleVersionManager
from app.services.dho import DHOService
from app.services.memory_records import MemoryRecordStore


async def _database_available() -> bool:
    try:
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.integration
async def test_postgres_memory_context_and_dho_round_trip():
    if not await _database_available():
        pytest.skip("PostgreSQL is not available")

    user_id = uuid4()
    project_id = uuid4()
    async with async_session_maker() as db:
        try:
            user = User(
                id=user_id,
                email=f"integration-{user_id}@example.com",
                username="integration",
                password_hash="not-used",
            )
            project = Project(
                id=project_id,
                user_id=user_id,
                title="持久化集成测试",
                core_idea="验证长篇小说系统的数据闭环",
                target_chapter_count=90,
            )
            character = Entity(
                project_id=project_id,
                type="character",
                name="林远",
                display_name="林远",
                data={"core_desire": "证明自己", "arms_status": "normal"},
            )
            db.add(user)
            await db.flush()
            db.add(project)
            await db.flush()
            db.add(character)
            await db.flush()
            await BibleVersionManager(db).apply_change(
                str(character.id),
                character.data,
                chapter_applied=0,
                change_summary="integration seed",
            )
            chapter3 = Chapter(
                project_id=project_id,
                chapter_number=3,
                volume_number=1,
                title="月圆异象",
                outline={"number": 3, "title": "月圆异象"},
                status="completed",
            )
            chapter50 = Chapter(
                project_id=project_id,
                chapter_number=50,
                volume_number=2,
                title="旧伤复发",
                outline={"number": 50, "title": "旧伤复发"},
                status="planned",
            )
            db.add_all([chapter3, chapter50])
            await db.flush()
            scene3 = Scene(
                chapter_id=chapter3.id,
                project_id=project_id,
                scene_number=1,
                title="伤痕发烫",
                content="月圆之夜，林远左手伤痕突然发烫。",
                word_count=18,
                pov_character_id=character.id,
                status="confirmed",
            )
            db.add(scene3)
            db.add(
                PlotThread(
                    project_id=project_id,
                    entity_id=character.id,
                    name="旧伤之谜",
                    description="调查左手伤痕来源",
                    start_chapter=3,
                    end_chapter=60,
                    priority=5,
                    status="active",
                )
            )
            await db.flush()
            await MemoryRecordStore(db).sync_chapter(chapter3.id)

            constraint = SceneConstraint(
                chapter_number=50,
                scene_number=1,
                scene_title="月下追踪",
                narrative_goal="林远调查月圆异象",
                scene_function="progression",
                pov_character="林远",
                characters_present=["林远"],
                character_emotional_states={"林远": "警惕"},
                opening_emotion="平静",
                closing_emotion="不安",
                emotional_beats=["旧伤发热"],
                reader_should_know=["月圆与伤痕有关"],
                reader_should_not_know=["伤痕来源"],
                prose_directives=["克制"],
                forbidden_elements=["只见"],
                word_budget=800,
            )
            context, _ = await ContextBuilder(db).build_context_with_budget(
                str(project_id), constraint
            )
            assert any(
                "伤痕" in memory["summary"] and memory["chapter"] == 3
                for memory in context["memory_retrieval"]
            )
            assert context["injected_plot_threads"][0]["name"] == "旧伤之谜"

            dho = DHOService(db)
            base = await dho.refresh_official_outline(project, source="integration")
            candidate_snapshot = deepcopy(base.snapshot_json)
            for chapter in candidate_snapshot["chapters"]:
                if chapter["number"] == 50:
                    chapter["title"] = "月下真相"
            candidate_snapshot["chapters"].append(
                {"number": 51, "volume": 2, "title": "追踪者", "goal": "揭露跟踪者"}
            )
            candidate = await dho.create_candidate(
                project,
                trigger={"type": "integration"},
                candidate_snapshot=candidate_snapshot,
                affected_from=50,
            )
            await dho.approve(project, candidate, user_id)
            await db.commit()

            chapters = (
                await db.execute(
                    select(Chapter)
                    .where(Chapter.project_id == project_id)
                    .order_by(Chapter.chapter_number)
                )
            ).scalars().all()
            assert [(chapter.chapter_number, chapter.title) for chapter in chapters] == [
                (3, "月圆异象"),
                (50, "月下真相"),
                (51, "追踪者"),
            ]
        finally:
            await db.rollback()
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

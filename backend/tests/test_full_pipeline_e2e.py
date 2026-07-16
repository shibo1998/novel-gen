"""Deterministic full-pipeline E2E through real APIs and PostgreSQL."""

from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, text

from app.agents.chapter import ChapterAgent
from app.agents.outline import OutlineChapterBatchAgent, OutlineSkeletonAgent
from app.agents.worldbuilding import WorldbuildingAgent
from app.core.security import get_current_user
from app.db.session import async_session_maker
from app.main import app
from app.models.domain import User
from app.pipeline.coordinator import coordinator
from app.pipeline.task_queue import task_manager
from app.services.quality_evaluator import QualityEvaluator


async def _database_available() -> bool:
    try:
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _await_task(task_id: str) -> dict:
    task = task_manager.get_task(task_id)
    assert task is not None
    await task._future
    status = task_manager.get_task_status(task_id)
    assert status is not None
    assert status["status"] == "completed", status
    return status


@pytest.mark.integration
async def test_full_novel_pipeline_is_repeatable(monkeypatch):
    if not await _database_available():
        pytest.skip("PostgreSQL is not available")

    async def fake_worldbuilding(_self, _inputs, on_token):
        on_token('{"setting_document":"测试世界"}')
        return {
            "setting_document": "灵力受月相影响的修仙世界。",
            "constraints": {"hard": ["凡人不可凭空飞行"], "soft": ["叙事克制"]},
            "conflict_seeds": [{"name": "旧伤", "description": "月圆发烫", "stake": "身世"}],
        }

    async def fake_skeleton(_self, inputs, on_progress=None):
        assert inputs["project_id"]
        return {
            "volumes": [
                {
                    "title": f"第{number}卷",
                    "core_conflict": f"冲突{number}",
                    "character_arc_stage": "成长",
                    "volume_summary": "推进主线",
                    "opening_state": "未知",
                    "ending_state": "变化",
                    "handoff_hook": "下一卷",
                    "must_resolve": [f"线索{number}"],
                }
                for number in range(1, 4)
            ],
            "foreshadowing_registry": [
                {
                    "name": "左手伤痕",
                    "description": "月圆发烫",
                    "sow_chapter_hint": 1,
                    "reap_chapter_hint": 8,
                }
            ],
        }

    async def fake_batch(_self, inputs, on_progress=None):
        return {
            "chapters": [
                {
                    "number": number,
                    "volume": inputs["volume"]["number"],
                    "title": f"第{number}章测试",
                    "goal": f"推进第{number}章",
                    "key_events": [{"event_name": "发现", "brief": "旧伤出现异常"}],
                    "pov_character": "林远",
                    "foreshadowing_seeds": [],
                }
                for number in range(inputs["batch_start"], inputs["batch_end"] + 1)
            ],
            "foreshadowing_additions": [],
        }

    async def fake_chapter(_self, inputs, on_progress=None):
        number = inputs["chapter"]["number"]
        return [
            {
                "chapter_number": number,
                "scene_number": 1,
                "scene_title": f"第{number}章场景",
                "narrative_goal": inputs["chapter"]["goal"],
                "scene_function": "progression",
                "pov_character": "林远",
                "characters_present": ["林远"],
                "character_emotional_states": {"林远": "警惕"},
                "opening_emotion": "平静",
                "closing_emotion": "不安",
                "emotional_beats": ["发现异常"],
                "reader_should_know": ["旧伤与月相有关"],
                "reader_should_not_know": ["旧伤来源"],
                "prose_directives": ["动作具体"],
                "forbidden_elements": ["只见"],
                "word_budget": 800,
            }
        ]

    async def fake_quality(_self, _content, chapter_number, constraint=None):
        return {
            "chapter_number": chapter_number,
            "evaluation_status": "completed",
            "overall_score": 2.5,
            "max_score": 5,
            "dimension_scores": {"continuity": {"score": 2, "label": "连贯性"}},
            "weak_spots": [{"dimension": "continuity", "score": 2, "label": "连贯性"}],
            "needs_human_review": True,
            "verdict": "需人工审查",
        }

    monkeypatch.setattr(WorldbuildingAgent, "run_stream", fake_worldbuilding)
    monkeypatch.setattr(OutlineSkeletonAgent, "run", fake_skeleton)
    monkeypatch.setattr(OutlineChapterBatchAgent, "run", fake_batch)
    monkeypatch.setattr(ChapterAgent, "run", fake_chapter)
    monkeypatch.setattr(QualityEvaluator, "evaluate", fake_quality)
    monkeypatch.setattr(
        coordinator.writer,
        "write_scene",
        AsyncMock(return_value="林远按住发烫的左手伤痕，月光正落在石阶上。"),
    )
    monkeypatch.setattr(
        coordinator.reviewer,
        "review",
        AsyncMock(return_value={"status": "pass", "issues": [], "summary": "通过"}),
    )

    user_id = uuid4()
    async with async_session_maker() as db:
        db.add(
            User(
                id=user_id,
                email=f"e2e-{user_id}@example.com",
                username="e2e",
                password_hash="not-used",
            )
        )
        await db.commit()

    app.dependency_overrides[get_current_user] = lambda: str(user_id)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={
                    "title": "全链路验收",
                    "core_idea": "杂灵根弟子调查左手旧伤并改变宗门",
                    "genre": "玄幻",
                    "tone_style": "克制",
                    "target_word_count": 30000,
                    "target_chapter_count": 10,
                },
            )
            assert response.status_code == 201, response.text
            project_id = response.json()["id"]

            world = await client.post(f"/api/projects/{project_id}/worldbuilding", json={})
            assert world.status_code == 200, world.text
            await _await_task(world.json()["task_id"])

            outline = await client.post(f"/api/projects/{project_id}/outline", json={})
            assert outline.status_code == 200, outline.text
            await _await_task(outline.json()["task_id"])

            chapters_response = await client.get(f"/api/projects/{project_id}/chapters")
            chapters = chapters_response.json()
            assert [chapter["chapter_number"] for chapter in chapters] == [1, 2, 3, 4, 5]
            chapter1, chapter2 = chapters[0], chapters[1]

            expand1 = await client.post(
                f"/api/projects/{project_id}/chapters/{chapter1['id']}/expand",
                json={"regenerate": False},
            )
            await _await_task(expand1.json()["task_id"])
            scenes1 = (
                await client.get(
                    f"/api/projects/{project_id}/chapters/{chapter1['id']}/scenes"
                )
            ).json()
            assert len(scenes1) == 1

            write1 = await client.post(f"/api/v1/scenes/{scenes1[0]['id']}/write-auto")
            assert write1.status_code == 200, write1.text
            await _await_task(write1.json()["task_id"])

            reviews = (await client.get(f"/api/projects/{project_id}/reviews")).json()
            assert len(reviews) == 1
            versions = (
                await client.get(f"/api/chapters/{chapter1['id']}/content-versions")
            ).json()
            assert len(versions) == 1 and versions[0]["source"] == "ai"

            metrics_before_repeat = (
                await client.get(
                    f"/api/admin/metrics/summary?project_id={project_id}"
                )
            ).json()
            repeated_write = await client.post(
                f"/api/v1/scenes/{scenes1[0]['id']}/write-auto"
            )
            assert repeated_write.status_code == 200, repeated_write.text
            assert repeated_write.json()["task_id"] == write1.json()["task_id"]
            assert repeated_write.json()["status"] == "completed"
            repeated_versions = (
                await client.get(f"/api/chapters/{chapter1['id']}/content-versions")
            ).json()
            metrics_after_repeat = (
                await client.get(
                    f"/api/admin/metrics/summary?project_id={project_id}"
                )
            ).json()
            assert len(repeated_versions) == 1
            assert metrics_after_repeat["total_calls"] == metrics_before_repeat["total_calls"]
            assert metrics_after_repeat["total_cost"] == metrics_before_repeat["total_cost"]

            manual = await client.post(
                f"/api/v1/scenes/{scenes1[0]['id']}/save",
                json={"content": "林远重新检查伤痕，确认它只在月圆之夜发热。"},
            )
            assert manual.status_code == 200, manual.text
            versions = (
                await client.get(f"/api/chapters/{chapter1['id']}/content-versions")
            ).json()
            assert len(versions) == 2 and versions[0]["source"] == "manual"

            version_payload = (
                await client.get(f"/api/projects/{project_id}/outline/version")
            ).json()
            candidate_snapshot = deepcopy(version_payload["outline"])
            for chapter in candidate_snapshot["chapters"]:
                if chapter["number"] == 2:
                    chapter["title"] = "第2章重规划"
            candidate = await client.post(
                f"/api/projects/{project_id}/outline/replan",
                json={
                    "affected_from": 2,
                    "trigger": {"type": "manual_test", "description": "主角改变调查方向"},
                    "candidate_snapshot": candidate_snapshot,
                },
            )
            assert candidate.status_code == 200, candidate.text
            approved = await client.post(
                f"/api/projects/{project_id}/outline/replan-candidates/{candidate.json()['id']}/approve"
            )
            assert approved.status_code == 200, approved.text

            chapters = (await client.get(f"/api/projects/{project_id}/chapters")).json()
            chapter2 = next(chapter for chapter in chapters if chapter["chapter_number"] == 2)
            assert chapter2["title"] == "第2章重规划"

            expand2 = await client.post(
                f"/api/projects/{project_id}/chapters/{chapter2['id']}/expand",
                json={"regenerate": False},
            )
            await _await_task(expand2.json()["task_id"])
            scenes2 = (
                await client.get(
                    f"/api/projects/{project_id}/chapters/{chapter2['id']}/scenes"
                )
            ).json()
            write2 = await client.post(f"/api/v1/scenes/{scenes2[0]['id']}/write-auto")
            await _await_task(write2.json()["task_id"])

            task_rows = (await client.get(f"/api/projects/{project_id}/tasks")).json()
            assert len(task_rows) >= 2
    finally:
        app.dependency_overrides.clear()
        async with async_session_maker() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

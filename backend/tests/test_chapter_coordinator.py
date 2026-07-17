from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import app.pipeline.coordinator as coordinator_module
from app.models.constraints import SceneConstraint
from app.pipeline.coordinator import Coordinator


def _constraint(number: int) -> SceneConstraint:
    return SceneConstraint(
        chapter_number=1,
        scene_number=number,
        scene_title=f"场景{number}",
        narrative_goal=f"推进{number}",
        scene_function="progression",
        pov_character="陆衡",
        characters_present=["陆衡"],
        character_emotional_states={"陆衡": "警觉"},
        opening_emotion="警觉",
        closing_emotion="紧张",
        emotional_beats=[f"推进{number}"],
        reader_should_know=[f"事实{number}"],
        reader_should_not_know=[],
        reader_experience_goal="异常升级",
        prose_directives=[],
        forbidden_elements=[],
        word_budget=800,
    )


async def test_chapter_coordinator_repairs_at_most_once():
    coordinator = Coordinator()
    coordinator.chapter_writer = MagicMock()
    coordinator.chapter_writer.build_prompt.return_value = "章级提示"
    first = "<!-- SCENE:1 -->\n初稿一。\n<!-- SCENE:2 -->\n初稿二。"
    repaired = "<!-- SCENE:1 -->\n修订一。\n<!-- SCENE:2 -->\n修订二。"
    coordinator.chapter_writer.write_chapter = AsyncMock(side_effect=[first, repaired])
    coordinator.reviewer = MagicMock()
    coordinator.reviewer.review_chapter = AsyncMock(side_effect=[
        {
            "status": "needs_rewrite",
            "issues": [{"severity": "critical", "description": "整章字数不足"}],
        },
        {"status": "pass", "issues": [], "style_review": {}},
    ])

    result = await coordinator.run_chapter_writing_flow(
        chapter_title="江底隧道",
        constraints=[_constraint(1), _constraint(2)],
        project_id="project-1",
        chapter_number=1,
    )

    assert coordinator.chapter_writer.write_chapter.await_count == 2
    second_call = coordinator.chapter_writer.write_chapter.await_args_list[1].kwargs
    assert second_call["previous_content"] == first
    assert second_call["issues"][0]["description"] == "整章字数不足"
    assert result["revision_count"] == 1
    assert result["segments"] == {1: "修订一。", 2: "修订二。"}


async def test_chapter_coordinator_stops_after_failed_repair():
    coordinator = Coordinator()
    coordinator.chapter_writer = MagicMock()
    coordinator.chapter_writer.build_prompt.return_value = "章级提示"
    draft = "<!-- SCENE:1 -->\n仍需人工处理。"
    coordinator.chapter_writer.write_chapter = AsyncMock(side_effect=[draft, draft])
    coordinator.reviewer = MagicMock()
    coordinator.reviewer.review_chapter = AsyncMock(return_value={
        "status": "needs_rewrite",
        "issues": [{"severity": "critical", "description": "仍然超长"}],
    })

    result = await coordinator.run_chapter_writing_flow(
        chapter_title="江底隧道",
        constraints=[_constraint(1)],
        project_id="project-1",
        chapter_number=1,
    )

    assert coordinator.chapter_writer.write_chapter.await_count == 2
    assert result["passed"] is False
    assert result["revision_count"] == 1


async def test_chapter_coordinator_reserves_and_settles_each_llm_call(monkeypatch):
    coordinator = Coordinator()
    coordinator.chapter_writer = MagicMock()
    coordinator.chapter_writer.build_prompt.return_value = "章级提示"
    coordinator.chapter_writer.write_chapter = AsyncMock(
        return_value="<!-- SCENE:1 -->\n正文。"
    )
    coordinator.reviewer = MagicMock()
    coordinator.reviewer.review_chapter = AsyncMock(
        return_value={"status": "pass", "issues": [], "style_review": {}}
    )
    observer = SimpleNamespace(check_budget=AsyncMock(), record=AsyncMock())
    monkeypatch.setattr(coordinator_module, "LLMCallObserver", observer)

    await coordinator.run_chapter_writing_flow(
        chapter_title="江底隧道",
        constraints=[_constraint(1)],
        project_id="project-1",
        chapter_number=1,
        db=MagicMock(),
    )

    assert observer.check_budget.await_count == 2
    assert observer.record.await_count == 2
    assert [
        call.kwargs["agent"] for call in observer.record.await_args_list
    ] == ["chapter-writer", "chapter-reviewer"]

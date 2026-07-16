from unittest.mock import AsyncMock

import pytest

from app.llm.exceptions import LLMError
from app.models.constraints import SceneConstraint
from app.pipeline.coordinator import Coordinator


def _constraint() -> SceneConstraint:
    return SceneConstraint(
        chapter_number=1,
        scene_number=1,
        scene_title="测试",
        narrative_goal="推进",
        scene_function="progression",
        pov_character="林远",
        characters_present=["林远"],
        character_emotional_states={"林远": "平静"},
        opening_emotion="平静",
        closing_emotion="警惕",
        emotional_beats=["发现"],
        reader_should_know=[],
        reader_should_not_know=[],
        prose_directives=[],
        forbidden_elements=[],
    )


async def test_coordinator_records_call_semantics_and_context_snapshot():
    coordinator = Coordinator()
    collector = AsyncMock()

    await coordinator._record_call(
        collector=collector,
        agent="writer",
        project_id="project-1",
        chapter_number=15,
        event_id="scene-1",
        prompt="prompt text",
        output="generated text",
        started=0.0,
        retry_count=0,
        call_type="recovery",
        context_snapshot_id="snapshot-1",
    )

    metric = collector.record_call.await_args.args[0]
    assert metric.call_type == "recovery"
    assert metric.context_snapshot_id == "snapshot-1"
    assert metric.project_id == "project-1"
    assert metric.total_tokens == metric.prompt_tokens + metric.completion_tokens


async def test_coordinator_stops_when_reviewer_is_unavailable(monkeypatch):
    coordinator = Coordinator()
    coordinator.writer.write_scene = AsyncMock(return_value="场景正文")
    coordinator.reviewer.review = AsyncMock(
        return_value={"status": "error", "issues": [], "error": "provider unavailable"}
    )
    monkeypatch.setattr(
        "app.pipeline.coordinator.BudgetGuard.check_call_budget",
        AsyncMock(),
    )

    with pytest.raises(LLMError, match="Reviewer failed: provider unavailable"):
        await coordinator.run_writing_flow(
            _constraint(),
            project_id="project-1",
            chapter_number=1,
        )

    coordinator.writer.write_scene.assert_awaited_once()
    coordinator.reviewer.review.assert_awaited_once()

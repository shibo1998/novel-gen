from types import SimpleNamespace

from app.agents.reviewer import ReviewerAgent
from app.models.constraints import SceneConstraint


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


async def test_reviewer_llm_failure_is_not_reported_as_pass():
    reviewer = ReviewerAgent()

    async def failed_stream(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")
        yield

    reviewer.llm = SimpleNamespace(complete_stream=failed_stream)

    result = await reviewer.review("林远走进山门。", _constraint())

    assert result["status"] == "error"
    assert "provider unavailable" in result["error"]


async def test_reviewer_invalid_json_is_not_reported_as_pass():
    reviewer = ReviewerAgent()

    async def invalid_stream(*_args, **_kwargs):
        yield "not json"

    reviewer.llm = SimpleNamespace(complete_stream=invalid_stream)

    result = await reviewer.review("林远走进山门。", _constraint())

    assert result["status"] == "error"
    assert "invalid JSON" in result["error"]


def test_rewrite_hints_accept_llm_issue_schema():
    hints = ReviewerAgent()._build_rewrite_hints(
        [
            {
                "severity": "critical",
                "category": "continuity",
                "description": "角色在同一场景中出现在两个地点。",
                "suggestion": "删除冲突地点描写。",
            }
        ]
    )

    assert "[critical] continuity：角色在同一场景中出现在两个地点。" in hints
    assert "建议：删除冲突地点描写。" in hints

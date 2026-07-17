from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        reader_experience_goal="先压抑，后紧张，结尾不安",
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


async def test_reviewer_keeps_structured_style_review_diagnostic_only():
    reviewer = ReviewerAgent()
    reviewer._base_review = AsyncMock(
        return_value={
            "status": "pass",
            "issues": [],
            "style_review": {
                "dialogue_density": {"score": 3, "evidence": "两人见面后全由旁白概括。"},
                "pacing": {"score": 8, "evidence": "开头异常，中段升级。"},
                "colloquialism": {"score": 7, "evidence": "对白符合角色身份。"},
            },
        }
    )
    reviewer._detect_ai_patterns = lambda _content: []

    result = await reviewer.review("林远走进山门。", _constraint())

    assert result["status"] == "pass"
    assert result["style_review"]["dialogue_density"]["score"] == 3
    assert result["issues"] == []
    reviewer._base_review.assert_awaited_once()


async def test_reviewer_rejects_a_clear_word_budget_overrun():
    reviewer = ReviewerAgent()
    reviewer._base_review = AsyncMock(
        return_value={"status": "pass", "issues": [], "style_review": {}}
    )
    reviewer._detect_ai_patterns = lambda _content: []
    constraint = _constraint()
    constraint.word_budget = 1000

    result = await reviewer.review("字" * 1200, constraint)

    assert result["status"] == "needs_rewrite"
    assert result["issues"][0]["id"] == "WORD_BUDGET_OVERRUN"
    assert result["issues"][0]["severity"] == "critical"


def test_reviewer_prompt_requests_reader_experience_style_scores():
    constraint = _constraint()
    prompt = ReviewerAgent().jinja.get_template("reviewer.j2").render(
        content="林远走进山门。",
        chapter_number=1,
        scene_number=1,
        constraint_card=constraint,
        bible={},
        previous_summaries=[],
    )

    assert constraint.reader_experience_goal in prompt
    assert '"style_review"' in prompt
    assert "dialogue_density" in prompt
    assert "只作为作者诊断" in prompt


def test_reviewer_detects_high_confidence_narrative_templates():
    content = (
        "没人抬头。没人回头。没人把手机放下。"
        "他不知道的是，多年以后才明白这件事。由此可见，一切早有安排。"
    )

    issues = ReviewerAgent()._detect_ai_patterns(content)
    issue_ids = {issue["id"] for issue in issues}

    assert "SYMMETRIC_NEGATION" in issue_ids
    assert "AUTHOR_FOREKNOWLEDGE" in issue_ids
    assert "ESSAY_VOICE" in issue_ids

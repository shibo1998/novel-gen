from unittest.mock import AsyncMock

import pytest

from app.agents.chapter_writer import (
    ChapterSegmentationError,
    ChapterWriterAgent,
    chapter_budget_range,
    count_chapter_characters,
    split_chapter_draft,
)
from app.models.constraints import SceneConstraint


def _constraint(number: int, goal: str) -> SceneConstraint:
    return SceneConstraint(
        chapter_number=1,
        scene_number=number,
        scene_title=f"场景{number}",
        narrative_goal=goal,
        scene_function="progression",
        pov_character="陆衡",
        characters_present=["陆衡"],
        character_emotional_states={"陆衡": "疲惫"},
        opening_emotion="疲惫",
        closing_emotion="警觉",
        emotional_beats=[f"触发{number}", f"行动{number}", f"结果{number}"],
        reader_should_know=[f"事实{number}"],
        reader_should_not_know=[],
        reader_experience_goal="异常逐步逼近",
        prose_directives=[],
        forbidden_elements=[],
        word_budget=800,
        injected_previous=[{"chapter": 0, "scene": 1, "summary": "前情"}],
    )


def test_chapter_prompt_contains_all_scenes_and_one_total_budget():
    prompt = ChapterWriterAgent().build_prompt(
        chapter_number=1,
        chapter_title="江底隧道",
        constraints=[_constraint(1, "发现广播异常"), _constraint(2, "列车驶入陌生站台")],
    )

    assert "发现广播异常" in prompt
    assert "列车驶入陌生站台" in prompt
    assert "正文目标 2500 字" in prompt
    assert "不给单个场景分配字数" in prompt
    assert "<!-- SCENE:1 -->" in prompt
    assert "<!-- SCENE:2 -->" in prompt
    assert "word_budget" not in prompt


def test_chapter_repair_prompt_contains_previous_draft_and_issue():
    prompt = ChapterWriterAgent().build_prompt(
        chapter_number=1,
        chapter_title="江底隧道",
        constraints=[_constraint(1, "发现广播异常")],
        previous_content="# 第1章 江底隧道\n<!-- SCENE:1 -->\n旧稿正文",
        issues=[{"severity": "critical", "description": "正文超出章级预算"}],
    )

    assert "旧稿正文" in prompt
    assert "正文超出章级预算" in prompt
    assert "修订后重新输出完整章节" in prompt


def test_split_chapter_draft_removes_markers_and_preserves_heading():
    content = (
        "# 第1章 江底隧道\n\n"
        "<!-- SCENE:1 -->\n第一场正文。\n\n"
        "<!-- SCENE:2 -->\n第二场正文。"
    )

    segments = split_chapter_draft(content, [1, 2])

    assert segments == {
        1: "# 第1章 江底隧道\n\n第一场正文。",
        2: "第二场正文。",
    }
    assert "SCENE" not in "\n".join(segments.values())


@pytest.mark.parametrize(
    "content",
    [
        "<!-- SCENE:1 -->第一场正文。",
        "<!-- SCENE:2 -->第二场正文。<!-- SCENE:1 -->第一场正文。",
        "<!-- SCENE:1 --><!-- SCENE:2 -->第二场正文。",
    ],
)
def test_split_chapter_draft_rejects_ambiguous_markers(content):
    with pytest.raises(ChapterSegmentationError):
        split_chapter_draft(content, [1, 2])


def test_chapter_character_count_ignores_heading_markers_and_whitespace():
    content = "# 第1章 标题\n<!-- SCENE:1 -->\n甲 乙。\n<!-- SCENE:2 -->\n丙！"

    assert count_chapter_characters(content) == 5
    assert chapter_budget_range(2500) == (2300, 2700)


async def test_chapter_writer_uses_one_llm_stream(monkeypatch):
    writer = ChapterWriterAgent()
    writer.llm = AsyncMock()
    writer.llm.complete_stream = lambda *_args, **_kwargs: _stream("整章正文")

    result = await writer.write_chapter(
        chapter_number=1,
        chapter_title="江底隧道",
        constraints=[_constraint(1, "发现广播异常")],
    )

    assert result == "整章正文"


async def _stream(value: str):
    yield value

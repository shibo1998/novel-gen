from app.agents.template_environment import create_template_environment
from app.services.word_budget import CHAPTER_WORD_BUDGET, distribute_scene_word_budgets


def test_scene_word_budgets_evenly_split_the_fixed_chapter_total():
    scenes = [{"scene_number": number} for number in range(1, 4)]

    result = distribute_scene_word_budgets(scenes, CHAPTER_WORD_BUDGET)

    assert [scene["word_budget"] for scene in result] == [834, 833, 833]
    assert sum(scene["word_budget"] for scene in result) == 2500


def test_chapter_prompt_allocates_the_project_budget_across_scenes():
    prompt = create_template_environment().get_template("chapter.j2").render(
        chapter={
            "number": 1,
            "title": "归渊旧城",
            "goal": "主角发现异常",
            "key_events": [],
            "pov_character": "陆衡",
        },
        chapter_word_budget=2500,
        hard_constraints=[],
        soft_constraints=[],
        characters=[],
        relationships=[],
        due_foreshadowings=[],
        chapter_summaries=[],
        relevant_memories=[],
    )

    assert "本章正文目标：2500字" in prompt
    assert "展开为2-5个场景" in prompt
    assert "本章总字数固定为 2500 字" in prompt
    assert "所有场景之和必须恰好等于 2500" in prompt
    assert "禁止在 prose_directives 中指定字数、句长" in prompt
    assert "对话占比50%+" not in prompt
    assert "不负责逐句导演" in prompt
    assert "具体动作清单" in prompt

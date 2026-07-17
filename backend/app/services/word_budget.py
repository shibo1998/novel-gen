"""Fixed chapter word-budget rules shared by planning and writing."""

CHAPTER_WORD_BUDGET = 2500


def scene_word_budget_values(
    scene_count: int,
    total: int = CHAPTER_WORD_BUDGET,
) -> list[int]:
    """Split a chapter budget evenly while preserving the exact total."""
    if scene_count <= 0:
        return []
    base, remainder = divmod(total, scene_count)
    return [base + (1 if index < remainder else 0) for index in range(scene_count)]


def distribute_scene_word_budgets(
    scenes: list[dict],
    total: int = CHAPTER_WORD_BUDGET,
) -> list[dict]:
    budgets = scene_word_budget_values(len(scenes), total)
    return [
        {**scene, "word_budget": budget}
        for scene, budget in zip(scenes, budgets)
    ]

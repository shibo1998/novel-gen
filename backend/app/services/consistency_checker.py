"""Deterministic post-generation checks for scene constraint cards."""

from typing import Any


def check_due_foreshadowing_coverage(
    due_foreshadowings: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return warnings for due foreshadowings omitted by every generated scene."""
    covered_ids: set[str] = set()
    for scene in scenes:
        covered_ids.update(str(item) for item in scene.get("foreshadowing_ids", []) if item)
    warnings: list[dict[str, str]] = []
    for item in due_foreshadowings:
        foreshadowing_id = str(item.get("id", ""))
        name = str(item.get("name", ""))
        if foreshadowing_id in covered_ids:
            continue
        warnings.append(
            {
                "code": "due_foreshadowing_missing",
                "foreshadowing_id": foreshadowing_id,
                "name": name,
                "message": f"到期伏笔“{name}”未覆盖到任何场景约束卡",
            }
        )
    return warnings

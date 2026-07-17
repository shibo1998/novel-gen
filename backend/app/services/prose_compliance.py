from typing import Any

from app.pipeline.compliance import scan_text


def apply_scene_compliance(
    scene: Any,
    content: str,
    *,
    review_passed: bool,
    review_result: dict | None = None,
) -> dict:
    issues = scan_text(content)
    effective_passed = bool(review_passed) and not issues
    result = dict(review_result or {})
    result["passed"] = effective_passed
    result["compliance"] = {"passed": not issues, "issues": issues}
    scene.review_result = result
    scene.status = "confirmed" if effective_passed else "draft"
    return result


def apply_chapter_compliance(
    scenes: list[Any],
    content: str,
    *,
    review_passed: bool,
    review_result: dict | None = None,
) -> dict:
    """Apply one complete-chapter verdict to every planned scene."""
    issues = scan_text(content)
    effective_passed = bool(review_passed) and not issues
    result = dict(review_result or {})
    result["passed"] = effective_passed
    result["scope"] = "chapter"
    result["compliance"] = {"passed": not issues, "issues": issues}
    for scene in scenes:
        scene.review_result = dict(result)
        scene.status = "confirmed" if effective_passed else "draft"
    return result

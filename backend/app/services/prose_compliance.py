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

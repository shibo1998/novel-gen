"""Single chapter quality state transition policy."""


class ChapterQualityState:
    DRAFTING = "drafting"
    SCENE_PASSED = "scene_passed"
    QUALITY_SCORED = "quality_scored"
    CONFIRMED = "confirmed"
    NEEDS_HUMAN = "needs_human"

    @classmethod
    def after_scene_reviews(cls, scenes) -> str:
        if not scenes or any(scene.status not in ("confirmed", "completed") for scene in scenes):
            return cls.DRAFTING
        if any((scene.review_result or {}).get("passed") is not True for scene in scenes):
            return cls.NEEDS_HUMAN
        return cls.SCENE_PASSED

    @classmethod
    def after_quality_report(cls, report) -> str:
        if report.evaluation_status != "completed" or report.needs_human_review:
            return cls.NEEDS_HUMAN
        return cls.CONFIRMED

from types import SimpleNamespace

from app.services.chapter_quality_state import ChapterQualityState


def _scene(*, status="confirmed", review_result=None):
    return SimpleNamespace(status=status, review_result=review_result)


def test_missing_reviewer_pass_never_counts_as_scene_passed():
    state = ChapterQualityState.after_scene_reviews(
        [_scene(review_result={"status": "pass"})]
    )
    assert state == ChapterQualityState.NEEDS_HUMAN


def test_all_scenes_require_explicit_pass_true():
    state = ChapterQualityState.after_scene_reviews(
        [_scene(review_result={"passed": True}), _scene(review_result={"passed": True})]
    )
    assert state == ChapterQualityState.SCENE_PASSED


def test_unconfirmed_scene_remains_drafting_even_with_pass():
    state = ChapterQualityState.after_scene_reviews(
        [_scene(status="draft", review_result={"passed": True})]
    )
    assert state == ChapterQualityState.DRAFTING


def test_unavailable_quality_report_requires_human_review():
    report = SimpleNamespace(evaluation_status="unavailable", needs_human_review=False)
    assert ChapterQualityState.after_quality_report(report) == ChapterQualityState.NEEDS_HUMAN


def test_completed_quality_report_can_confirm_chapter():
    report = SimpleNamespace(evaluation_status="completed", needs_human_review=False)
    assert ChapterQualityState.after_quality_report(report) == ChapterQualityState.CONFIRMED

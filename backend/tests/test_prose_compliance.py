from types import SimpleNamespace

from app.services.prose_compliance import apply_chapter_compliance, apply_scene_compliance


def test_clean_reviewed_prose_is_confirmed():
    scene = SimpleNamespace(status="draft", review_result=None)
    result = apply_scene_compliance(
        scene, "暮色里，林远沿山路返回宗门。", review_passed=True
    )
    assert scene.status == "confirmed"
    assert result["passed"] is True
    assert result["compliance"] == {"passed": True, "issues": []}


def test_blocked_prose_stays_draft_and_persists_issues():
    scene = SimpleNamespace(status="draft", review_result=None)
    result = apply_scene_compliance(scene, "他抵达了中国。", review_passed=True)
    assert scene.status == "draft"
    assert result["passed"] is False
    assert result["compliance"]["issues"]


def test_manual_save_without_review_stays_draft():
    scene = SimpleNamespace(status="confirmed", review_result=None)
    result = apply_scene_compliance(scene, "这是干净的正文。", review_passed=False)
    assert scene.status == "draft"
    assert result["compliance"]["passed"] is True


def test_apply_chapter_compliance_uses_one_verdict_for_all_scenes():
    scenes = [SimpleNamespace(), SimpleNamespace()]

    result = apply_chapter_compliance(
        scenes,
        "这是干净的整章正文。",
        review_passed=True,
        review_result={"issues": []},
    )

    assert result["passed"] is True
    assert result["scope"] == "chapter"
    assert [scene.status for scene in scenes] == ["confirmed", "confirmed"]
    assert all(scene.review_result["scope"] == "chapter" for scene in scenes)

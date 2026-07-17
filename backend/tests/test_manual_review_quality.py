from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.api import writing


async def test_compliant_manual_review_restarts_chapter_quality(monkeypatch):
    chapter_id = uuid4()
    scene = SimpleNamespace(
        id=uuid4(),
        chapter_id=chapter_id,
        project_id=uuid4(),
        content="林远沿山路返回宗门。",
        constraint_card={},
        status="draft",
        review_result=None,
    )
    active_version = SimpleNamespace(id=uuid4(), chapter_id=chapter_id)
    reviewer = SimpleNamespace(
        review=AsyncMock(
            return_value={
                "status": "pass",
                "issues": [],
                "style_review": {
                    "pacing": {"score": 6, "evidence": "中段节奏平稳"}
                },
            }
        )
    )
    quality = AsyncMock(return_value=None)
    db = AsyncMock()

    monkeypatch.setattr(writing, "_get_owned_scene", AsyncMock(return_value=scene))
    monkeypatch.setattr(
        writing,
        "SceneConstraint",
        lambda **_kwargs: SimpleNamespace(chapter_number=1, injected_bible=None),
    )
    monkeypatch.setattr(writing, "ReviewerAgent", lambda: reviewer)
    monkeypatch.setattr(
        writing.ChapterContentVersionService,
        "get_active",
        AsyncMock(return_value=active_version),
    )
    monkeypatch.setattr(
        writing.QualityWorkflow,
        "evaluate_if_chapter_complete",
        quality,
    )
    monkeypatch.setattr(
        writing,
        "_resolve_reviewed_foreshadowings",
        AsyncMock(return_value=[]),
    )

    result = await writing.review_scene(scene.id, str(uuid4()), db)

    assert result["passed"] is True
    assert scene.status == "confirmed"
    assert scene.review_result["style_review"]["pacing"]["score"] == 6
    quality.assert_awaited_once_with(chapter_id, active_version)
    db.commit.assert_not_awaited()


async def test_failed_manual_review_does_not_run_quality(monkeypatch):
    scene = SimpleNamespace(
        id=uuid4(),
        chapter_id=uuid4(),
        project_id=uuid4(),
        content="林远沿山路返回宗门。",
        constraint_card={},
        status="draft",
        review_result=None,
    )
    reviewer = SimpleNamespace(
        review=AsyncMock(return_value={"status": "fail", "issues": ["continuity"]})
    )
    quality = MagicMock()
    db = AsyncMock()

    monkeypatch.setattr(writing, "_get_owned_scene", AsyncMock(return_value=scene))
    monkeypatch.setattr(
        writing,
        "SceneConstraint",
        lambda **_kwargs: SimpleNamespace(chapter_number=1, injected_bible=None),
    )
    monkeypatch.setattr(writing, "ReviewerAgent", lambda: reviewer)
    monkeypatch.setattr(
        writing.QualityWorkflow,
        "evaluate_if_chapter_complete",
        quality,
    )

    result = await writing.review_scene(scene.id, str(uuid4()), db)

    assert result["passed"] is False
    assert scene.status == "draft"
    quality.assert_not_called()

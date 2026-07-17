from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.api import writing


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


async def test_write_chapter_resolves_number_through_chapter_id(monkeypatch):
    project_id = uuid4()
    chapter_id = uuid4()
    scene = SimpleNamespace(
        id=uuid4(),
        project_id=project_id,
        chapter_id=chapter_id,
        scene_number=1,
        status="confirmed",
    )
    chapter = SimpleNamespace(
        id=chapter_id,
        project_id=project_id,
        chapter_number=7,
    )
    db = AsyncMock()
    db.execute.side_effect = [_scalar(chapter), _scalars([scene])]
    monkeypatch.setattr(
        writing,
        "_get_owned_scene",
        AsyncMock(return_value=scene),
    )

    result = await writing.write_chapter_auto(scene.id, str(uuid4()), db)

    assert result == {"task_id": None, "status": "completed", "scene_count": 0}
    assert db.execute.await_count == 2


async def test_apply_whole_chapter_result_persists_one_atomic_version(monkeypatch):
    project_id = uuid4()
    chapter_id = uuid4()
    snapshot_id = uuid4()
    scenes = [
        SimpleNamespace(id=uuid4(), scene_number=1),
        SimpleNamespace(id=uuid4(), scene_number=2),
    ]
    constraint_context = {
        "injected_bible": {},
        "injected_previous": None,
        "injected_foreshadowings": None,
        "injected_memories": None,
        "injected_plot_threads": None,
        "injected_chapter_summaries": None,
        "injected_world_rules": None,
        "injected_style": None,
    }
    constraints = [SimpleNamespace(**constraint_context), SimpleNamespace(**constraint_context)]
    flow_result = {
        "segments": {1: "第一场。", 2: "第二场。"},
        "content": "第一场。\n\n第二场。",
        "passed": True,
        "issues": [],
        "revision_count": 0,
        "style_review": {},
        "resolved_foreshadowing_ids": [],
        "entity_changes": [],
    }
    durable = SimpleNamespace(id=uuid4())
    version = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=version)
    evaluate = AsyncMock(return_value=None)
    monkeypatch.setattr(writing.ChapterContentVersionService, "create", create)
    monkeypatch.setattr(
        writing.QualityWorkflow,
        "evaluate_if_chapter_complete",
        evaluate,
    )
    monkeypatch.setattr(
        writing,
        "_resolve_reviewed_foreshadowings",
        AsyncMock(),
    )
    monkeypatch.setattr(
        writing,
        "apply_reviewed_bible_changes",
        AsyncMock(return_value=[]),
    )

    review_result, created_version = await writing._apply_whole_chapter_result(
        AsyncMock(),
        project_id=project_id,
        chapter_id=chapter_id,
        chapter_number=1,
        scenes=scenes,
        constraints=constraints,
        flow_result=flow_result,
        durable_task=durable,
        context_snapshot_id=snapshot_id,
    )

    assert [scene.content for scene in scenes] == ["第一场。", "第二场。"]
    assert [scene.status for scene in scenes] == ["confirmed", "confirmed"]
    create.assert_awaited_once()
    evaluate.assert_awaited_once_with(chapter_id, version)
    assert review_result["passed"] is True
    assert created_version is version


def test_chapter_idempotency_key_is_stable_and_fits_database_column():
    project_id = uuid4()
    snapshots = [uuid4() for _ in range(8)]

    first = writing._chapter_idempotency_key(project_id, 12, snapshots)
    repeated = writing._chapter_idempotency_key(project_id, 12, snapshots)
    changed = writing._chapter_idempotency_key(project_id, 12, snapshots[:-1])

    assert first == repeated
    assert first != changed
    assert len(first) <= 100


def test_assign_chapter_word_budgets_refreshes_old_constraint_cards():
    scenes = [
        SimpleNamespace(
            constraint_card={
                "word_budget": old_budget,
                "prose_directives": ["叙述保持克制口吻"],
            }
        )
        for old_budget in (1200, 1000, 1000)
    ]

    writing._assign_chapter_word_budgets(scenes)

    assert [scene.constraint_card["word_budget"] for scene in scenes] == [834, 833, 833]
    assert scenes[0].constraint_card["prose_directives"] == ["叙述保持克制口吻"]

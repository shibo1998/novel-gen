from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.agents.reviewer import ReviewerAgent
from app.services import reviewed_bible_changes


def test_reviewer_entity_changes_are_limited_to_injected_bible_names():
    constraint = SimpleNamespace(injected_bible={"lin_yuan": {"injury": "old"}})
    result = {
        "entity_changes": [
            {
                "entity_name": "lin_yuan",
                "updates": {"injury": "healed", "__private": "ignored"},
                "summary": "伤势痊愈",
            },
            {
                "entity_name": "unknown",
                "updates": {"identity": "invented"},
                "summary": "越权创建",
            },
        ]
    }

    changes = ReviewerAgent._validated_entity_changes(result, constraint)

    assert changes == [
        {
            "entity_name": "lin_yuan",
            "updates": {"injury": "healed"},
            "summary": "伤势痊愈",
        }
    ]


async def test_reviewed_bible_change_calls_temporal_version_manager(monkeypatch):
    project_id = uuid4()
    scene_id = uuid4()
    entity = SimpleNamespace(id=uuid4(), name="lin_yuan")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [entity]
    db = AsyncMock()
    db.execute.return_value = result
    apply_change = AsyncMock(return_value="version-1")
    monkeypatch.setattr(
        reviewed_bible_changes,
        "BibleVersionManager",
        lambda _db: SimpleNamespace(apply_change=apply_change),
    )

    versions = await reviewed_bible_changes.apply_reviewed_bible_changes(
        db,
        project_id=project_id,
        chapter_number=12,
        scene_id=scene_id,
        injected_bible={"lin_yuan": {"injury": "old"}},
        requested_changes=[
            {
                "entity_name": "lin_yuan",
                "updates": {"injury": "healed"},
                "summary": "伤势痊愈",
            }
        ],
    )

    assert versions == ["version-1"]
    apply_change.assert_awaited_once_with(
        str(entity.id),
        {"injury": "healed"},
        12,
        event_id=f"scene:{scene_id}",
        change_summary="伤势痊愈",
    )


async def test_unknown_reviewed_entity_is_ignored_without_database_query():
    db = AsyncMock()

    versions = await reviewed_bible_changes.apply_reviewed_bible_changes(
        db,
        project_id=uuid4(),
        chapter_number=3,
        scene_id=uuid4(),
        injected_bible={"lin_yuan": {}},
        requested_changes=[
            {"entity_name": "unknown", "updates": {"state": "changed"}}
        ],
    )

    assert versions == []
    db.execute.assert_not_awaited()

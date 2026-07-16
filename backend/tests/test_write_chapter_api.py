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


def test_chapter_idempotency_key_is_stable_and_fits_database_column():
    project_id = uuid4()
    snapshots = [uuid4() for _ in range(8)]

    first = writing._chapter_idempotency_key(project_id, 12, snapshots)
    repeated = writing._chapter_idempotency_key(project_id, 12, snapshots)
    changed = writing._chapter_idempotency_key(project_id, 12, snapshots[:-1])

    assert first == repeated
    assert first != changed
    assert len(first) <= 100

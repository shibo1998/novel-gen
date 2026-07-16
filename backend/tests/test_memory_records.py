from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models.domain import MemoryRecord
from app.services.memory_records import MemoryRecordStore


def _result(records):
    result = MagicMock()
    result.scalars.return_value.all.return_value = records
    return result


async def test_chapter_50_retrieves_salient_chapter_3_fact():
    project_id = uuid4()
    old_fact = MemoryRecord(
        id=uuid4(),
        project_id=project_id,
        memory_type="scene_event",
        content="林远发现月圆之夜左手伤痕会发烫。",
        summary="月圆之夜，林远左手伤痕发烫",
        chapter_number=3,
        salience=1.0,
        emotional_intensity=1.5,
        metadata_json={"scene_number": 2},
        content_hash="a" * 64,
        index_status="not_indexed",
    )
    recent_noise = MemoryRecord(
        id=uuid4(),
        project_id=project_id,
        memory_type="scene_event",
        content="林远在客栈吃了一顿饭。",
        summary="客栈吃饭",
        chapter_number=49,
        salience=0.1,
        emotional_intensity=0.0,
        metadata_json={"scene_number": 1},
        content_hash="b" * 64,
        index_status="not_indexed",
    )
    db = AsyncMock()
    db.execute.return_value = _result([recent_noise, old_fact])

    retrieved = await MemoryRecordStore(db).retrieve(
        project_id=project_id,
        current_chapter=50,
        query="月圆之夜 林远 异常 伤痕",
        limit=1,
    )

    assert retrieved[0]["chapter"] == 3
    assert "伤痕" in retrieved[0]["summary"]
    assert retrieved[0]["index_status"] == "not_indexed"


async def test_memory_add_is_idempotent_by_project_and_content_hash():
    project_id = uuid4()
    existing = MemoryRecord(
        id=uuid4(),
        project_id=project_id,
        memory_type="scene_event",
        content="相同事实",
        summary="相同事实",
        chapter_number=1,
        salience=0.5,
        emotional_intensity=0.5,
        metadata_json={},
        content_hash=MemoryRecordStore.content_hash("scene_event", "相同事实"),
        index_status="not_indexed",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.execute.return_value = result

    returned = await MemoryRecordStore(db).add(
        project_id=project_id,
        memory_type="scene_event",
        content="相同事实",
        chapter_number=1,
    )

    assert returned is existing
    db.add.assert_not_called()
    db.flush.assert_not_awaited()

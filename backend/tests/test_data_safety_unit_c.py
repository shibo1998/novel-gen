from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import tasks
from app.db import session as session_module
from app.models.domain import GenerationTask, MemoryRecord
from app.services.generation_task_store import GenerationTaskStore
from app.services.memory_records import MemoryRecordStore


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


async def test_request_session_commits_on_success(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(session_module, "async_session_maker", lambda: _SessionContext(db))

    dependency = session_module.get_db()
    assert await anext(dependency) is db
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


async def test_request_session_rolls_back_on_error(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(session_module, "async_session_maker", lambda: _SessionContext(db))

    dependency = session_module.get_db()
    assert await anext(dependency) is db
    with pytest.raises(RuntimeError, match="boom"):
        await dependency.athrow(RuntimeError("boom"))

    db.rollback.assert_awaited_once()


async def test_failed_generation_task_can_restart_in_place():
    task = SimpleNamespace(
        status="failed",
        phase="write",
        initial_attempt_count=1,
        error_code="KeyError",
        error_message="name",
        completed_at=object(),
        started_at=None,
        updated_at=None,
    )
    db = AsyncMock()

    await GenerationTaskStore(db).restart(task)

    assert task.status == "running"
    assert task.initial_attempt_count == 2
    assert task.error_code is None
    assert task.error_message is None
    assert task.completed_at is None
    assert task.started_at is not None
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_generation_task_start_reselects_after_conflict_safe_insert():
    existing = GenerationTask(
        id=uuid4(),
        task_id="existing-task",
        project_id=uuid4(),
        scene_id=uuid4(),
        context_snapshot_id=uuid4(),
        task_type="write-auto",
        phase="write",
        status="running",
        idempotency_key="same-key",
    )
    insert_result = MagicMock()
    selected_result = MagicMock()
    selected_result.scalar_one.return_value = existing
    db = AsyncMock()
    db.execute.side_effect = [insert_result, selected_result]

    returned = await GenerationTaskStore(db).start(
        task_id="new-racing-task",
        project_id=existing.project_id,
        scene_id=existing.scene_id,
        context_snapshot_id=existing.context_snapshot_id,
        task_type="write-auto",
        idempotency_key="same-key",
    )

    assert returned is existing
    assert db.execute.await_count == 2
    db.add.assert_not_called()


async def test_memory_add_reselects_winner_after_conflict(monkeypatch):
    project_id = uuid4()
    winner = MemoryRecord(
        id=uuid4(),
        project_id=project_id,
        memory_type="chapter_summary",
        content="同章摘要",
        summary="同章摘要",
        chapter_number=10,
        salience=0.5,
        emotional_intensity=0.5,
        metadata_json={},
        content_hash=MemoryRecordStore.content_hash("chapter_summary", "同章摘要"),
        index_status="indexed",
    )
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    insert_result = MagicMock()
    selected_result = MagicMock()
    selected_result.scalar_one.return_value = winner
    db = AsyncMock()
    db.execute.side_effect = [no_existing, insert_result, selected_result]
    monkeypatch.setattr(
        MemoryRecordStore,
        "_embed_for_index",
        AsyncMock(return_value=([0.0] * 1024, "indexed")),
    )

    returned = await MemoryRecordStore(db).add(
        project_id=project_id,
        memory_type="chapter_summary",
        content="同章摘要",
        chapter_number=10,
    )

    assert returned is winner
    assert db.execute.await_count == 3
    db.add.assert_not_called()


async def test_durable_task_status_wins_over_stale_json_state(monkeypatch):
    project_id = uuid4()
    durable = SimpleNamespace(
        task_id="task-1",
        project_id=project_id,
        scene_id=uuid4(),
        context_snapshot_id=uuid4(),
        phase="done",
        status="completed",
        error_message=None,
    )
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = durable
    db = AsyncMock()
    db.execute.return_value = query_result
    monkeypatch.setattr(
        tasks.task_manager,
        "get_task_status",
        lambda _task_id: {
            "task_id": "task-1",
            "status": "orphaned",
            "result": {"content": "done"},
            "error": "stale",
            "meta": {"project_id": str(project_id), "phase": "orphaned"},
        },
    )

    result = await tasks.get_task_status("task-1", str(uuid4()), db)

    assert result.status == "completed"
    assert result.error is None
    assert result.meta["phase"] == "done"

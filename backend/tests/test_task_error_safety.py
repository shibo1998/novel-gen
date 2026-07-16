from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx

from app.api import writing
from app.core.security import get_current_user
from app.core.task_errors import PUBLIC_TASK_ERROR, TASK_EXECUTION_FAILED
from app.db.session import get_db
from app.main import app
from app.pipeline.task_queue import STREAM_EVENT_ERROR, Task
from app.services.generation_task_store import GenerationTaskStore


async def test_live_task_failure_is_sanitized(monkeypatch):
    async def fail():
        raise RuntimeError("provider key sk-secret leaked")

    task = Task("task-1", fail(), stream=True)
    queue = task.subscribe()
    monkeypatch.setattr("app.pipeline.task_queue.task_manager._save", MagicMock())

    await task._run()
    event = await queue.get()

    assert task.error == PUBLIC_TASK_ERROR
    assert event.event == STREAM_EVENT_ERROR
    assert event.data == {"error": PUBLIC_TASK_ERROR, "error_code": TASK_EXECUTION_FAILED}


async def test_durable_task_failure_persists_only_public_error():
    db = AsyncMock()
    task = SimpleNamespace(task_id="task-2")

    await GenerationTaskStore(db).fail(task, RuntimeError("postgresql://secret"))

    assert task.error_code == TASK_EXECUTION_FAILED
    assert task.error_message == PUBLIC_TASK_ERROR
    db.flush.assert_awaited_once()


async def test_task_api_sanitizes_legacy_persisted_error():
    project_id = uuid4()
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = SimpleNamespace(id=project_id)
    tasks_result = MagicMock()
    tasks_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            task_id="legacy-task",
            scene_id=None,
            context_snapshot_id=None,
            task_type="write-auto",
            phase="write",
            status="failed",
            error_message="postgresql://user:password@internal/db",
            recovery_attempt_count=0,
            max_recovery_attempts=2,
            recovery_allowance=1.0,
            spent_cost=0.0,
            updated_at=None,
            completed_at=None,
        )
    ]
    db = AsyncMock()
    db.execute.side_effect = [project_result, tasks_result]

    async def override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = lambda: str(uuid4())
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/projects/{project_id}/tasks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["error"] == PUBLIC_TASK_ERROR
    assert response.json()[0]["error_code"] == TASK_EXECUTION_FAILED
    assert "password" not in response.text


async def test_writing_sse_does_not_return_internal_exception(monkeypatch):
    project_id = uuid4()
    scene = SimpleNamespace(project_id=project_id, constraint_card={})

    async def override_get_db():
        yield AsyncMock()

    async def fail_context(*_args, **_kwargs):
        raise RuntimeError("provider endpoint https://internal.example")

    app.dependency_overrides[get_current_user] = lambda: str(uuid4())
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(writing, "_get_owned_scene", AsyncMock(return_value=scene))
    monkeypatch.setattr(writing, "SceneConstraint", lambda **_kwargs: object())
    monkeypatch.setattr(writing, "_build_writing_context", fail_context)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/scenes/{uuid4()}/write", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert PUBLIC_TASK_ERROR in response.text
    assert "internal.example" not in response.text

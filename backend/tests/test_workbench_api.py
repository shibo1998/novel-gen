from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


async def _request(path: str, db: AsyncMock, user_id, *, method: str = "GET", json=None):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = lambda: str(user_id)
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=json)
    finally:
        app.dependency_overrides.clear()


async def test_project_chapters_return_real_ids_and_scene_counts():
    project_id = uuid4()
    user_id = uuid4()
    chapter_id = uuid4()
    chapter = SimpleNamespace(
        id=chapter_id,
        chapter_number=15,
        volume_number=1,
        title="禁地余波",
        status="expanded",
        word_count=1200,
        is_locked=False,
        active_content_version_id=uuid4(),
    )
    scenes = [
        SimpleNamespace(chapter_id=chapter_id),
        SimpleNamespace(chapter_id=chapter_id),
    ]
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar(SimpleNamespace(id=project_id)),
        _scalars([chapter]),
        _scalars(scenes),
    ]

    response = await _request(f"/api/projects/{project_id}/chapters", db, user_id)

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(chapter_id)
    assert response.json()[0]["scene_count"] == 2
    assert response.json()[0]["active_content_version_id"] is not None


async def test_project_task_list_hides_unowned_project():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(f"/api/projects/{project_id}/tasks", db, user_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


async def test_metrics_summary_hides_unowned_project():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(f"/api/admin/metrics/summary?project_id={project_id}", db, user_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


async def test_plot_thread_list_hides_unowned_project():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(f"/api/projects/{project_id}/plot-threads", db, user_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


async def test_plot_thread_create_validates_chapter_range_for_owned_project():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(SimpleNamespace(id=project_id))

    response = await _request(
        f"/api/projects/{project_id}/plot-threads",
        db,
        user_id,
        method="POST",
        json={
            "name": "旧伤之谜",
            "start_chapter": 10,
            "end_chapter": 5,
            "priority": 5,
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "end_chapter cannot precede start_chapter"}
    db.add.assert_not_called()


async def test_plot_thread_update_hides_unowned_thread():
    thread_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(
        f"/api/plot-threads/{thread_id}",
        db,
        user_id,
        method="PUT",
        json={"status": "resolved"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Plot thread not found"}

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


async def test_get_outline_returns_empty_result_when_not_generated():
    project_id = uuid4()
    user_id = uuid4()
    project = SimpleNamespace(id=project_id, user_id=user_id)
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(project),
        _scalars_result([]),
        _scalars_result([]),
    ]

    async def override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = lambda: str(user_id)
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/projects/{project_id}/outline")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "volumes": [],
        "chapters": [],
        "foreshadowing_registry": [],
    }


async def test_get_outline_returns_not_found_when_project_does_not_exist():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar_result(None)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = lambda: str(user_id)
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/projects/{project_id}/outline")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}

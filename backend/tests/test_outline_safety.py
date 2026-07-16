from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.outline import trigger_outline
from app.models.schemas import OutlineRequest


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _project(project_id, user_id):
    return SimpleNamespace(
        id=project_id,
        user_id=user_id,
        data={"setting_document": "world", "constraints": {"hard": [], "soft": []}},
        target_chapter_count=90,
    )


async def test_existing_outline_requires_explicit_regeneration():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(_project(project_id, user_id)),
        _scalars_result([SimpleNamespace(id=uuid4())]),
        _scalars_result([]),
    ]

    with pytest.raises(HTTPException) as exc:
        await trigger_outline(
            project_id,
            OutlineRequest(regenerate=False),
            str(user_id),
            db,
        )

    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


async def test_regeneration_is_blocked_after_writing_started():
    project_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(_project(project_id, user_id)),
        _scalars_result([SimpleNamespace(id=uuid4())]),
        _scalars_result([SimpleNamespace(word_count=100, status="writing")]),
    ]

    with pytest.raises(HTTPException) as exc:
        await trigger_outline(
            project_id,
            OutlineRequest(regenerate=True),
            str(user_id),
            db,
        )

    assert exc.value.status_code == 409
    assert "writing has started" in exc.value.detail

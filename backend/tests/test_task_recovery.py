from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.tasks import recover_task


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


async def test_completed_task_cannot_be_recovered():
    db = AsyncMock()
    db.execute.return_value = _result(
        SimpleNamespace(
            scene_id=uuid4(),
            context_snapshot_id=uuid4(),
            status="completed",
            recovery_attempt_count=0,
            max_recovery_attempts=2,
        )
    )

    with pytest.raises(HTTPException) as exc:
        await recover_task("task-1", str(uuid4()), db)

    assert exc.value.status_code == 409
    assert exc.value.detail == "Task is not recoverable"


async def test_recovery_attempt_limit_is_enforced():
    db = AsyncMock()
    db.execute.return_value = _result(
        SimpleNamespace(
            scene_id=uuid4(),
            context_snapshot_id=uuid4(),
            status="failed",
            recovery_attempt_count=2,
            max_recovery_attempts=2,
        )
    )

    with pytest.raises(HTTPException) as exc:
        await recover_task("task-1", str(uuid4()), db)

    assert exc.value.status_code == 409
    assert exc.value.detail == "Recovery attempt limit reached"

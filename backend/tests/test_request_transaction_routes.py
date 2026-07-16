from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import auth
from app.models.schemas import UserCreate


async def test_register_does_not_commit_before_response_preparation(monkeypatch):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = result
    db.refresh.side_effect = RuntimeError("response preparation failed")
    monkeypatch.setattr(auth, "hash_password", lambda _password: "hashed")

    with pytest.raises(RuntimeError, match="response preparation failed"):
        await auth.register(
            UserCreate(
                email="atomic@example.com",
                username="atomic",
                password="long-enough-password",
            ),
            db,
        )

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()

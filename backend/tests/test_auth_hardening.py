from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException
from jose import jwt

from app.api import auth as auth_api
from app.api.auth import LoginThrottle
from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_token,
)
from app.db.session import get_db
from app.main import app
from app.models.schemas import UserCreate


async def _unused_db() -> AsyncIterator[AsyncMock]:
    yield AsyncMock()


async def test_query_token_is_not_accepted_for_protected_endpoint():
    token = create_access_token({"sub": "user-1"})
    app.dependency_overrides[get_db] = _unused_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/auth/me?token={token}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize(
    ("decoder", "expected_detail"),
    [
        (verify_token, "Invalid authentication credentials"),
        (decode_refresh_token, "Invalid refresh token"),
    ],
)
def test_malformed_jwt_returns_stable_generic_error(decoder, expected_detail):
    with pytest.raises(HTTPException) as exc_info:
        decoder("not.a.jwt")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == expected_detail
    assert "JWT" not in exc_info.value.detail


def test_access_and_refresh_tokens_use_configured_lifetimes(monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", 7)
    monkeypatch.setattr(settings, "refresh_token_expire_days", 11)
    before = datetime.now(timezone.utc).timestamp()

    access = jwt.get_unverified_claims(create_access_token({"sub": "user-1"}))
    refresh = jwt.get_unverified_claims(create_refresh_token({"sub": "user-1"}))

    assert 6 * 60 <= access["exp"] - before <= 7 * 60 + 2
    assert 10 * 86400 <= refresh["exp"] - before <= 11 * 86400 + 2


def test_registration_rejects_password_shorter_than_twelve_characters():
    with pytest.raises(ValueError):
        UserCreate(email="reader@example.com", username="reader", password="short-pass")


def test_login_throttle_blocks_repeated_failures_and_success_clears_account():
    now = [100.0]
    throttle = LoginThrottle(
        failure_limit=2,
        window_seconds=60,
        max_entries=10,
        clock=lambda: now[0],
    )

    throttle.record_failure("127.0.0.1", "reader@example.com")
    assert not throttle.is_blocked("127.0.0.1", "reader@example.com")
    throttle.clear_account("reader@example.com")
    assert not throttle.is_blocked("other-client", "reader@example.com")

    throttle.record_failure("127.0.0.1", "reader@example.com")
    assert throttle.is_blocked("127.0.0.1", "reader@example.com")
    assert not throttle.is_blocked("other-client", "reader@example.com")
    throttle.record_failure("other-client", "reader@example.com")
    assert throttle.is_blocked("other-client", "reader@example.com")

    now[0] += 61
    assert not throttle.is_blocked("127.0.0.1", "reader@example.com")


def test_login_throttle_keeps_storage_bounded():
    throttle = LoginThrottle(failure_limit=5, window_seconds=60, max_entries=4)

    for index in range(10):
        throttle.record_failure(f"client-{index}", f"user-{index}@example.com")

    assert throttle.entry_count <= 4


async def test_login_endpoint_returns_429_after_failure_limit(monkeypatch):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    async def override_get_db():
        yield db

    throttle = LoginThrottle(failure_limit=2, window_seconds=60, max_entries=10)
    monkeypatch.setattr(auth_api, "login_throttle", throttle)
    verify_password = MagicMock(return_value=False)
    monkeypatch.setattr(auth_api, "verify_password", verify_password)
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {"email": "reader@example.com", "password": "wrong-password"}
            first = await client.post("/api/auth/login", json=payload)
            second = await client.post("/api/auth/login", json=payload)
            blocked = await client.post("/api/auth/login", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == str(settings.login_failure_window_seconds)
    assert verify_password.call_count == 2

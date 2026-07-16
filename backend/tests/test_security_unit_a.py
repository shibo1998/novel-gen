"""单元 A 安全修复回归测试。

覆盖：
- 问题 10：实体端点 IDOR 越权 —— get/update entity 必须校验项目归属，
  非属主访问应返回 404（而非泄露/篡改他人数据）。
- 问题 11：启动安全校验 —— 生产环境默认密钥/弱口令拒绝启动，开发仅告警。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


async def _request(path: str, db, user_id, *, method: str = "GET", json=None):
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


# ── 问题 10：IDOR ────────────────────────────────────────────────


async def test_get_entity_of_unowned_project_returns_404():
    """他人项目的实体：归属过滤后查询返回 None → 404，不泄露数据。"""
    project_id = uuid4()
    entity_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(
        f"/api/projects/{project_id}/entities/{entity_id}", db, user_id
    )

    assert response.status_code == 404


async def test_update_entity_of_unowned_project_returns_404():
    """他人项目的实体 PUT：归属过滤后返回 None → 404，不允许篡改。"""
    project_id = uuid4()
    entity_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalar(None)

    response = await _request(
        f"/api/projects/{project_id}/entities/{entity_id}",
        db,
        user_id,
        method="PUT",
        json={"description": "hacked"},
    )

    assert response.status_code == 404
    # 越权路径不应触发写库提交
    db.commit.assert_not_called()


async def test_get_entity_owned_project_returns_data():
    """属主访问：归属过滤命中 → 正常返回实体。"""
    project_id = uuid4()
    entity_id = uuid4()
    user_id = uuid4()
    entity = SimpleNamespace(
        id=entity_id,
        project_id=project_id,
        type="character",
        name="li_yuan",
        display_name="李远",
        description="主角",
        data={},
        version=1,
        current_version_id=None,
        is_active=True,
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
    )
    db = AsyncMock()
    db.execute.return_value = _scalar(entity)

    response = await _request(
        f"/api/projects/{project_id}/entities/{entity_id}", db, user_id
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(entity_id)


# ── 问题 11：启动安全校验 ────────────────────────────────────────


def _make_settings(**overrides):
    from app.config import Settings

    base = dict(
        secret_key="x" * 40,
        db_password="a-strong-db-password",
        cors_origins="http://localhost:5173",
        environment="production",
    )
    base.update(overrides)
    return Settings(**base)


def test_production_rejects_default_secret_key():
    settings = _make_settings(secret_key="change-me-in-production")
    with pytest.raises(RuntimeError):
        settings.validate_security()


def test_production_rejects_weak_db_password():
    settings = _make_settings(db_password="novel123")
    with pytest.raises(RuntimeError):
        settings.validate_security()


def test_production_rejects_short_secret_key():
    settings = _make_settings(secret_key="tooshort")
    with pytest.raises(RuntimeError):
        settings.validate_security()


def test_production_passes_with_strong_values():
    settings = _make_settings()
    settings.validate_security()  # 不应抛异常


def test_development_only_warns_never_raises():
    settings = _make_settings(
        secret_key="change-me-in-production",
        db_password="novel123",
        environment="development",
    )
    # 开发环境即使全是默认值也放行
    settings.validate_security()
    assert settings.security_warnings()  # 但确实检测到了告警项

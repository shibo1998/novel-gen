import time
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from app.config import settings
from app.db.session import async_session_maker
from app.models.domain import CostReservation, Project, User
from app.services.budget_guard import BudgetExceededError
from app.services.cost_reservations import CostReservationService
from app.services.llm_observability import LLMCallObserver

pytestmark = pytest.mark.integration


async def _database_available() -> bool:
    try:
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
def generous_budget(monkeypatch):
    monkeypatch.setattr(settings, "max_cost_per_project", 10.0)
    monkeypatch.setattr(settings, "max_cost_per_chapter", 10.0)
    monkeypatch.setattr(settings, "budget_reservation_ttl_seconds", 600)


async def _create_project():
    user_id = uuid4()
    project_id = uuid4()
    async with async_session_maker() as db:
        db.add(
            User(
                id=user_id,
                email=f"budget-{user_id}@example.com",
                username="budget",
                password_hash="unused",
            )
        )
        await db.flush()
        db.add(
            Project(
                id=project_id,
                user_id=user_id,
                title="预算测试",
                core_idea="验证并发成本预留",
            )
        )
        await db.commit()
    return user_id, project_id


async def _cleanup_user(user_id):
    async with async_session_maker() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def test_active_reservation_blocks_a_second_call(monkeypatch):
    if not await _database_available():
        pytest.skip("PostgreSQL is not available")
    monkeypatch.setattr(settings, "max_cost_per_project", 1.0)
    monkeypatch.setattr(settings, "max_cost_per_chapter", 1.0)
    user_id, project_id = await _create_project()
    try:
        async with async_session_maker() as db:
            await CostReservationService(db).reserve(str(project_id), 1, 0.8)
            await db.commit()
        async with async_session_maker() as db:
            with pytest.raises(BudgetExceededError):
                await CostReservationService(db).reserve(str(project_id), 1, 0.3)
    finally:
        await _cleanup_user(user_id)


async def test_observer_settles_reservation_with_actual_cost(generous_budget):
    if not await _database_available():
        pytest.skip("PostgreSQL is not available")
    user_id, project_id = await _create_project()
    try:
        await LLMCallObserver.check_budget(
            str(project_id), 2, prompt="测试提示", expected_output_tokens=20
        )
        async with async_session_maker() as db:
            reservation = (
                await db.execute(
                    select(CostReservation).where(
                        CostReservation.project_id == project_id,
                        CostReservation.status == "reserved",
                    )
                )
            ).scalar_one()

        await LLMCallObserver.record(
            project_id=str(project_id),
            agent="TestAgent",
            prompt="测试提示",
            output="测试输出",
            started=time.perf_counter(),
            chapter_number=2,
        )

        async with async_session_maker() as db:
            settled = await db.get(CostReservation, reservation.id)
            assert settled.status == "settled"
            assert settled.actual_cost is not None
            assert settled.settled_at is not None
    finally:
        await _cleanup_user(user_id)

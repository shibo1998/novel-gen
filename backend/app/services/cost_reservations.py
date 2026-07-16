from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update

from app.config import settings
from app.models.domain import CostReservation, LLMCallMetric


class CostReservationService:
    def __init__(self, db):
        self.db = db

    async def reserve(
        self,
        project_id: str,
        chapter_number: int | None,
        estimated_cost: float,
    ) -> CostReservation:
        from app.services.budget_guard import BudgetExceededError

        project_uuid = UUID(project_id)
        now = datetime.utcnow()
        lock_key = project_uuid.int & ((1 << 63) - 1)
        await self.db.execute(
            select(func.pg_advisory_xact_lock(lock_key))
        )
        await self.db.execute(
            update(CostReservation)
            .where(
                CostReservation.project_id == project_uuid,
                CostReservation.status == "reserved",
                CostReservation.expires_at <= now,
            )
            .values(status="expired")
        )
        spent_project = await self._sum_metrics(project_uuid, None)
        reserved_project = await self._sum_reserved(project_uuid, None, now)
        if spent_project + reserved_project + estimated_cost > settings.max_cost_per_project:
            raise BudgetExceededError("Project budget would be exceeded by this call")
        if chapter_number is not None:
            spent_chapter = await self._sum_metrics(project_uuid, chapter_number)
            reserved_chapter = await self._sum_reserved(project_uuid, chapter_number, now)
            if spent_chapter + reserved_chapter + estimated_cost > settings.max_cost_per_chapter:
                raise BudgetExceededError("Chapter budget would be exceeded by this call")
        reservation = CostReservation(
            project_id=project_uuid,
            chapter_number=chapter_number,
            estimated_cost=max(0.0, estimated_cost),
            status="reserved",
            expires_at=now + timedelta(seconds=settings.budget_reservation_ttl_seconds),
        )
        self.db.add(reservation)
        await self.db.flush()
        return reservation

    async def settle(self, reservation_id: str, actual_cost: float) -> None:
        await self.db.execute(
            update(CostReservation)
            .where(
                CostReservation.id == UUID(reservation_id),
                CostReservation.status == "reserved",
            )
            .values(
                status="settled",
                actual_cost=max(0.0, actual_cost),
                settled_at=datetime.utcnow(),
            )
        )

    async def _sum_metrics(self, project_id: UUID, chapter_number: int | None) -> float:
        stmt = select(func.coalesce(func.sum(LLMCallMetric.cost_estimate), 0.0)).where(
            LLMCallMetric.project_id == project_id
        )
        if chapter_number is not None:
            stmt = stmt.where(LLMCallMetric.chapter_number == chapter_number)
        return float((await self.db.execute(stmt)).scalar_one())

    async def _sum_reserved(
        self, project_id: UUID, chapter_number: int | None, now: datetime
    ) -> float:
        stmt = select(func.coalesce(func.sum(CostReservation.estimated_cost), 0.0)).where(
            CostReservation.project_id == project_id,
            CostReservation.status == "reserved",
            CostReservation.expires_at > now,
        )
        if chapter_number is not None:
            stmt = stmt.where(CostReservation.chapter_number == chapter_number)
        return float((await self.db.execute(stmt)).scalar_one())

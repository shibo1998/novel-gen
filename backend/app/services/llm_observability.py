"""Shared budget checks and persisted metrics for non-Coordinator LLM calls."""

from __future__ import annotations

import json
import time
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from app.config import settings
from app.db.session import async_session_maker
from app.services.budget_guard import BudgetGuard
from app.services.cost_reservations import CostReservationService
from app.services.metrics_collector import LLMCallMetrics, MetricsCollector
from app.services.pricing import estimate_cost
from app.utils.tokens import count_tokens_pair

_active_reservation: ContextVar[str | None] = ContextVar(
    "active_llm_cost_reservation", default=None
)


class LLMCallObserver:
    @staticmethod
    async def check_budget(
        project_id: str | None,
        chapter_number: int | None = None,
        *,
        prompt: str = "",
        expected_output_tokens: int = 1200,
    ) -> None:
        _active_reservation.set(None)
        if not project_id:
            return
        # Deliberately isolated from the business transaction: attempted LLM spend must
        # remain observable even when the caller later rolls back its domain changes.
        async with async_session_maker() as db:
            collector = MetricsCollector(db)
            guard = BudgetGuard(collector)
            estimated_cost = estimate_cost(
                settings.llm_model,
                count_tokens_pair(prompt, "", settings.llm_model)[0],
                expected_output_tokens,
            )
            await guard.check_call_budget(project_id, chapter_number, estimated_cost)
            reservation = await CostReservationService(db).reserve(
                project_id, chapter_number, estimated_cost
            )
            await db.commit()
            _active_reservation.set(str(reservation.id))

    @staticmethod
    async def record(
        *,
        project_id: str | None,
        agent: str,
        prompt: str,
        output: Any,
        started: float,
        chapter_number: int | None = None,
        event_id: str | None = None,
        call_type: str = "initial",
        context_snapshot_id: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if not project_id:
            _active_reservation.set(None)
            return
        completion = output if isinstance(output, str) else json.dumps(
            output, ensure_ascii=False, default=str
        )
        prompt_tokens, completion_tokens = count_tokens_pair(prompt, completion, settings.llm_model)
        actual_cost = estimate_cost(settings.llm_model, prompt_tokens, completion_tokens)
        reservation_id = _active_reservation.get()
        # Metrics use an independent transaction by design so failed business work does
        # not erase cost/audit records for an LLM call that already happened.
        try:
            async with async_session_maker() as db:
                collector = MetricsCollector(db)
                await collector.record_call(
                    LLMCallMetrics(
                        timestamp=datetime.utcnow(),
                        agent=agent,
                        chapter_number=chapter_number or 0,
                        event_id=event_id,
                        model=settings.llm_model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        retry_count=0,
                        cost_estimate=actual_cost,
                        success=error is None,
                        error_type=type(error).__name__ if error else None,
                        project_id=project_id,
                        call_type=call_type,
                        context_snapshot_id=context_snapshot_id,
                    )
                )
                if reservation_id:
                    await CostReservationService(db).settle(reservation_id, actual_cost)
                await db.commit()
        finally:
            _active_reservation.set(None)

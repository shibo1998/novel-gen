"""Durable generation task and draft-attempt persistence."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.task_errors import PUBLIC_TASK_ERROR, TASK_EXECUTION_FAILED
from app.models.domain import GenerationTask, SceneDraftAttempt

logger = logging.getLogger(__name__)


class GenerationTaskStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def start(
        self,
        *,
        task_id: str,
        project_id: UUID,
        scene_id: UUID,
        context_snapshot_id: UUID,
        task_type: str,
        idempotency_key: str,
    ) -> GenerationTask:
        await self.db.execute(
            insert(GenerationTask)
            .values(
                task_id=task_id,
                project_id=project_id,
                scene_id=scene_id,
                context_snapshot_id=context_snapshot_id,
                task_type=task_type,
                phase="write",
                status="running",
                idempotency_key=idempotency_key,
                initial_attempt_count=1,
                max_recovery_attempts=settings.max_recovery_attempts,
                recovery_allowance=settings.scene_recovery_allowance,
                started_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing()
        )
        task = (
            await self.db.execute(
                select(GenerationTask).where(
                    (GenerationTask.task_id == task_id)
                    | (
                        (GenerationTask.project_id == project_id)
                        & (GenerationTask.idempotency_key == idempotency_key)
                    )
                )
            )
        ).scalar_one()
        return task

    async def get_by_idempotency(
        self,
        project_id: UUID,
        idempotency_key: str,
    ) -> GenerationTask | None:
        return (
            await self.db.execute(
                select(GenerationTask).where(
                    GenerationTask.project_id == project_id,
                    GenerationTask.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def save_attempt(
        self,
        task: GenerationTask,
        content: str,
        *,
        status: str,
        call_type: str,
        attempt_number: int,
        scene_id: UUID | None = None,
        context_snapshot_id: UUID | None = None,
    ) -> SceneDraftAttempt:
        attempt = SceneDraftAttempt(
            scene_id=scene_id or task.scene_id,
            task_id=task.id,
            context_snapshot_id=context_snapshot_id or task.context_snapshot_id,
            attempt_number=attempt_number,
            call_type=call_type,
            status=status,
            content=content,
        )
        self.db.add(attempt)
        task.checkpoint_json = {"partial_draft_text": content}
        task.updated_at = datetime.utcnow()
        await self.db.flush()
        return attempt

    async def archive_partial_draft(self, task: GenerationTask, content: str) -> None:
        """Archive partial output for diagnostics; recovery regenerates the full scene."""
        task.checkpoint_json = {"partial_draft_text": content}
        task.updated_at = datetime.utcnow()
        await self.db.flush()

    async def complete(self, task: GenerationTask) -> None:
        task.status = "completed"
        task.phase = "done"
        task.completed_at = datetime.utcnow()
        task.updated_at = task.completed_at
        await self.db.flush()

    async def restart(self, task: GenerationTask) -> None:
        """Restart a failed durable task in place while preserving its idempotency key."""
        task.status = "running"
        task.phase = "write"
        task.initial_attempt_count += 1
        task.error_code = None
        task.error_message = None
        task.completed_at = None
        task.started_at = datetime.utcnow()
        task.updated_at = task.started_at
        await self.db.flush()

    async def fail(self, task: GenerationTask, error: Exception) -> None:
        logger.error(
            "Generation task %s failed",
            task.task_id,
            exc_info=(type(error), error, error.__traceback__),
        )
        task.status = "failed"
        task.error_code = TASK_EXECUTION_FAILED
        task.error_message = PUBLIC_TASK_ERROR
        task.completed_at = datetime.utcnow()
        task.updated_at = task.completed_at
        await self.db.flush()

    async def mark_running_interrupted(self) -> int:
        result = await self.db.execute(
            update(GenerationTask)
            .where(GenerationTask.status == "running")
            .values(
                status="interrupted",
                error_code="ServerRestart",
                error_message="Task was interrupted by server restart and may be recovered.",
                updated_at=datetime.utcnow(),
            )
        )
        return result.rowcount or 0

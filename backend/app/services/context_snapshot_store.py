"""Create immutable writer-input snapshots for durable generation tasks."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.constraints import SceneConstraint
from app.models.domain import ContextSnapshot


class ContextSnapshotStore:
    """Persist and deduplicate the complete input used for a generation attempt."""

    SCHEMA_VERSION = 1

    def __init__(self, db: AsyncSession):
        self.db = db

    def build_payload(
        self,
        constraint: SceneConstraint,
        context: dict[str, Any],
        allocation_report: dict[str, Any],
        *,
        chapter_outline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "constraint_card_snapshot": constraint.model_dump(mode="json"),
            "memory_retrieval_frozen": context.get("memory_retrieval", []),
            "plot_thread_snapshot": context.get("injected_plot_threads", []),
            "bible_snapshot": context.get("injected_bible", {}),
            "previous_summary_snapshot": context.get("injected_previous", []),
            "foreshadowing_snapshot": context.get("injected_foreshadowings", []),
            "chapter_outline_frozen": chapter_outline or {},
            "context_budget_allocation": allocation_report,
            "prompt_version": settings.prompt_version,
            "model_id": settings.llm_model,
        }

    @staticmethod
    def digest(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def create_or_get(
        self,
        project_id: UUID,
        scene_id: UUID,
        payload: dict[str, Any],
    ) -> ContextSnapshot:
        digest = self.digest(payload)
        existing = (
            await self.db.execute(
                select(ContextSnapshot).where(
                    ContextSnapshot.project_id == project_id,
                    ContextSnapshot.digest == digest,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        snapshot = ContextSnapshot(
            project_id=project_id,
            scene_id=scene_id,
            schema_version=self.SCHEMA_VERSION,
            snapshot_json=payload,
            digest=digest,
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

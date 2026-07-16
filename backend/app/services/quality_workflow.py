"""Persist quality evaluation results and enqueue human review."""

import logging
import time

from sqlalchemy import select

from app.config import settings
from app.models.domain import (
    Chapter,
    ChapterContentVersion,
    DHOReplanCandidate,
    HumanReviewItem,
    Project,
    QualityReport,
    Scene,
)
from app.services.chapter_quality_state import ChapterQualityState
from app.services.dho import DHOService
from app.services.llm_observability import LLMCallObserver
from app.services.memory_records import MemoryRecordStore
from app.services.quality_evaluator import QualityEvaluator

logger = logging.getLogger(__name__)


class QualityWorkflow:
    EVALUATOR_VERSION = "v1"

    def __init__(self, db):
        self.db = db

    async def evaluate_if_chapter_complete(
        self, chapter_id, version: ChapterContentVersion
    ) -> tuple[QualityReport, HumanReviewItem | None] | None:
        chapter = (
            await self.db.execute(select(Chapter).where(Chapter.id == chapter_id))
        ).scalar_one()
        scenes = (
            await self.db.execute(select(Scene).where(Scene.chapter_id == chapter_id))
        ).scalars().all()
        chapter.quality_state = ChapterQualityState.after_scene_reviews(scenes)
        if not scenes or any(scene.status not in ("confirmed", "completed") for scene in scenes):
            return None
        await MemoryRecordStore(self.db).sync_chapter(chapter_id)
        return await self.evaluate_version(
            chapter,
            version,
            reviewer_results=[scene.review_result or {} for scene in scenes],
        )

    async def evaluate_version(
        self,
        chapter: Chapter,
        version: ChapterContentVersion,
        reviewer_results: list[dict] | None = None,
    ) -> tuple[QualityReport, HumanReviewItem | None]:
        project_id = str(chapter.project_id)
        await LLMCallObserver.check_budget(
            project_id,
            chapter.chapter_number,
            prompt=version.compiled_content,
            expected_output_tokens=1500,
        )
        started = time.perf_counter()
        result = await QualityEvaluator(project_id).evaluate(
            version.compiled_content, chapter.chapter_number
        )
        result["reviewer_results"] = reviewer_results or []
        evaluation_error = (
            RuntimeError("One or more quality dimensions were unavailable")
            if result.get("evaluation_status") == "unavailable"
            else None
        )
        await LLMCallObserver.record(
            project_id=project_id,
            agent="QualityEvaluator",
            prompt=version.compiled_content,
            output=result,
            started=started,
            chapter_number=chapter.chapter_number,
            error=evaluation_error,
        )
        report = QualityReport(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            chapter_content_version_id=version.id,
            chapter_number=chapter.chapter_number,
            overall_score=result["overall_score"],
            max_score=result["max_score"],
            dimension_scores=result["dimension_scores"],
            weak_spots=result["weak_spots"],
            needs_human_review=result["needs_human_review"],
            verdict=result["verdict"],
            evaluation_status=result.get("evaluation_status", "completed"),
            evaluator_version=self.EVALUATOR_VERSION,
            prompt_version=settings.prompt_version,
            error_json={
                "failed_dimensions": result.get("failed_dimensions", []),
                "reviewer_results": result.get("reviewer_results", []),
            },
        )
        self.db.add(report)
        await self.db.flush()
        chapter.quality_state = ChapterQualityState.after_quality_report(report)

        item = None
        if report.needs_human_review:
            item = HumanReviewItem(
                project_id=chapter.project_id,
                chapter_id=chapter.id,
                chapter_content_version_id=version.id,
                quality_report_id=report.id,
                item_type="quality_review",
                priority="high" if report.evaluation_status == "unavailable" else "normal",
                reason_json={
                    "verdict": report.verdict,
                    "weak_spots": report.weak_spots,
                    "evaluation_status": report.evaluation_status,
                    "quality_state": chapter.quality_state,
                },
            )
            self.db.add(item)
            await self.db.flush()
        await self._maybe_trigger_dho(chapter, report)
        return report, item

    async def _maybe_trigger_dho(self, chapter: Chapter, report: QualityReport) -> None:
        """Create one pending DHO candidate after severe measured outline drift."""
        if (
            report.evaluation_status != "completed"
            or report.overall_score is None
            or report.overall_score >= 2.5
        ):
            return
        project = (
            await self.db.execute(select(Project).where(Project.id == chapter.project_id))
        ).scalar_one()
        affected_from = chapter.chapter_number + 1
        if affected_from > project.target_chapter_count:
            return
        pending = (
            await self.db.execute(
                select(DHOReplanCandidate).where(
                    DHOReplanCandidate.project_id == chapter.project_id,
                    DHOReplanCandidate.status == "pending_review",
                )
            )
        ).scalar_one_or_none()
        if pending:
            return
        try:
            candidate = await DHOService(self.db).generate_candidate(
                project,
                trigger={
                    "type": "quality_drift",
                    "chapter": chapter.chapter_number,
                    "overall_score": report.overall_score,
                    "weak_spots": report.weak_spots,
                },
                affected_from=affected_from,
            )
            report.error_json = {
                **(report.error_json or {}),
                "dho_candidate_id": str(candidate.id),
            }
        except Exception as exc:
            logger.exception("Automatic DHO candidate generation failed: %s", exc)

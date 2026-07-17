"""Dynamic outline versioning with immutable candidates and explicit approval."""

import json
import time
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.template_environment import create_template_environment
from app.llm.client import collect_stream_text, get_llm_client
from app.models.domain import (
    Chapter,
    DHOReplanCandidate,
    Foreshadowing,
    OutlineVersion,
    Project,
    Scene,
    Volume,
)
from app.services.chapter_repository import ChapterRepository
from app.services.llm_observability import LLMCallObserver
from app.services.versioning_base import VersionedSnapshot


class DHOConflictError(Exception):
    pass


class DHOService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_client()
        self.jinja = create_template_environment()

    async def generate_candidate(
        self,
        project: Project,
        *,
        trigger: dict,
        affected_from: int,
        created_by: UUID | None = None,
    ) -> DHOReplanCandidate:
        base = await self.capture_current_outline(project, created_by=created_by)
        prompt = self.jinja.get_template("outline_replan.j2").render(
            current_outline=base.snapshot_json,
            trigger=trigger,
            affected_from=affected_from,
        )
        project_id = str(project.id)
        await LLMCallObserver.check_budget(project_id, affected_from, prompt=prompt)
        started = time.perf_counter()
        try:
            raw = await collect_stream_text(
                self.llm,
                prompt,
                system="你只能调整未写章节，并且必须返回有效 JSON。",
            )
            candidate_snapshot = self._parse_json(raw)
        except Exception as exc:
            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=prompt,
                output="",
                started=started,
                chapter_number=affected_from,
                error=exc,
            )
            raise
        await LLMCallObserver.record(
            project_id=project_id,
            agent=self.__class__.__name__,
            prompt=prompt,
            output=raw,
            started=started,
            chapter_number=affected_from,
        )
        return await self.create_candidate(
            project,
            trigger=trigger,
            candidate_snapshot=candidate_snapshot,
            affected_from=affected_from,
            created_by=created_by,
        )

    async def capture_current_outline(
        self, project: Project, *, created_by: UUID | None = None
    ) -> OutlineVersion:
        return await self.refresh_official_outline(
            project, source="sync", created_by=created_by
        )

    async def refresh_official_outline(
        self,
        project: Project,
        *,
        source: str,
        created_by: UUID | None = None,
    ) -> OutlineVersion:
        snapshot = await self._snapshot(project.id)
        digest = self._digest(snapshot)
        current = None
        if project.active_outline_version_id:
            current = (
                await self.db.execute(
                    select(OutlineVersion).where(
                        OutlineVersion.id == project.active_outline_version_id
                    )
                )
            ).scalar_one()
            if current.digest == digest:
                return current
        next_number = await VersionedSnapshot.next_number(
            self.db, OutlineVersion, OutlineVersion.project_id, project.id
        )
        version = OutlineVersion(
            project_id=project.id,
            version_number=next_number,
            parent_version_id=current.id if current else None,
            snapshot_json=snapshot,
            digest=digest,
            source=source,
            status="approved",
            created_by=created_by,
            approved_at=datetime.utcnow(),
        )
        self.db.add(version)
        await self.db.flush()
        if current:
            current.status = "archived"
        project.active_outline_version_id = version.id
        return version

    async def create_candidate(
        self,
        project: Project,
        *,
        trigger: dict,
        candidate_snapshot: dict,
        affected_from: int,
        created_by: UUID | None = None,
    ) -> DHOReplanCandidate:
        base = await self.capture_current_outline(project, created_by=created_by)
        self._validate_candidate(candidate_snapshot)
        self._assert_written_chapters_unchanged(base.snapshot_json, candidate_snapshot, affected_from)
        await self._assert_persisted_written_chapters_unchanged(
            project.id, base.snapshot_json, candidate_snapshot
        )
        diff = self.diff(base.snapshot_json, candidate_snapshot)
        candidate = DHOReplanCandidate(
            project_id=project.id,
            base_outline_version_id=base.id,
            trigger_json=trigger,
            affected_from=affected_from,
            affected_to=max((c.get("number", 0) for c in candidate_snapshot.get("chapters", [])), default=None),
            candidate_snapshot=candidate_snapshot,
            diff_json=diff,
            status="pending_review",
            created_by=created_by,
        )
        self.db.add(candidate)
        await self.db.flush()
        return candidate

    async def approve(self, project: Project, candidate: DHOReplanCandidate, user_id: UUID) -> OutlineVersion:
        project = (
            await self.db.execute(
                select(Project).where(Project.id == project.id).with_for_update()
            )
        ).scalar_one()
        candidate = (
            await self.db.execute(
                select(DHOReplanCandidate)
                .where(DHOReplanCandidate.id == candidate.id)
                .with_for_update()
            )
        ).scalar_one()
        if candidate.status != "pending_review":
            raise DHOConflictError("Candidate is no longer pending review")
        if project.active_outline_version_id != candidate.base_outline_version_id:
            raise DHOConflictError("Active outline changed after this candidate was created")

        base = (
            await self.db.execute(select(OutlineVersion).where(OutlineVersion.id == candidate.base_outline_version_id))
        ).scalar_one()
        self._assert_written_chapters_unchanged(
            base.snapshot_json, candidate.candidate_snapshot, candidate.affected_from
        )
        await self._assert_persisted_written_chapters_unchanged(
            project.id, base.snapshot_json, candidate.candidate_snapshot
        )
        next_number = await VersionedSnapshot.next_number(
            self.db, OutlineVersion, OutlineVersion.project_id, project.id
        )
        version = OutlineVersion(
            project_id=project.id,
            version_number=next_number,
            parent_version_id=base.id,
            snapshot_json=candidate.candidate_snapshot,
            digest=self._digest(candidate.candidate_snapshot),
            source="dho",
            status="approved",
            created_by=user_id,
            approved_at=datetime.utcnow(),
        )
        self.db.add(version)
        await self.db.flush()

        await ChapterRepository(self.db).apply_outline_snapshot(
            project.id,
            candidate.affected_from,
            candidate.candidate_snapshot.get("chapters", []),
        )

        base.status = "archived"
        project.active_outline_version_id = version.id
        candidate.status = "approved"
        candidate.applied_outline_version_id = version.id
        candidate.decided_by = user_id
        candidate.decided_at = datetime.utcnow()
        return version

    @staticmethod
    def diff(old: dict, new: dict) -> dict:
        old_map = {c["number"]: c for c in old.get("chapters", [])}
        new_map = {c["number"]: c for c in new.get("chapters", [])}
        return {
            "chapters_added": [new_map[n] for n in sorted(new_map.keys() - old_map.keys())],
            "chapters_removed": [old_map[n] for n in sorted(old_map.keys() - new_map.keys())],
            "chapters_modified": [
                {"number": n, "old": old_map[n], "new": new_map[n]}
                for n in sorted(old_map.keys() & new_map.keys())
                if old_map[n] != new_map[n]
            ],
        }

    @staticmethod
    def _assert_written_chapters_unchanged(old: dict, new: dict, affected_from: int) -> None:
        old_map = {c["number"]: c for c in old.get("chapters", [])}
        new_map = {c["number"]: c for c in new.get("chapters", [])}
        for number in old_map.keys() | new_map.keys():
            if number < affected_from and new_map.get(number) != old_map.get(number):
                raise DHOConflictError(f"Written chapter {number} cannot be changed")

    async def _assert_persisted_written_chapters_unchanged(
        self,
        project_id: UUID,
        old: dict,
        new: dict,
    ) -> None:
        chapters = (
            await self.db.execute(select(Chapter).where(Chapter.project_id == project_id))
        ).scalars().all()
        scenes = (
            await self.db.execute(
                select(Scene).where(
                    Scene.project_id == project_id,
                    Scene.content.isnot(None),
                )
            )
        ).scalars().all()
        chapters_with_content = {scene.chapter_id for scene in scenes if scene.content}
        protected_numbers = {
            chapter.chapter_number
            for chapter in chapters
            if chapter.is_locked
            or chapter.status in ("writing", "reviewing", "completed")
            or chapter.id in chapters_with_content
        }
        old_map = {item["number"]: item for item in old.get("chapters", [])}
        new_map = {item["number"]: item for item in new.get("chapters", [])}
        for number in protected_numbers:
            if new_map.get(number) != old_map.get(number):
                raise DHOConflictError(f"Written chapter {number} cannot be changed")

    @staticmethod
    def _validate_candidate(candidate: dict) -> None:
        chapters = candidate.get("chapters")
        if not isinstance(chapters, list):
            raise DHOConflictError("Candidate must contain a chapters list")
        numbers = [item.get("number") for item in chapters if isinstance(item, dict)]
        if len(numbers) != len(chapters) or any(
            not isinstance(number, int) or number < 1 for number in numbers
        ):
            raise DHOConflictError("Every candidate chapter needs a positive integer number")
        if len(set(numbers)) != len(numbers):
            raise DHOConflictError("Candidate chapter numbers must be unique")

    async def _snapshot(self, project_id: UUID) -> dict:
        volumes = (
            await self.db.execute(select(Volume).where(Volume.project_id == project_id).order_by(Volume.volume_number))
        ).scalars().all()
        chapters = (
            await self.db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number))
        ).scalars().all()
        foreshadowings = (
            await self.db.execute(select(Foreshadowing).where(Foreshadowing.project_id == project_id))
        ).scalars().all()
        return {
            "volumes": [
                {"number": v.volume_number, "title": v.title, "contract": v.contract}
                for v in volumes
            ],
            "chapters": [
                {"number": c.chapter_number, "title": c.title, **(c.outline or {})}
                for c in chapters
            ],
            "foreshadowing_registry": [
                {"id": str(f.id), "name": f.name, "status": f.status}
                for f in foreshadowings
            ],
        }

    @staticmethod
    def _digest(snapshot: dict) -> str:
        return VersionedSnapshot.digest(snapshot)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text_value = raw.strip()
        if text_value.startswith("```json"):
            text_value = text_value[7:]
        elif text_value.startswith("```"):
            text_value = text_value[3:]
        if text_value.endswith("```"):
            text_value = text_value[:-3]
        parsed = json.loads(text_value.strip())
        if not isinstance(parsed.get("chapters"), list):
            raise ValueError("Replanned outline must contain a chapters list")
        return parsed

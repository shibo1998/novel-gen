"""Versioned project style profiles."""

import hashlib
from uuid import UUID

from sqlalchemy import func, select

from app.models.domain import Project, ProjectStyleVersion
from app.services.style_analyzer import StyleAnalyzer


class ProjectStyleService:
    def __init__(self, db):
        self.db = db

    async def create_from_sample(
        self, project: Project, sample: str, created_by: UUID
    ) -> ProjectStyleVersion:
        profile = await StyleAnalyzer().analyze_text(sample)
        next_number = (
            await self.db.execute(
                select(func.coalesce(func.max(ProjectStyleVersion.version_number), 0)).where(
                    ProjectStyleVersion.project_id == project.id
                )
            )
        ).scalar_one() + 1
        version = ProjectStyleVersion(
            project_id=project.id,
            version_number=next_number,
            profile_json=profile.to_dict(),
            sample_hash=hashlib.sha256(sample.encode("utf-8")).hexdigest(),
            created_by=created_by,
        )
        self.db.add(version)
        await self.db.flush()
        project.active_style_version_id = version.id
        return version

    async def activate(self, project: Project, version: ProjectStyleVersion) -> None:
        if version.project_id != project.id:
            raise ValueError("Style version does not belong to project")
        project.active_style_version_id = version.id

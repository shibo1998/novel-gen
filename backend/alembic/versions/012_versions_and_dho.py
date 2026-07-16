"""Add immutable content/outline versions and DHO candidates.

Revision ID: 012
Revises: 011
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outline_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("project_id", "version_number", name="uq_outline_versions_project_number"),
    )
    op.create_index("idx_outline_versions_project_status", "outline_versions", ["project_id", "status"])
    op.create_foreign_key(
        "fk_outline_versions_parent", "outline_versions", "outline_versions",
        ["parent_version_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("projects", sa.Column("active_outline_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_projects_active_outline_version", "projects", "outline_versions",
        ["active_outline_version_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "chapter_content_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.UUID(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("scene_snapshot", sa.JSON(), nullable=False),
        sa.Column("compiled_content", sa.Text(), nullable=False),
        sa.Column("context_snapshot_id", sa.UUID(), sa.ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_task_id", sa.UUID(), sa.ForeignKey("generation_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("chapter_id", "version_number", name="uq_chapter_content_versions_number"),
    )
    op.create_foreign_key(
        "fk_chapter_content_versions_parent", "chapter_content_versions", "chapter_content_versions",
        ["parent_version_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("chapters", sa.Column("active_content_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_chapters_active_content_version", "chapters", "chapter_content_versions",
        ["active_content_version_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "dho_replan_candidates",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_outline_version_id", sa.UUID(), sa.ForeignKey("outline_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_json", sa.JSON(), nullable=False),
        sa.Column("affected_from", sa.Integer(), nullable=False),
        sa.Column("affected_to", sa.Integer(), nullable=True),
        sa.Column("candidate_snapshot", sa.JSON(), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.Column("applied_outline_version_id", sa.UUID(), sa.ForeignKey("outline_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_dho_candidates_project_status", "dho_replan_candidates", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_dho_candidates_project_status", table_name="dho_replan_candidates")
    op.drop_table("dho_replan_candidates")
    op.drop_constraint("fk_chapters_active_content_version", "chapters", type_="foreignkey")
    op.drop_column("chapters", "active_content_version_id")
    op.drop_table("chapter_content_versions")
    op.drop_constraint("fk_projects_active_outline_version", "projects", type_="foreignkey")
    op.drop_column("projects", "active_outline_version_id")
    op.drop_index("idx_outline_versions_project_status", table_name="outline_versions")
    op.drop_table("outline_versions")

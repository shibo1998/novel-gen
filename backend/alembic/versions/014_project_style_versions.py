"""Add versioned project style profiles.

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_style_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("sample_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "version_number", name="uq_project_style_version_number"),
    )
    op.add_column("projects", sa.Column("active_style_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_projects_active_style", "projects", "project_style_versions",
        ["active_style_version_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_active_style", "projects", type_="foreignkey")
    op.drop_column("projects", "active_style_version_id")
    op.drop_table("project_style_versions")

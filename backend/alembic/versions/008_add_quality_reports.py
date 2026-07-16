"""add quality_reports table

Revision ID: 008
Revises: 007
Create Date: 2026-07-14

存储每章的自动化质量评估结果。
"""
from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), nullable=False, index=True),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("dimension_scores", sa.JSON(), nullable=False),
        sa.Column("weak_spots", sa.JSON(), nullable=False),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "chapter_number", name="uq_quality_report_project_chapter"),
    )

    op.create_index("idx_quality_reports_chapter", "quality_reports", ["chapter_number"])


def downgrade() -> None:
    op.drop_index("idx_quality_reports_chapter", "quality_reports")
    op.drop_table("quality_reports")

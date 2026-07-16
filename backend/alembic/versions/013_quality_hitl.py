"""Version quality reports and add HITL queue.

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_quality_report_project_chapter", "quality_reports", type_="unique")
    op.alter_column("quality_reports", "overall_score", existing_type=sa.Float(), nullable=True)
    op.add_column("quality_reports", sa.Column("chapter_id", sa.UUID(), nullable=True))
    op.add_column("quality_reports", sa.Column("chapter_content_version_id", sa.UUID(), nullable=True))
    op.add_column("quality_reports", sa.Column("evaluation_status", sa.String(30), nullable=False, server_default="completed"))
    op.add_column("quality_reports", sa.Column("evaluator_version", sa.String(50), nullable=False, server_default="v1"))
    op.add_column("quality_reports", sa.Column("prompt_version", sa.String(50), nullable=True))
    op.add_column("quality_reports", sa.Column("error_json", sa.JSON(), nullable=True))
    op.add_column("quality_reports", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")))
    op.create_foreign_key("fk_quality_reports_chapter", "quality_reports", "chapters", ["chapter_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(
        "fk_quality_reports_content_version", "quality_reports", "chapter_content_versions",
        ["chapter_content_version_id"], ["id"], ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_quality_report_version_evaluator", "quality_reports",
        ["chapter_content_version_id", "evaluator_version"],
    )

    op.create_table(
        "human_review_items",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.UUID(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_content_version_id", sa.UUID(), sa.ForeignKey("chapter_content_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quality_report_id", sa.UUID(), sa.ForeignKey("quality_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("reason_json", sa.JSON(), nullable=False),
        sa.Column("assignee_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_human_review_project_status", "human_review_items", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_human_review_project_status", table_name="human_review_items")
    op.drop_table("human_review_items")
    op.drop_constraint("uq_quality_report_version_evaluator", "quality_reports", type_="unique")
    op.drop_constraint("fk_quality_reports_content_version", "quality_reports", type_="foreignkey")
    op.drop_constraint("fk_quality_reports_chapter", "quality_reports", type_="foreignkey")
    for column in (
        "updated_at", "error_json", "prompt_version", "evaluator_version",
        "evaluation_status", "chapter_content_version_id", "chapter_id",
    ):
        op.drop_column("quality_reports", column)
    op.alter_column("quality_reports", "overall_score", existing_type=sa.Float(), nullable=False)
    op.create_unique_constraint(
        "uq_quality_report_project_chapter", "quality_reports", ["project_id", "chapter_number"]
    )

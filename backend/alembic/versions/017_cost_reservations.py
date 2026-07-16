"""add persistent cost reservations

Revision ID: 017
Revises: 016
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("actual_cost", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="reserved"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_reservations_project_id", "cost_reservations", ["project_id"])
    op.create_index("ix_cost_reservations_chapter_number", "cost_reservations", ["chapter_number"])
    op.create_index("ix_cost_reservations_status", "cost_reservations", ["status"])
    op.create_index("ix_cost_reservations_expires_at", "cost_reservations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_cost_reservations_expires_at", table_name="cost_reservations")
    op.drop_index("ix_cost_reservations_status", table_name="cost_reservations")
    op.drop_index("ix_cost_reservations_chapter_number", table_name="cost_reservations")
    op.drop_index("ix_cost_reservations_project_id", table_name="cost_reservations")
    op.drop_table("cost_reservations")

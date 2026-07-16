"""Add call semantics and context snapshot linkage to LLM metrics.

Revision ID: 011
Revises: 010
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_call_metrics",
        sa.Column("call_type", sa.String(20), nullable=False, server_default="initial"),
    )
    op.add_column(
        "llm_call_metrics",
        sa.Column(
            "context_snapshot_id",
            sa.UUID(),
            sa.ForeignKey("context_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_call_metrics", "context_snapshot_id")
    op.drop_column("llm_call_metrics", "call_type")

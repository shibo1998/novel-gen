"""add chapter quality state

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chapters",
        sa.Column("quality_state", sa.String(length=30), nullable=False, server_default="drafting"),
    )


def downgrade() -> None:
    op.drop_column("chapters", "quality_state")

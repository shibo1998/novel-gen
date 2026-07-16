"""add target_chapter_count to projects table

Revision ID: 005
Revises: 004
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("target_chapter_count", sa.Integer(), nullable=False, server_default="90"),
    )


def downgrade() -> None:
    op.drop_column("projects", "target_chapter_count")

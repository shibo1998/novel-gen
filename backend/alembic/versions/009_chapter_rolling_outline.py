"""repair outline schema and add volume contracts

Revision ID: 009
Revises: 008
Create Date: 2026-07-14
"""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    foreshadowing_columns = _columns("foreshadowings")
    if "status" not in foreshadowing_columns:
        op.add_column(
            "foreshadowings",
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        )

    volume_columns = _columns("volumes")
    if "contract" not in volume_columns:
        op.add_column(
            "volumes",
            sa.Column("contract", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chapters_project_number "
        "ON chapters (project_id, chapter_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_chapters_project_number")
    if "contract" in _columns("volumes"):
        op.drop_column("volumes", "contract")
    # Keep foreshadowings.status because it may predate this repair and contain user state.

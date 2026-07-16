"""Preserve the historical target chapter count revision.

The column was already introduced by revision 003. This revision remains in the
chain as a no-op so fresh databases and installations that already applied 003
follow the same schema history without attempting to add the column twice.

Revision ID: 005
Revises: 004
Create Date: 2026-07-14

"""
# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

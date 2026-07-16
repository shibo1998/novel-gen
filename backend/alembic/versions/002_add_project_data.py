"""Add data column to projects

Revision ID: 002
Revises: 001
Create Date: 2026-07-13

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('data', sa.JSON, default=dict))


def downgrade() -> None:
    op.drop_column('projects', 'data')

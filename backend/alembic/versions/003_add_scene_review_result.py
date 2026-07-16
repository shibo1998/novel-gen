"""Add review_result to scenes

Revision ID: 003
Revises: 002
Create Date: 2026-07-13

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 两个字段都在 003 合并执行
    op.add_column('scenes', sa.Column('review_result', sa.JSON, nullable=True))
    op.add_column(
        'projects',
        sa.Column(
            'target_chapter_count',
            sa.Integer,
            nullable=False,
            server_default=sa.text('90'),
        ),
    )


def downgrade() -> None:
    op.drop_column('scenes', 'review_result')
    op.drop_column('projects', 'target_chapter_count')

"""Add volumes table and extend chapters/foreshadowings for rolling-outline

Revises: 003
Create Date: 2026-07-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. volumes 表（含显式主键 PK + 唯一约束） ────────────────
    op.create_table(
        'volumes',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('volume_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(100), nullable=True),
        sa.Column('core_conflict', sa.Text(), nullable=True),
        sa.Column('character_arc_stage', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('chapter_start', sa.Integer(), nullable=True),
        sa.Column('chapter_end', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_volumes_project_id', 'volumes', ['project_id'])
    op.create_primary_key('pk_volumes', 'volumes', ['id'])
    op.create_unique_constraint(
        'uq_volumes_project_number', 'volumes', ['project_id', 'volume_number']
    )
    op.create_foreign_key(
        'fk_volumes_project', 'volumes', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )

    # ── 2. chapters 扩展 ─────────────────────────────────────────
    op.add_column('chapters', sa.Column('volume_id', sa.UUID(), nullable=True))
    op.add_column('chapters', sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_foreign_key(
        'fk_chapters_volume', 'chapters', 'volumes',
        ['volume_id'], ['id'], ondelete='SET NULL'
    )

    # ── 3. foreshadowings 扩展 ───────────────────────────────────
    op.add_column('foreshadowings', sa.Column('sow_volume', sa.Integer(), nullable=True))
    op.add_column('foreshadowings', sa.Column('reap_volume', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_constraint('fk_chapters_volume', 'chapters', type_='foreignkey')
    op.drop_column('chapters', 'volume_id')
    op.drop_column('chapters', 'is_locked')
    op.drop_column('foreshadowings', 'sow_volume')
    op.drop_column('foreshadowings', 'reap_volume')
    op.drop_constraint('fk_volumes_project', 'volumes', type_='foreignkey')
    op.drop_constraint('uq_volumes_project_number', 'volumes', type_='unique')
    op.drop_index('ix_volumes_project_id', 'volumes')
    op.drop_table('volumes')

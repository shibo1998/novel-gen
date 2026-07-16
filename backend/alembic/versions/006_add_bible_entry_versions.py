"""add bible_entry_versions table

Revision ID: 006
Revises: 005
Create Date: 2026-07-14

Story Bible 时态版本表。每个 Bible 条目（角色/地点/规则/关系）
在剧情导致变化时创建新版本快照，确保写作时注入的是"本章生效的版本"。
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bible_entry_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entry_id", sa.UUID(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("json_snapshot", sa.JSON(), nullable=False),
        sa.Column("chapter_applied", sa.Integer(), nullable=False, index=True),
        sa.Column("event_applied", sa.String(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("previous_version_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    # 同一 entry 内版本号唯一
    op.create_index(
        "idx_bible_versions_entry_chapter",
        "bible_entry_versions",
        ["entry_id", "chapter_applied"],
    )
    op.create_index(
        "idx_bible_versions_entry_version",
        "bible_entry_versions",
        ["entry_id", "version_number"],
        unique=True,
    )

    # 给 entities 表加当前版本指针
    op.add_column("entities", sa.Column("current_version_id", sa.UUID(), nullable=True))
    op.add_column("entities", sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False))

    # foreshadowings 加状态字段（status 已存在，只需加新增字段）
    op.add_column("foreshadowings", sa.Column("resolved_chapter", sa.Integer(), nullable=True))
    op.add_column("foreshadowings", sa.Column("resolved_event", sa.String(), nullable=True))
    op.add_column("foreshadowings", sa.Column("resolved_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("foreshadowings", "resolved_at")
    op.drop_column("foreshadowings", "resolved_event")
    op.drop_column("foreshadowings", "resolved_chapter")
    # 注意：foreshadowings.status 在 001_initial.py 中已创建，006 不负责删除
    # 注意：entities.is_active / current_version_id 在 006 添加，006 负责删除
    op.drop_column("entities", "is_active")
    op.drop_column("entities", "current_version_id")
    op.drop_index("idx_bible_versions_entry_version", "bible_entry_versions")
    op.drop_index("idx_bible_versions_entry_chapter", "bible_entry_versions")
    op.drop_table("bible_entry_versions")

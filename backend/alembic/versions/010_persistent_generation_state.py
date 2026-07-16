"""Add durable memory, context snapshots, generation tasks, and draft attempts.

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa
from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.UUID(), sa.ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.UUID(), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("salience", sa.Float(), nullable=False, server_default="0"),
        sa.Column("emotional_intensity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("vector_point_id", sa.String(100), nullable=True),
        sa.Column("index_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_memory_records_project_content_hash"),
    )
    op.create_index("idx_memory_records_project_chapter", "memory_records", ["project_id", "chapter_number"])
    op.create_index("idx_memory_records_entity", "memory_records", ["entity_id"])

    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.UUID(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "digest", name="uq_context_snapshots_project_digest"),
    )
    op.create_index("idx_context_snapshots_scene", "context_snapshots", ["scene_id"])

    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.String(100), nullable=False, unique=True),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.UUID(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("context_snapshot_id", sa.UUID(), sa.ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("initial_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_recovery_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("recovery_allowance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("spent_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("spent_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_generation_tasks_project_idempotency"),
    )
    op.create_index("idx_generation_tasks_project_status", "generation_tasks", ["project_id", "status"])

    op.create_table(
        "scene_draft_attempts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scene_id", sa.UUID(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_snapshot_id", sa.UUID(), sa.ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("call_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_scene_draft_attempt_task_number"),
    )


def downgrade() -> None:
    op.drop_table("scene_draft_attempts")
    op.drop_index("idx_generation_tasks_project_status", table_name="generation_tasks")
    op.drop_table("generation_tasks")
    op.drop_index("idx_context_snapshots_scene", table_name="context_snapshots")
    op.drop_table("context_snapshots")
    op.drop_index("idx_memory_records_entity", table_name="memory_records")
    op.drop_index("idx_memory_records_project_chapter", table_name="memory_records")
    op.drop_table("memory_records")

"""add llm_call_metrics table

Revision ID: 007
Revises: 006
Create Date: 2026-07-14

记录每次 LLM 调用的结构化指标：token 消耗、延迟、成本、成功率。
"""
from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_call_metrics",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), nullable=True, index=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("agent", sa.String(50), nullable=False, index=True),
        sa.Column("chapter_number", sa.Integer(), nullable=True, index=True),
        sa.Column("event_id", sa.String(100), nullable=True),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("error_type", sa.String(50), nullable=True),
    )

    op.create_index("idx_metrics_project_chapter", "llm_call_metrics", ["project_id", "chapter_number"])
    op.create_index("idx_metrics_timestamp", "llm_call_metrics", ["timestamp"])


def downgrade() -> None:
    op.drop_index("idx_metrics_timestamp", "llm_call_metrics")
    op.drop_index("idx_metrics_project_chapter", "llm_call_metrics")
    op.drop_table("llm_call_metrics")

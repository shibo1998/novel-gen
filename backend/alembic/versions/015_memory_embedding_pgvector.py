"""Add pgvector embedding column + HNSW index to memory_records.

Revision ID: 015
Revises: 014

语义召回链路的存储层：
- 启用 pgvector 扩展；
- memory_records 增加 embedding vector(dim) 列（可空，历史行由回填脚本补）；
- 建 HNSW 余弦索引，支撑 O(log n) 语义 top-k 检索；
- index_status 语义在应用层改为 pending/indexed/failed（列本身无需改）。

vector_point_id 保留为遗留列（Qdrant 时代残留），本迁移不删，避免影响存量。
"""

from alembic import op

from app.config import settings

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dim = settings.embed_dim
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS embedding vector({dim})")
    # HNSW 余弦索引：pgvector 对 NULL 向量自动跳过，历史未回填行不影响建索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_records_embedding_hnsw "
        "ON memory_records USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memory_records_embedding_hnsw")
    op.execute("ALTER TABLE memory_records DROP COLUMN IF EXISTS embedding")

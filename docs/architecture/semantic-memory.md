# 语义记忆层

语义记忆与业务记录共存于 PostgreSQL 16 + pgvector，避免独立向量服务的双写一致性问题。

- `memory_records.embedding` 使用 `vector(1024)`，迁移 `015` 创建 `vector_cosine_ops` HNSW 索引。
- 新记录通过 Ollama 的 OpenAI 兼容接口调用 `bge-m3`；失败会写为 `index_status=failed`，正文事务不受阻断。
- 召回合并语义 top-k、最近记录和词面命中三路结果。没有 Ollama 时自动退化为确定性召回。
- 存量回填：`poetry run python scripts/backfill_embeddings.py`。脚本幂等，可重复执行。

本地启动前先在 Ollama 安装并启动 `bge-m3`，随后执行 `poetry run python -m alembic upgrade head`。生产环境默认不自动迁移；需要显式设置 `AUTO_MIGRATE=true` 才会在应用启动时运行迁移。

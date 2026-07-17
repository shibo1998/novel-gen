# 语义记忆层

语义记忆与业务记录共存于 PostgreSQL 16 + pgvector，避免独立向量服务的双写一致性问题。

- `memory_records.embedding` 使用 `vector(1024)`，迁移 `015` 创建 `vector_cosine_ops` HNSW 索引。
- 新记录通过 Ollama 的 OpenAI 兼容接口调用 `bge-m3`；失败会写为 `index_status=failed`，正文事务不受阻断。
- 召回合并语义 top-k、最近记录和词面命中三路结果。没有 Ollama 时自动退化为确定性召回。
- 存量回填：`poetry run python scripts/backfill_embeddings.py`。脚本幂等，可重复执行。

本地启动前先在 Ollama 安装并启动 `bge-m3`，随后执行 `poetry run python -m alembic upgrade head`。生产环境默认不自动迁移；需要显式设置 `AUTO_MIGRATE=true` 才会在应用启动时运行迁移。

## 向量后端决策（2026-07-16）

**状态：已采用。** 当前唯一生产向量后端是 PostgreSQL + pgvector。Qdrant 不是待实现依赖，也不应加入当前 Compose 或双写链路。

早期 `docs/plans/Phase-01-基础设施与项目骨架.md` 和 `Phase-04-Memory层与ContextBuilder.md` 曾规划独立 Qdrant `scenes` collection，用于保存审校通过场景并进行相似场景检索。该方案的 embedding 仍为 TODO，未形成可运行实现，后来由迁移 `015_memory_embedding_pgvector.py` 和 `memory_records` 三路召回正式取代。`docs/plans/` 是本地历史计划，不是当前产品规格。

选择 pgvector 的原因：

- 记忆业务记录与 embedding 可在同一数据源维护，避免 PostgreSQL/Qdrant 双写一致性问题。
- 当前规模不需要独立向量服务的分片和扩缩容能力。
- 部署、备份、权限过滤和故障恢复都可复用现有 PostgreSQL 运维链路。

仅在出现可测量的瓶颈或能力缺口时重新评估 Qdrant：

- pgvector 检索 P95 在完成索引、查询和召回参数优化后仍不满足产品 SLO。
- 向量查询负载持续影响核心业务数据库，需要独立扩缩容或故障隔离。
- 产品明确需要 pgvector 难以提供的多向量、分布式分片或专用向量过滤能力。
- 基准测试证明 Qdrant 的召回质量、吞吐或总运维成本具有显著优势。

重新评估前不实现双写。若未来切换，应先定义统一向量存储接口、离线回填与校验流程、灰度读切换和回滚方案。

`entities.qdrant_point_id` 与 `memory_records.vector_point_id` 是旧方案遗留字段，不表示未来规划。确认生产数据和外部工具均无依赖后，应通过 Alembic 迁移删除。

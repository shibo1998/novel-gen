"""pgvector 向量索引 —— 语义召回的存取层。

这是审查中「不存在的 vector_store.py」的正式落地。用 pgvector 把
MemoryRecord.embedding 列写入 / 检索，取代此前从未落地的 Qdrant 脚手架。

为什么用裸 SQL：
- pgvector 的向量运算（`<=>` cosine 距离）不是 SQLAlchemy ORM 原生表达式，
  用 `text()` 参数化最直接，且与本项目 alembic 迁移的裸 SQL 风格一致；
- 全部走绑定参数（`:vec` 等），无字符串拼接，无注入风险。

向量以 pgvector 的字符串字面量形式传参：`[0.1,0.2,...]`。
"""
from __future__ import annotations

import logging
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def to_pgvector_literal(vector: Sequence[float]) -> str:
    """把浮点序列转成 pgvector 接受的字面量字符串 `[v1,v2,...]`。"""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


async def upsert_embedding(
    db: AsyncSession,
    record_id: UUID,
    vector: Sequence[float],
) -> None:
    """把某条 MemoryRecord 的向量写入 embedding 列，并置 index_status='indexed'。

    与调用方处于同一事务：调用方 commit 时向量与业务数据一起落盘，
    保证「记录存在但向量丢失」这种脱节状态不会出现（相较独立向量服务的双写）。
    """
    await db.execute(
        text(
            "UPDATE memory_records "
            "SET embedding = CAST(:vec AS vector), index_status = 'indexed' "
            "WHERE id = :rid"
        ),
        {"vec": to_pgvector_literal(vector), "rid": str(record_id)},
    )


async def mark_index_failed(db: AsyncSession, record_id: UUID) -> None:
    """embedding 失败时把该记录标为 failed，供后台补偿重试。"""
    await db.execute(
        text("UPDATE memory_records SET index_status = 'failed' WHERE id = :rid"),
        {"rid": str(record_id)},
    )


async def search(
    db: AsyncSession,
    *,
    project_id: UUID | str,
    query_vector: Sequence[float],
    k: int = 10,
    chapter_lt: int | None = None,
    memory_types: tuple[str, ...] | None = None,
) -> list[dict]:
    """语义 top-k 检索：按 cosine 距离返回最相近的记录。

    Args:
        project_id: 限定项目。
        query_vector: 查询向量。
        k: 返回条数。
        chapter_lt: 只召回章号 < 该值的记录（写第 N 章时不能看到 N 及之后）。
        memory_types: 限定记忆类型（如 scene_event / chapter_summary）。

    Returns:
        [{id, chapter_number, memory_type, distance}, ...]，distance 越小越相近。
        仅返回已建索引（embedding IS NOT NULL）的记录。
    """
    params: dict = {
        "pid": str(project_id),
        "vec": to_pgvector_literal(query_vector),
        "k": k,
    }
    conditions = ["project_id = :pid", "embedding IS NOT NULL"]
    if chapter_lt is not None:
        conditions.append("chapter_number IS NOT NULL AND chapter_number < :chlt")
        params["chlt"] = chapter_lt
    if memory_types:
        # 展开为 IN (:mt0, :mt1, ...)
        placeholders = []
        for i, mt in enumerate(memory_types):
            key = f"mt{i}"
            placeholders.append(f":{key}")
            params[key] = mt
        conditions.append(f"memory_type IN ({', '.join(placeholders)})")

    where_clause = " AND ".join(conditions)
    result = await db.execute(
        text(
            "SELECT id, chapter_number, memory_type, "
            "(embedding <=> CAST(:vec AS vector)) AS distance "
            "FROM memory_records "
            f"WHERE {where_clause} "
            "ORDER BY embedding <=> CAST(:vec AS vector) "
            "LIMIT :k"
        ),
        params,
    )
    rows = result.mappings().all()
    return [
        {
            "id": str(row["id"]),
            "chapter_number": row["chapter_number"],
            "memory_type": row["memory_type"],
            "distance": float(row["distance"]) if row["distance"] is not None else None,
        }
        for row in rows
    ]

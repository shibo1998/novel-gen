"""回填存量 MemoryRecord 的 embedding（幂等，可重跑）。

背景：Phase 1 引入语义召回后，历史记录（index_status != 'indexed'）没有 embedding。
本脚本批量为它们补 embedding，供 pgvector 语义检索使用。

用法：
    poetry run python -m scripts.backfill_embeddings [--project-id UUID] [--batch 50]

幂等性：只处理 index_status != 'indexed' 或 embedding IS NULL 的行；
成功置 indexed，失败置 failed，可反复重跑直到全部 indexed。
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.db.session import async_session_maker
from app.llm.embedding import EmbeddingError, get_embedding_client
from app.models.domain import MemoryRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_embeddings")


async def backfill(project_id: str | None = None, batch: int = 50) -> tuple[int, int]:
    """回填 embedding。返回 (成功数, 失败数)。"""
    client = get_embedding_client()
    ok = 0
    failed = 0
    async with async_session_maker() as db:
        stmt = select(MemoryRecord).where(MemoryRecord.embedding.is_(None))
        if project_id:
            stmt = stmt.where(MemoryRecord.project_id == project_id)
        records = (await db.execute(stmt)).scalars().all()
        logger.info("待回填记录数：%d", len(records))

        for start in range(0, len(records), batch):
            chunk = records[start:start + batch]
            texts = [(r.summary or r.content) for r in chunk]
            try:
                vectors = await client.embed_texts(texts)
            except EmbeddingError as exc:
                logger.error("批次 embedding 失败 [%d:%d]: %s", start, start + len(chunk), exc)
                for r in chunk:
                    r.index_status = "failed"
                failed += len(chunk)
                await db.commit()
                continue

            for r, vec in zip(chunk, vectors):
                r.embedding = vec
                r.index_status = "indexed"
                ok += 1
            await db.commit()
            logger.info("已回填 %d/%d", min(start + batch, len(records)), len(records))

    logger.info("回填完成：成功 %d，失败 %d", ok, failed)
    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 MemoryRecord embedding")
    parser.add_argument("--project-id", default=None, help="只回填指定项目（默认全部）")
    parser.add_argument("--batch", type=int, default=50, help="每批嵌入条数")
    args = parser.parse_args()
    asyncio.run(backfill(args.project_id, args.batch))


if __name__ == "__main__":
    main()

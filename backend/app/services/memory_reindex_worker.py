import asyncio
import logging

from app.config import settings
from app.db.session import async_session_maker
from app.services.memory_records import MemoryRecordStore

logger = logging.getLogger(__name__)


async def reindex_memory_once() -> tuple[int, int]:
    async with async_session_maker() as db:
        result = await MemoryRecordStore(db).reindex_pending(
            batch_size=settings.memory_reindex_batch_size
        )
        await db.commit()
        return result


async def memory_reindex_loop() -> None:
    while True:
        await asyncio.sleep(max(1.0, settings.memory_reindex_interval_seconds))
        try:
            indexed, failed = await reindex_memory_once()
            if indexed or failed:
                logger.info(
                    "Memory reindex batch finished: indexed=%d failed=%d",
                    indexed,
                    failed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Memory reindex worker failed; retrying on next interval")

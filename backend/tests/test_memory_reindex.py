from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.llm.embedding import EmbeddingError
from app.services.memory_records import MemoryRecordStore


def _pending_result(records):
    result = MagicMock()
    result.scalars.return_value.all.return_value = records
    return result


async def test_reindex_pending_indexes_a_bounded_batch(monkeypatch):
    records = [
        SimpleNamespace(summary="first", content="one", embedding=None, index_status="failed"),
        SimpleNamespace(summary=None, content="two", embedding=None, index_status="not_indexed"),
    ]
    db = AsyncMock()
    db.execute.return_value = _pending_result(records)
    client = SimpleNamespace(embed_texts=AsyncMock(return_value=[[0.1], [0.2]]))
    monkeypatch.setattr("app.llm.embedding.get_embedding_client", lambda: client)

    indexed, failed = await MemoryRecordStore(db).reindex_pending(batch_size=2)

    assert (indexed, failed) == (2, 0)
    assert [record.embedding for record in records] == [[0.1], [0.2]]
    assert all(record.index_status == "indexed" for record in records)
    db.flush.assert_awaited_once()


async def test_reindex_pending_keeps_records_retryable_on_provider_failure(monkeypatch):
    records = [SimpleNamespace(summary="first", content="one", embedding=None, index_status="failed")]
    db = AsyncMock()
    db.execute.return_value = _pending_result(records)
    client = SimpleNamespace(embed_texts=AsyncMock(side_effect=EmbeddingError("offline")))
    monkeypatch.setattr("app.llm.embedding.get_embedding_client", lambda: client)

    indexed, failed = await MemoryRecordStore(db).reindex_pending(batch_size=1)

    assert (indexed, failed) == (0, 1)
    assert records[0].embedding is None
    assert records[0].index_status == "failed"
    db.flush.assert_awaited_once()

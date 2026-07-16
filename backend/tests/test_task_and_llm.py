import asyncio
from unittest.mock import AsyncMock

import pytest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_none

from app.config import settings
from app.llm import client as llm_client_module
from app.llm.client import CircuitBreaker, UnifiedOpenAIClient
from app.llm.exceptions import LLMCircuitBreakerError, LLMError, LLMTimeoutError
from app.pipeline.task_queue import TaskManager
from app.utils import retry as retry_utils


async def test_task_factory_receives_its_own_id_and_persists_meta(monkeypatch):
    manager = TaskManager()
    monkeypatch.setattr(manager, "_save", lambda: None)
    received_ids: list[str] = []

    async def run(task_id: str):
        received_ids.append(task_id)
        manager.update_meta(task_id, phase="test", completed_chapter_count=5)
        return {"ok": True}

    first_id = manager.create_task(coroutine_factory=run)
    second_id = manager.create_task(coroutine_factory=run)
    await asyncio.gather(
        manager.get_task(first_id)._future,
        manager.get_task(second_id)._future,
    )

    assert received_ids == [first_id, second_id]
    assert manager.get_task(first_id).meta == {"phase": "test", "completed_chapter_count": 5}
    assert manager.get_task(second_id).meta == {"phase": "test", "completed_chapter_count": 5}


async def test_task_manager_accepts_preallocated_durable_id(monkeypatch):
    manager = TaskManager()
    monkeypatch.setattr(manager, "_save", lambda: None)

    async def run(task_id: str):
        return {"task_id": task_id}

    task_id = manager.create_task(coroutine_factory=run, task_id="durable-task-1")
    await manager.get_task(task_id)._future

    assert task_id == "durable-task-1"
    assert manager.get_task(task_id).result == {"task_id": "durable-task-1"}


async def test_find_active_task_matches_project_and_kind(monkeypatch):
    manager = TaskManager()
    monkeypatch.setattr(manager, "_save", lambda: None)

    async def wait_forever(_task_id: str):
        await asyncio.Event().wait()

    task_id = manager.create_task(
        coroutine_factory=wait_forever,
        meta={"project_id": "project-1", "kind": "outline_generation"},
    )
    await asyncio.sleep(0)
    try:
        assert manager.find_active_task(
            project_id="project-1", kind="outline_generation"
        ).id == task_id
        assert manager.find_active_task(
            project_id="project-2", kind="outline_generation"
        ) is None
    finally:
        future = manager.get_task(task_id)._future
        future.cancel()
        with pytest.raises(asyncio.CancelledError):
            await future


class _SlowStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0.1)
        raise StopAsyncIteration


class _FakeCompletions:
    async def create(self, **_kwargs):
        return _SlowStream()


class _FakeOpenAI:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()


async def test_openai_stream_has_whole_call_timeout(monkeypatch):
    monkeypatch.setattr(settings, "llm_timeout_seconds", 0.01)
    client = UnifiedOpenAIClient()
    client._client = _FakeOpenAI()

    with pytest.raises(LLMTimeoutError, match="timed out"):
        async for _ in client.complete_stream("prompt"):
            pass


async def test_retry_exhaustion_raises_domain_error(monkeypatch):
    def immediate_retry_decorator(_max_retries=None):
        return retry(
            stop=stop_after_attempt(1),
            wait=wait_none(),
            retry=retry_if_exception_type(LLMTimeoutError),
        )

    monkeypatch.setattr(retry_utils, "create_llm_retry_decorator", immediate_retry_decorator)

    @retry_utils.with_retry
    async def always_times_out():
        raise LLMTimeoutError("temporary timeout")

    with pytest.raises(LLMError, match="configured retries"):
        await always_times_out()


async def test_circuit_rejects_calls_until_recovery(monkeypatch):
    breaker = CircuitBreaker(threshold=1, timeout=60)
    breaker.record_failure()
    monkeypatch.setattr(llm_client_module, "_circuit_breaker", breaker)

    with pytest.raises(LLMCircuitBreakerError, match="circuit breaker is open"):
        async for _ in UnifiedOpenAIClient()._complete_stream_once("prompt"):
            pass


async def test_stream_retries_before_first_token(monkeypatch):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LLMTimeoutError("before output")
        yield "ok"

    monkeypatch.setattr(settings, "llm_max_retries", 2)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    chunks = [chunk async for chunk in llm_client_module._retry_stream_before_first_token(factory)]

    assert chunks == ["ok"]
    assert calls == 2


async def test_stream_does_not_retry_after_partial_output(monkeypatch):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        yield "partial"
        raise LLMTimeoutError("stream interrupted")

    monkeypatch.setattr(settings, "llm_max_retries", 3)
    with pytest.raises(LLMTimeoutError, match="interrupted"):
        _ = [chunk async for chunk in llm_client_module._retry_stream_before_first_token(factory)]

    assert calls == 1

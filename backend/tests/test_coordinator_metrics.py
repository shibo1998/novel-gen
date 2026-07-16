from unittest.mock import AsyncMock

from app.pipeline.coordinator import Coordinator


async def test_coordinator_records_call_semantics_and_context_snapshot():
    coordinator = Coordinator()
    collector = AsyncMock()

    await coordinator._record_call(
        collector=collector,
        agent="writer",
        project_id="project-1",
        chapter_number=15,
        event_id="scene-1",
        prompt="prompt text",
        output="generated text",
        started=0.0,
        retry_count=0,
        call_type="recovery",
        context_snapshot_id="snapshot-1",
    )

    metric = collector.record_call.await_args.args[0]
    assert metric.call_type == "recovery"
    assert metric.context_snapshot_id == "snapshot-1"
    assert metric.project_id == "project-1"
    assert metric.total_tokens == metric.prompt_tokens + metric.completion_tokens

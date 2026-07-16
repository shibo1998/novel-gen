from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.quality_evaluator import QualityEvaluator


def _streaming_mock(*chunks: str, error: Exception | None = None) -> MagicMock:
    async def stream(*_args, **_kwargs):
        if error is not None:
            raise error
        for chunk in chunks:
            yield chunk

    return MagicMock(side_effect=stream)


async def test_quality_provider_failure_is_unavailable_not_default_score():
    evaluator = QualityEvaluator("test-project")
    stream = _streaming_mock(error=RuntimeError("provider unavailable"))
    evaluator.llm = SimpleNamespace(complete_stream=stream)

    result = await evaluator.evaluate("测试正文", 1)

    assert result["evaluation_status"] == "unavailable"
    assert result["overall_score"] is None
    assert result["needs_human_review"] is True
    assert len(result["failed_dimensions"]) == len(evaluator.dimensions)


async def test_quality_invalid_provider_output_is_unavailable():
    evaluator = QualityEvaluator("test-project")
    evaluator.llm = SimpleNamespace(
        complete_stream=_streaming_mock("质量不错，但我不想给数字。")
    )

    result = await evaluator.evaluate("测试正文", 1)

    assert result["evaluation_status"] == "unavailable"
    assert result["overall_score"] is None


async def test_quality_accepts_streamed_structured_score():
    evaluator = QualityEvaluator("test-project")
    stream = _streaming_mock('{"score": 4,', ' "feedback": "结构清楚"}')
    evaluator.llm = SimpleNamespace(complete_stream=stream)

    result = await evaluator.evaluate("测试正文", 1)

    assert result["evaluation_status"] == "completed"
    assert result["overall_score"] == 4.0
    assert stream.call_count == len(evaluator.dimensions)

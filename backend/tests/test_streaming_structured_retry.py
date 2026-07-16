from types import SimpleNamespace

from app.agents.base import BaseAgent


class _StructuredAgent(BaseAgent):
    @property
    def template_name(self) -> str:
        return "worldbuilding.j2"

    def output_schema(self) -> dict:
        return {}


async def test_truncated_structured_output_retries_as_a_fresh_stream(monkeypatch):
    agent = _StructuredAgent()
    prompts = []

    async def complete_stream(prompt: str, system: str = ""):
        prompts.append(prompt)
        if len(prompts) == 1:
            yield '{"value":"unfinished'
        else:
            yield '{"value":"complete"}'

    agent.llm = SimpleNamespace(complete_stream=complete_stream)
    monkeypatch.setattr("app.agents.base.settings.llm_max_retries", 2)

    result = await agent.run(
        {"core_idea": "测试", "genre": "奇幻", "tone_style": "克制"}
    )

    assert result == {"value": "complete"}
    assert len(prompts) == 2
    assert "结构化输出恢复" in prompts[1]


async def test_non_truncation_json_error_retries_as_a_fresh_stream(monkeypatch):
    agent = _StructuredAgent()
    calls = 0

    async def complete_stream(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "not-json"
        else:
            yield '{"value":"recovered"}'

    agent.llm = SimpleNamespace(complete_stream=complete_stream)
    monkeypatch.setattr("app.agents.base.settings.llm_max_retries", 3)

    result = await agent.run(
        {"core_idea": "测试", "genre": "奇幻", "tone_style": "克制"}
    )

    assert result == {"value": "recovered"}
    assert calls == 2

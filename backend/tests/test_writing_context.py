from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agents.writer import WriterAgent
from app.api import writing
from app.models.constraints import SceneConstraint
from app.pipeline.context_builder import ContextBuilder
from app.services.context_budget import ContextBudgetManager, ContextSlice


def _constraint() -> SceneConstraint:
    return SceneConstraint(
        chapter_number=15,
        scene_number=1,
        scene_title="禁地余波",
        narrative_goal="林远确认有人跟踪",
        scene_function="progression",
        pov_character="林远",
        characters_present=["林远", "玄明"],
        character_emotional_states={"林远": "警惕"},
        opening_emotion="不安",
        closing_emotion="决心",
        emotional_beats=["察觉", "判断"],
        reader_should_know=["有人跟踪"],
        reader_should_not_know=["跟踪者身份"],
        prose_directives=["克制"],
        forbidden_elements=["只见"],
    )


def test_empty_context_slices_are_not_reported_as_budget_drops():
    manager = ContextBudgetManager(model="gpt-4o")
    slices = [
        ContextSlice("chapter_summaries", "", "medium"),
        ContextSlice("world_rules", "", "medium"),
        ContextSlice("historical_events", "", "low"),
    ]

    allocated, report = manager.allocate(slices, chapter_number=1)

    assert allocated == []
    assert report.dropped_categories == []


async def test_writer_prompt_includes_budgeted_history_and_legacy_world_rules():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [
        MagicMock(display_name="灵气守恒", description="灵气不能凭空产生"),
    ]
    db.execute.return_value = result
    builder = ContextBuilder(db)

    world_rules = await builder._get_world_rules(str(uuid4()))
    statement = db.execute.await_args.args[0]
    list_param = next(
        value for value in statement.compile().params.values() if isinstance(value, list)
    )
    assert set(list_param) == {"rule", "world_rule"}

    enriched = builder.enrich_constraint(
        _constraint(),
        {
            "chapter_summaries": "第14章：林远逃出禁地",
            "world_rules": world_rules,
        },
    )
    prompt = WriterAgent()._build_prompt(enriched)

    assert enriched.injected_chapter_summaries == "第14章：林远逃出禁地"
    assert enriched.injected_world_rules == "【灵气守恒】灵气不能凭空产生"
    assert "历史章节摘要" in prompt
    assert "林远逃出禁地" in prompt
    assert "世界观硬规则" in prompt
    assert "灵气不能凭空产生" in prompt


async def test_writing_context_is_built_and_injected(monkeypatch):
    project_id = uuid4()
    db = AsyncMock()
    builder = MagicMock()
    builder.build_context_with_budget = AsyncMock(
        return_value=(
            {
                "injected_bible": {"林远": {"arms_status": "normal"}},
                "injected_previous": [{"chapter": 14, "summary": "逃出禁地"}],
                "injected_foreshadowings": [
                    {
                        "id": "fs-left-hand",
                        "name": "左手伤痕",
                        "description": "月圆发烫",
                        "reap_chapter": 30,
                        "is_due": False,
                    }
                ],
                "memory_retrieval": [{"chapter": 3, "summary": "月圆时左手伤痕发烫"}],
                "injected_plot_threads": [
                    {"name": "旧伤之谜", "description": "调查伤痕来源", "priority": 5}
                ],
            },
            {"utilization": "25%", "dropped_categories": []},
        )
    )
    builder.enrich_constraint.side_effect = lambda constraint, context: constraint.model_copy(
        injected_bible=context["injected_bible"],
        injected_previous=context["injected_previous"],
        injected_foreshadowings=context["injected_foreshadowings"],
        injected_memories=context["memory_retrieval"],
        injected_plot_threads=context["injected_plot_threads"],
    )
    monkeypatch.setattr(writing, "ContextBuilder", lambda _db: builder)

    enriched = await writing._enrich_constraint_for_writing(db, project_id, _constraint())

    builder.build_context_with_budget.assert_awaited_once()
    assert enriched.injected_bible == {"林远": {"arms_status": "normal"}}
    assert enriched.injected_previous == [{"chapter": 14, "summary": "逃出禁地"}]
    assert enriched.injected_foreshadowings[0]["id"] == "fs-left-hand"
    assert enriched.injected_memories == [{"chapter": 3, "summary": "月圆时左手伤痕发烫"}]
    assert enriched.injected_plot_threads[0]["name"] == "旧伤之谜"

    prompt = WriterAgent()._build_prompt(enriched)
    assert "arms_status" in prompt
    assert "逃出禁地" in prompt
    assert "左手伤痕" in prompt
    assert "ID=fs-left-hand" in prompt
    assert "长期记忆检索" in prompt
    assert "月圆时左手伤痕发烫" in prompt
    assert "活跃情节线" in prompt
    assert "旧伤之谜" in prompt


async def test_writer_stream_forwards_and_collects_tokens(monkeypatch):
    agent = WriterAgent()

    async def chunks(*_args, **_kwargs):
        for chunk in ("第一段", "第二段"):
            yield chunk

    agent.llm.complete_stream = chunks
    received = []

    async def on_token(chunk):
        received.append(chunk)

    content = await agent.write_scene_stream(_constraint(), on_token=on_token)

    assert content == "第一段第二段"
    assert received == ["第一段", "第二段"]


async def test_owned_scene_hides_other_users_scene():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await writing._get_owned_scene(db, uuid4(), str(uuid4()))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Scene not found"

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.agents.chapter import ChapterAgent
from app.agents.reviewer import ReviewerAgent
from app.api import writing
from app.api.chapter import _planning_characters
from app.models.constraints import SceneConstraint
from app.pipeline.context_builder import ContextBuilder
from app.pipeline.coordinator import Coordinator
from app.services.consistency_checker import check_due_foreshadowing_coverage
from app.services.foreshadow_scheduler import ForeshadowScheduler
from app.services.outline_planner import _bind_foreshadowing_seeds


def _scalars_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _constraint(foreshadowings=None) -> SceneConstraint:
    return SceneConstraint(
        chapter_number=20,
        scene_number=1,
        scene_title="旧信",
        narrative_goal="拆开旧信",
        scene_function="resolution",
        pov_character="林远",
        characters_present=["林远"],
        character_emotional_states={"林远": "紧张"},
        opening_emotion="紧张",
        closing_emotion="释然",
        emotional_beats=["发现真相"],
        reader_should_know=["旧信来自师父"],
        reader_should_not_know=[],
        prose_directives=[],
        forbidden_elements=[],
        foreshadowing_ids=[item["id"] for item in (foreshadowings or [])],
        injected_foreshadowings=foreshadowings or [],
    )


async def test_scheduler_separates_active_and_due_and_keeps_ids():
    active_id = uuid4()
    due_id = uuid4()
    future_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalars_result(
        [
            SimpleNamespace(
                id=active_id,
                name="旧伤",
                description="月圆发热",
                sow_chapter=3,
                reap_chapter=30,
            ),
            SimpleNamespace(
                id=due_id,
                name="旧信",
                description="师父留下的真相",
                sow_chapter=5,
                reap_chapter=20,
            ),
            SimpleNamespace(
                id=future_id,
                name="未来来客",
                description="尚未播种",
                sow_chapter=25,
                reap_chapter=40,
            ),
        ]
    )

    schedule = await ForeshadowScheduler(db).get_schedule(str(uuid4()), 20)

    assert [item["id"] for item in schedule["active"]] == [str(active_id), str(due_id)]
    assert [item["id"] for item in schedule["due"]] == [str(due_id)]


def test_due_coverage_requires_explicit_id_not_incidental_name():
    due = [{"id": "fs-1", "name": "旧信"}]

    warnings = check_due_foreshadowing_coverage(
        due,
        [{"narrative_goal": "读完旧信", "foreshadowing_ids": []}],
    )
    covered = check_due_foreshadowing_coverage(
        due,
        [{"narrative_goal": "读完旧信", "foreshadowing_ids": ["fs-1"]}],
    )

    assert warnings[0]["code"] == "due_foreshadowing_missing"
    assert covered == []


def test_chapter_seed_is_bound_without_mutating_agent_output():
    foreshadowing_id = uuid4()
    raw_seed = {"name": "旧信", "brief": "信封首次出现"}
    chapter = {"number": 5, "foreshadowing_seeds": [raw_seed]}

    result = _bind_foreshadowing_seeds(
        chapter,
        {"旧信": SimpleNamespace(id=foreshadowing_id)},
    )

    assert result[0]["foreshadowing_id"] == str(foreshadowing_id)
    assert "foreshadowing_id" not in raw_seed


async def test_active_foreshadowing_context_keeps_due_item_and_id():
    foreshadowing_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalars_result(
        [
            SimpleNamespace(
                id=foreshadowing_id,
                name="旧信",
                description="师父留下的真相",
                sow_chapter=5,
                reap_chapter=20,
            )
        ]
    )

    result = await ContextBuilder(db)._get_active_foreshadowings(str(uuid4()), 20)

    assert result == [
        {
            "id": str(foreshadowing_id),
            "name": "旧信",
            "description": "师父留下的真相",
            "sow_chapter": 5,
            "reap_chapter": 20,
            "is_due": True,
        }
    ]


def test_chapter_prompt_includes_due_id_history_and_semantic_memory():
    prompt = ChapterAgent().jinja.get_template("chapter.j2").render(
        chapter={"number": 20, "title": "真相", "goal": "揭晓", "key_events": [], "pov_character": "林远"},
        hard_constraints=[],
        soft_constraints=[],
        characters=[
            {
                "name": "林远",
                "personality_traits": "克制",
                "speech_style": "简短",
                "quirks": "摸左手旧伤",
                "current_state": {"injury": "healed"},
            }
        ],
        relationships=[{"from": "林远", "to": "师父", "status": "决裂"}],
        chapter_summaries=[{"chapter": 19, "summary": "林远找到旧信"}],
        due_foreshadowings=[{"id": "fs-1", "name": "旧信", "description": "师父遗言", "reap_chapter": 20}],
        relevant_memories=[{"chapter": 5, "summary": "师父藏起信封"}],
    )

    assert "ID=fs-1" in prompt
    assert "林远找到旧信" in prompt
    assert "师父藏起信封" in prompt
    assert "foreshadowing_ids" in prompt
    assert '"injury": "healed"' in prompt
    assert '"status": "\\u51b3\\u88c2"' in prompt
    assert "reader_experience_goal" in prompt

    schema = ChapterAgent().output_schema()["items"]
    assert "reader_experience_goal" in schema["properties"]
    assert "reader_experience_goal" in schema["required"]


def test_planning_characters_use_previous_chapter_bible_snapshot():
    character = SimpleNamespace(
        name="林远",
        data={"personality_traits": "克制", "injury": "old"},
    )

    result = _planning_characters(
        [character],
        {
            "characters": {
                "林远": {"personality_traits": "果断", "injury": "healed"}
            }
        },
    )

    assert result[0]["personality_traits"] == "果断"
    assert result[0]["current_state"]["injury"] == "healed"


async def test_reviewer_filters_hallucinated_resolution_ids():
    allowed = {"id": str(uuid4()), "name": "旧信", "description": "师父遗言"}
    reviewer = ReviewerAgent()
    async def streamed_review(*_args, **_kwargs):
        yield '{"passed": true, "issues": [], "resolved_foreshadowing_ids": '
        yield f'["{allowed["id"]}", "not-in-context"]}}'

    reviewer.llm = SimpleNamespace(complete_stream=streamed_review)

    result = await reviewer.review("信中写明师父当年的选择。", _constraint([allowed]))

    assert result["status"] == "pass"
    assert result["resolved_foreshadowing_ids"] == [allowed["id"]]


async def test_coordinator_returns_resolutions_only_after_pass():
    item = {"id": str(uuid4()), "name": "旧信", "description": "师父遗言"}
    coordinator = Coordinator()
    coordinator.writer.write_scene = AsyncMock(return_value="信中写明真相。")
    coordinator.reviewer.review = AsyncMock(
        return_value={
            "status": "pass",
            "issues": [],
            "resolved_foreshadowing_ids": [item["id"]],
        }
    )

    result = await coordinator.run_writing_flow(
        _constraint([item]), str(uuid4()), chapter_number=21
    )

    assert result["resolved_foreshadowing_ids"] == [item["id"]]


async def test_resolution_helper_updates_only_selected_project_rows(monkeypatch):
    project_id = uuid4()
    foreshadowing_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = _scalars_result([SimpleNamespace(id=foreshadowing_id)])
    manager = MagicMock()
    manager.resolve_foreshadowing = AsyncMock(return_value=True)
    monkeypatch.setattr(writing, "BibleVersionManager", lambda _db: manager)

    resolved = await writing._resolve_reviewed_foreshadowings(
        db,
        project_id,
        20,
        [str(foreshadowing_id), "invalid-id"],
    )

    assert resolved == [str(foreshadowing_id)]
    manager.resolve_foreshadowing.assert_awaited_once_with(
        str(project_id), str(foreshadowing_id), 20
    )

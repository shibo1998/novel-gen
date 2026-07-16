from app.models.constraints import SceneConstraint
from app.services.context_snapshot_store import ContextSnapshotStore


def _constraint() -> SceneConstraint:
    return SceneConstraint(
        chapter_number=2,
        scene_number=1,
        scene_title="测试",
        narrative_goal="推进剧情",
        scene_function="progression",
        pov_character="林远",
        characters_present=["林远"],
        character_emotional_states={"林远": "警惕"},
        opening_emotion="平静",
        closing_emotion="不安",
        emotional_beats=["发现"],
        reader_should_know=["有异常"],
        reader_should_not_know=["真相"],
        prose_directives=["克制"],
        forbidden_elements=["只见"],
    )


def test_context_snapshot_payload_is_stable_and_complete():
    store = ContextSnapshotStore(None)
    payload = store.build_payload(
        _constraint(),
        {
            "injected_bible": {"林远": {"arms_status": "normal"}},
            "injected_previous": [{"chapter": 1, "summary": "拜入宗门"}],
            "injected_foreshadowings": [{"name": "左手伤痕"}],
            "memory_retrieval": [{"content": "月圆时伤痕发烫"}],
            "injected_plot_threads": [{"name": "旧伤之谜", "priority": 5}],
        },
        {"utilization": "20%", "dropped_categories": []},
        chapter_outline={"events": [{"event_id": "ch2-e1"}]},
    )

    assert payload["constraint_card_snapshot"]["chapter_number"] == 2
    assert payload["bible_snapshot"]["林远"]["arms_status"] == "normal"
    assert payload["memory_retrieval_frozen"][0]["content"] == "月圆时伤痕发烫"
    assert payload["plot_thread_snapshot"][0]["name"] == "旧伤之谜"
    assert payload["foreshadowing_snapshot"] == [{"name": "左手伤痕"}]
    assert ContextSnapshotStore.digest(payload) == ContextSnapshotStore.digest(dict(payload))

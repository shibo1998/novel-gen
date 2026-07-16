from app.models.domain import (
    BibleEntryVersion,
    ChapterContentVersion,
    ContextSnapshot,
    DHOReplanCandidate,
    Entity,
    Foreshadowing,
    GenerationTask,
    LLMCallMetric,
    MemoryRecord,
    OutlineVersion,
    QualityReport,
    SceneDraftAttempt,
)


def test_orm_matches_existing_bible_version_migration():
    assert {"current_version_id", "is_active"}.issubset(Entity.__table__.c.keys())
    assert {"resolved_chapter", "resolved_event", "resolved_at"}.issubset(Foreshadowing.__table__.c.keys())
    assert {
        "entry_id",
        "version_number",
        "json_snapshot",
        "chapter_applied",
        "previous_version_id",
    }.issubset(BibleEntryVersion.__table__.c.keys())


def test_orm_models_existing_metrics_and_quality_tables():
    assert {
        "project_id",
        "total_tokens",
        "cost_estimate",
        "success",
        "call_type",
        "context_snapshot_id",
    }.issubset(
        LLMCallMetric.__table__.c.keys()
    )


def test_orm_models_durable_generation_state():
    assert {"content_hash", "index_status", "metadata_json"}.issubset(MemoryRecord.__table__.c.keys())
    assert {"snapshot_json", "digest", "schema_version"}.issubset(ContextSnapshot.__table__.c.keys())
    assert {"idempotency_key", "checkpoint_json", "recovery_attempt_count"}.issubset(
        GenerationTask.__table__.c.keys()
    )
    assert {"attempt_number", "call_type", "content"}.issubset(SceneDraftAttempt.__table__.c.keys())


def test_orm_models_versions_and_dho_candidates():
    assert {"version_number", "snapshot_json", "status"}.issubset(
        OutlineVersion.__table__.c.keys()
    )
    assert {"version_number", "scene_snapshot", "compiled_content"}.issubset(
        ChapterContentVersion.__table__.c.keys()
    )
    assert {"base_outline_version_id", "candidate_snapshot", "diff_json"}.issubset(
        DHOReplanCandidate.__table__.c.keys()
    )
    assert {"project_id", "chapter_number", "overall_score", "needs_human_review"}.issubset(
        QualityReport.__table__.c.keys()
    )

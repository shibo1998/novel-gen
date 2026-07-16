import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明基类"""
    pass


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Project(Base):
    """项目表"""
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    core_idea = Column(Text, nullable=False)
    genre = Column(String(50))
    tone_style = Column(String(100))
    target_word_count = Column(Integer, default=100000)
    target_chapter_count = Column(Integer, default=90, nullable=False)
    status = Column(String(50), default="draft")
    data = Column(JSON, default=dict)
    active_outline_version_id = Column(UUID(as_uuid=True), nullable=True)
    active_style_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Entity(Base):
    """实体表（角色、地点、组织、物品、规则、魔法系统等）"""
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    data = Column(JSON, default=dict)
    version = Column(Integer, default=1)
    current_version_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Foreshadowing(Base):
    """伏笔表"""
    __tablename__ = "foreshadowings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sow_chapter = Column(Integer)
    sow_volume = Column(Integer)
    reap_chapter = Column(Integer)
    reap_volume = Column(Integer)
    status = Column(String(20), default="pending")
    resolved_chapter = Column(Integer, nullable=True)
    resolved_event = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BibleEntryVersion(Base):
    """Immutable Bible state at a specific chapter event."""
    __tablename__ = "bible_entry_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    json_snapshot = Column(JSON, nullable=False)
    chapter_applied = Column(Integer, nullable=False, index=True)
    event_applied = Column(String, nullable=True)
    change_summary = Column(Text, nullable=True)
    previous_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Chapter(Base):
    """章节表"""
    __tablename__ = "chapters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    volume_id = Column(UUID(as_uuid=True), ForeignKey("volumes.id", ondelete="SET NULL"), nullable=True, index=True)
    volume_number = Column(Integer, default=1)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(200))
    outline = Column(JSON)
    word_count = Column(Integer, default=0)
    status = Column(String(20), default="planned")
    quality_state = Column(String(30), default="drafting", nullable=False)
    is_locked = Column(Boolean, default=False)
    active_content_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Volume(Base):
    """卷表 —— 大纲中间层，管理卷级元数据和展开状态"""
    __tablename__ = "volumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    volume_number = Column(Integer, nullable=False)
    title = Column(String(100))
    core_conflict = Column(Text)
    character_arc_stage = Column(String(100))
    status = Column(String(20), default="planned")  # planned | planning | detailed | writing | completed | archived
    chapter_start = Column(Integer, nullable=True)  # 起始章号（展开后填入）
    chapter_end = Column(Integer, nullable=True)    # 结束章号（展开后填入）
    summary = Column(Text)                         # 卷级摘要（展开后由 AI 生成）
    contract = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # 同一项目内卷号唯一
        {"schema": None},
    )


class Scene(Base):
    """场景表"""
    __tablename__ = "scenes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_number = Column(Integer, nullable=False)
    title = Column(String(200))
    location = Column(String(200))
    time_period = Column(String(100))
    constraint_card = Column(JSON)
    content = Column(Text)
    word_count = Column(Integer, default=0)
    pov_character_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"))
    qdrant_point_id = Column(String(100))
    status = Column(String(20), default="planned")
    review_result = Column(JSON, nullable=True)  # Phase 9: AI 味审校结果
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReviewSuggestion(Base):
    """审校建议表"""
    __tablename__ = "review_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    severity = Column(String(20))
    category = Column(String(50))
    description = Column(Text, nullable=False)
    suggestion = Column(Text)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class LLMCallMetric(Base):
    """Persisted LLM call accounting record (migration 007)."""
    __tablename__ = "llm_call_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    agent = Column(String(50), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=True, index=True)
    event_id = Column(String(100), nullable=True)
    model = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    cost_estimate = Column(Float, nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    error_type = Column(String(50), nullable=True)
    call_type = Column(String(20), default="initial", nullable=False)
    context_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True
    )


class CostReservation(Base):
    """Expiring pre-call budget reservation settled by LLM observability."""
    __tablename__ = "cost_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=True, index=True)
    estimated_cost = Column(Float, nullable=False)
    actual_cost = Column(Float, nullable=True)
    status = Column(String(20), default="reserved", nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    settled_at = Column(DateTime, nullable=True)


class QualityReport(Base):
    """Chapter quality evaluation record (migration 008)."""
    __tablename__ = "quality_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    chapter_content_version_id = Column(UUID(as_uuid=True), ForeignKey("chapter_content_versions.id", ondelete="CASCADE"), nullable=True)
    overall_score = Column(Float, nullable=True)
    max_score = Column(Float, default=5.0, nullable=False)
    dimension_scores = Column(JSON, nullable=False)
    weak_spots = Column(JSON, nullable=False)
    needs_human_review = Column(Boolean, nullable=False)
    verdict = Column(String(50), nullable=True)
    evaluation_status = Column(String(30), default="completed", nullable=False)
    evaluator_version = Column(String(50), default="v1", nullable=False)
    prompt_version = Column(String(50), nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MemoryRecord(Base):
    """PostgreSQL source of truth for retrievable long-term memory."""
    __tablename__ = "memory_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    memory_type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    chapter_number = Column(Integer, nullable=True)
    salience = Column(Float, default=0.0, nullable=False)
    emotional_intensity = Column(Float, default=0.0, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    content_hash = Column(String(64), nullable=False)
    vector_point_id = Column(String(100), nullable=True)  # 遗留：Qdrant 时代残留，已弃用
    embedding = Column(Vector(settings.embed_dim), nullable=True)
    index_status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ContextSnapshot(Base):
    """Immutable writer input used for an initial generation and any recovery."""
    __tablename__ = "context_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    snapshot_json = Column(JSON, nullable=False)
    digest = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GenerationTask(Base):
    """Durable generation state replacing process-local task files."""
    __tablename__ = "generation_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(100), nullable=False, unique=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=True)
    context_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True)
    task_type = Column(String(50), nullable=False)
    phase = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    idempotency_key = Column(String(100), nullable=False)
    initial_attempt_count = Column(Integer, default=0, nullable=False)
    recovery_attempt_count = Column(Integer, default=0, nullable=False)
    max_recovery_attempts = Column(Integer, default=2, nullable=False)
    recovery_allowance = Column(Float, default=0.0, nullable=False)
    spent_cost = Column(Float, default=0.0, nullable=False)
    spent_tokens = Column(Integer, default=0, nullable=False)
    checkpoint_json = Column(JSON, default=dict, nullable=False)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class SceneDraftAttempt(Base):
    """Immutable generated or interrupted draft attempt for a scene."""
    __tablename__ = "scene_draft_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False)
    context_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True)
    attempt_number = Column(Integer, nullable=False)
    call_type = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    cost_estimate = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OutlineVersion(Base):
    __tablename__ = "outline_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    parent_version_id = Column(UUID(as_uuid=True), nullable=True)
    snapshot_json = Column(JSON, nullable=False)
    digest = Column(String(64), nullable=False)
    source = Column(String(30), nullable=False)
    status = Column(String(30), default="draft", nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)


class ChapterContentVersion(Base):
    __tablename__ = "chapter_content_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    parent_version_id = Column(UUID(as_uuid=True), nullable=True)
    source = Column(String(30), nullable=False)
    scene_snapshot = Column(JSON, nullable=False)
    compiled_content = Column(Text, nullable=False)
    context_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("context_snapshots.id", ondelete="SET NULL"), nullable=True)
    generation_task_id = Column(UUID(as_uuid=True), ForeignKey("generation_tasks.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DHOReplanCandidate(Base):
    __tablename__ = "dho_replan_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    base_outline_version_id = Column(UUID(as_uuid=True), ForeignKey("outline_versions.id", ondelete="CASCADE"), nullable=False)
    trigger_json = Column(JSON, nullable=False)
    affected_from = Column(Integer, nullable=False)
    affected_to = Column(Integer, nullable=True)
    candidate_snapshot = Column(JSON, nullable=False)
    diff_json = Column(JSON, nullable=False)
    status = Column(String(30), default="pending_review", nullable=False)
    applied_outline_version_id = Column(UUID(as_uuid=True), ForeignKey("outline_versions.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)


class HumanReviewItem(Base):
    __tablename__ = "human_review_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    chapter_content_version_id = Column(UUID(as_uuid=True), ForeignKey("chapter_content_versions.id", ondelete="CASCADE"), nullable=False)
    quality_report_id = Column(UUID(as_uuid=True), ForeignKey("quality_reports.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String(30), nullable=False)
    priority = Column(String(20), default="normal", nullable=False)
    status = Column(String(30), default="open", nullable=False)
    reason_json = Column(JSON, nullable=False)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class ProjectStyleVersion(Base):
    __tablename__ = "project_style_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    profile_json = Column(JSON, nullable=False)
    sample_hash = Column(String(64), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PlotThread(Base):
    """Manually curated long-running plot arc; automatic lifecycle uses Foreshadowing."""
    __tablename__ = "plot_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"))
    name = Column(String(200), nullable=False)
    description = Column(Text)
    start_chapter = Column(Integer)
    end_chapter = Column(Integer)
    priority = Column(Integer, default=1)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

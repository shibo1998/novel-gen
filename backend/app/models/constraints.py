"""约束卡数据模型"""
from typing import List, Optional

from pydantic import BaseModel, Field


class SceneConstraint(BaseModel):
    """场景约束卡"""
    chapter_number: int
    scene_number: int
    scene_title: str
    narrative_goal: str
    scene_function: str  # establishing / progression / turning_point / resolution

    pov_character: str
    characters_present: List[str]
    character_emotional_states: dict[str, str]

    opening_emotion: str
    closing_emotion: str
    emotional_beats: List[str]

    reader_should_know: List[str]
    reader_should_not_know: List[str]
    reader_experience_goal: str = Field(
        default="",
        description=(
            "给 Writer 的具体读者体验目标，例如前段疲惫、中段紧张、结尾产生翻页冲动"
        ),
    )

    prose_directives: List[str]
    forbidden_elements: List[str]
    word_budget: int = Field(default=1000, ge=500, le=3000)
    foreshadowing_ids: List[str] = Field(default_factory=list)

    # 由ContextBuilder填充（Phase 4 接入）
    injected_bible: Optional[dict] = None
    injected_previous: Optional[List[dict]] = None
    injected_foreshadowings: Optional[List[dict]] = None
    injected_memories: Optional[List[dict]] = None
    injected_plot_threads: Optional[List[dict]] = None
    injected_style: Optional[dict] = None
    injected_chapter_summaries: Optional[str] = None
    injected_world_rules: Optional[str] = None

    def model_copy(self, **updates):
        """支持深拷贝并更新字段"""
        data = self.model_dump()
        data.update(updates)
        return SceneConstraint(**data)


class RevisionNote(BaseModel):
    """审校反馈记录"""
    attempt: int
    critical_issues: List[dict]
    partial_content: str = ""


class ReviewResult(BaseModel):
    """审校结果"""
    passed: bool
    issues: List[dict] = Field(default_factory=list)
    summary: str = ""
    needs_human_review: bool = False
    style_review: dict = Field(default_factory=dict)

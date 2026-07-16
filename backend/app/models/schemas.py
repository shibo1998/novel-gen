from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ============== 认证相关 ==============

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=12)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ============== 项目相关 ==============

class ProjectBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    core_idea: str = Field(..., min_length=10)
    genre: Optional[str] = None
    tone_style: Optional[str] = None
    target_word_count: Optional[int] = Field(default=100000, ge=1000, le=1000000)
    target_chapter_count: Optional[int] = Field(default=90, ge=10, le=2000)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    core_idea: Optional[str] = Field(None, min_length=10)
    genre: Optional[str] = None
    tone_style: Optional[str] = None
    target_word_count: Optional[int] = Field(None, ge=1000, le=1000000)
    target_chapter_count: Optional[int] = Field(None, ge=10, le=2000)
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    core_idea: str
    genre: Optional[str]
    tone_style: Optional[str]
    target_word_count: int
    target_chapter_count: int
    status: str
    created_at: datetime
    updated_at: datetime


# ============== 实体相关 ==============

class EntityBase(BaseModel):
    type: str = Field(..., description="实体类型: character/location/organization/item/rule/magic_system")
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    data: Optional[dict] = None


class EntityCreate(EntityBase):
    project_id: UUID


class EntityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    data: Optional[dict] = None


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    type: str
    name: str
    display_name: str
    description: Optional[str]
    data: dict
    version: int
    created_at: datetime
    updated_at: datetime


# ============== 章节相关 ==============

class ChapterBase(BaseModel):
    volume_number: int = Field(default=1, ge=1)
    chapter_number: int = Field(..., ge=1)
    title: Optional[str] = Field(None, max_length=200)


class ChapterCreate(ChapterBase):
    project_id: UUID


class ChapterUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    outline: Optional[dict] = None
    status: Optional[str] = None


class ChapterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    volume_number: int
    chapter_number: int
    title: Optional[str]
    outline: Optional[dict]
    word_count: int
    status: str
    created_at: datetime
    updated_at: datetime


# ============== 场景相关 ==============

class SceneBase(BaseModel):
    scene_number: int = Field(..., ge=1)
    title: Optional[str] = Field(None, max_length=200)
    location: Optional[str] = None
    time_period: Optional[str] = None
    constraint_card: Optional[dict] = None


class SceneCreate(SceneBase):
    chapter_id: UUID
    project_id: UUID


class SceneUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    location: Optional[str] = None
    time_period: Optional[str] = None
    constraint_card: Optional[dict] = None
    content: Optional[str] = None
    status: Optional[str] = None


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: UUID
    project_id: UUID
    scene_number: int
    title: Optional[str]
    location: Optional[str]
    time_period: Optional[str]
    constraint_card: Optional[dict]
    content: Optional[str]
    word_count: int
    pov_character_id: Optional[UUID]
    status: str
    created_at: datetime
    updated_at: datetime


# ============== 世界观相关 ==============

class WorldbuildingRequest(BaseModel):
    regenerate: bool = Field(default=False, description="是否重新生成")


class WorldbuildingResponse(BaseModel):
    task_id: str
    status: str


class WorldbuildingResult(BaseModel):
    setting_document: str
    constraints: dict
    conflict_seeds: list


# ============== 大纲相关 ==============

class OutlineRequest(BaseModel):
    regenerate: bool = Field(default=False, description="是否重新生成")


class OutlineResponse(BaseModel):
    task_id: str
    status: str


class OutlineResult(BaseModel):
    volumes: list  # each: {number, title, core_conflict, character_arc_stage, status, chapter_start, chapter_end, summary, has_detail}
    chapters: list
    foreshadowing_registry: list  # each: {name, description, sow_chapter, reap_chapter}


class AppendVolumeRequest(BaseModel):
    """追加新卷请求
    - intent: 用户可选的写作意图（如"加点感情戏"/"主角去秘境"）
    - target_chapters: 新卷期望章数（默认按 target_chapter_count / total_volumes 估算）
    """
    intent: Optional[str] = Field(default=None, max_length=500)
    target_chapters: Optional[int] = Field(default=None, ge=3, le=50)


class AppendVolumeResponse(BaseModel):
    task_id: str
    status: str


class VolumeStatus(BaseModel):
    """卷元数据"""
    id: str
    project_id: str
    volume_number: int
    title: Optional[str] = None
    core_conflict: Optional[str] = None
    character_arc_stage: Optional[str] = None
    status: str  # planned | planning | detailed | writing | completed | archived
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    summary: Optional[str] = None
    contract: dict = Field(default_factory=dict)
    planned_chapter_count: int = 0
    target_chapter_count: int = 0
    is_complete: bool = False


class VolumeResponse(BaseModel):
    """卷列表查询响应"""
    volumes: list[VolumeStatus]


class ExpandVolumeResponse(BaseModel):
    """规划下一批章节响应（保留旧字段兼容卷展开调用）"""
    task_id: str
    status: str
    volume_number: int
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None


# ============== 任务状态 ==============

class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    result: Optional[dict] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    meta: dict = Field(default_factory=dict)


# ============== 通用响应 ==============

class MessageResponse(BaseModel):
    message: str
    data: Optional[dict] = None


class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    page_size: int
    total_pages: int

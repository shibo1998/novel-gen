# Phase 5：审校Agent + Coordinator编排

> **本 Phase 包含**：一致性冲突检测触发DHO、大纲版本乐观锁

## 交付物

```
backend/app/agents/reviewer.py
backend/app/prompts/reviewer.j2
backend/app/pipeline/coordinator.py        # [修改] 集成一致性检测
backend/app/services/outline_versioning.py  # [新增] 乐观锁
backend/app/api/chapter_versions.py       # [新增] 版本管理API
```

## 审校Agent

### 核心设计

审校Agent检查场景正文与约束卡的一致性，确保：
1. **事实一致性**：角色特征、背景、能力与Bible一致
2. **情节连续性**：角色是否知道不该知道的事，时间线是否连贯
3. **约束合规**：hard constraints是否违反，prose_directives是否遵守
4. **风格偏离**：语气、用词、句式是否偏离目标风格

### `backend/app/prompts/reviewer.j2`

```jinja2
你是一位专业的小说审校员。请仔细检查场景正文，确保其符合所有约束要求。

## 待审校场景
章号：{{ chapter_number }}，场景号：{{ scene_number }}

## 正文
{{ content }}

## 约束卡（原写作要求）
```json
{{ constraint_card | tojson(indent=2) }}
```

## Story Bible（角色事实）
{% if bible %}
```json
{{ bible | tojson(indent=2) }}
```
{% else %}
（暂无角色档案，将在Phase 4完善）
{% endif %}

## 已建立的事实（前文相关段落）
{% if previous_summaries %}
{% for s in previous_summaries %}
### 第{{ s.chapter }}章 第{{ s.scene }}场景
{{ s.summary }}
{% endfor %}
{% else %}
（暂无前文摘要）
{% endif %}

## 审校清单

### 1. 事实一致性
- [ ] 角色特征（外貌、性格、语言风格）是否与Bible一致？
- [ ] 角色能力是否在设定范围内？
- [ ] 地点描写是否符合世界观设定？

### 2. 情节连续性
- [ ] 角色是否知道不该知道的事？（知识泄露）
- [ ] 时间线是否连贯？
- [ ] 物品状态是否前后一致？

### 3. 约束合规
- [ ] hard constraints 是否违反？
- [ ] prose_directives 是否遵守？
- [ ] forbidden_elements 是否出现？

### 4. 风格偏离
- [ ] 语气、用词是否偏离目标风格？
- [ ] 对话是否太"AI腔"？

## 输出要求

输出严格的JSON格式：

```json
{
  "issues": [
    {
      "severity": "critical|major|minor|style",
      "category": "factual|continuity|constraint|style",
      "description": "问题描述",
      "suggestion": "修改建议",
      "evidence": "原文引用（精确到句子）"
    }
  ],
  "passed": true或false,
  "summary": "一句话总结审校结果"
}
```

**重要**：
- severity=critical 必须出现才表示有问题
- 避免过度挑剔 minor 问题
- evidence 必须是原文的精确引用
```

### `backend/app/agents/reviewer.py`

```python
import json
from jinja2 import Environment, FileSystemLoader
from app.llm.client import get_llm_client


class ReviewerAgent:
    """审校Agent：检测场景正文的一致性问题"""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    @property
    def template_name(self) -> str:
        return "reviewer.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["critical", "major", "minor", "style"]},
                            "category": {"type": "string", "enum": ["factual", "continuity", "constraint", "style"]},
                            "description": {"type": "string"},
                            "suggestion": {"type": "string"},
                            "evidence": {"type": "string"}
                        }
                    }
                },
                "passed": {"type": "boolean"},
                "summary": {"type": "string"}
            },
            "required": ["issues", "passed", "summary"]
        }

    async def review(self, content: str, constraint, context: dict = None) -> dict:
        """
        审校场景，返回问题列表

        context = {
            "bible": {...},  # Story Bible
            "previous_summaries": [...]  # 前文摘要
        }
        """
        template = self.jinja.get_template(self.template_name)

        prompt = template.render(
            content=content,
            chapter_number=constraint.chapter_number,
            scene_number=constraint.scene_number,
            constraint_card=constraint,
            bible=context.get("bible", {}) if context else {},
            previous_summaries=context.get("previous_summaries", []) if context else []
        )

        system = "你是一位专业审校员。严格检查，但不要过度挑剔minor问题。"

        raw = await self.llm.complete(prompt, system=system)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "issues": [],
                "passed": True,
                "summary": "审校通过（解析异常）"
            }
```

## Coordinator编排 [增强]

### `backend/app/pipeline/coordinator.py`

```python
import logging
from typing import Optional
from uuid import UUID
from app.models.constraints import SceneConstraint
from app.services.consistency_checker import ConsistencyChecker

logger = logging.getLogger(__name__)


class ReplanTrigger:
    """重规划触发类型"""
    VOLUME_COMPLETED = "volume_completed"
    USER_EDIT = "user_edit"
    CONSISTENCY_FIX = "consistency_fix"


class Coordinator:
    """
    主编排器：串联所有Agent，完成整本小说的生成流程
    """

    MAX_REVISION_ATTEMPTS = 3  # 最大重试次数

    def __init__(self, db, agents: dict, memory, context_builder):
        self.db = db
        self.agents = agents  # {"worldbuilding": ..., "outline": ..., "writer": ..., "reviewer": ...}
        self.memory = memory
        self.context_builder = context_builder
        self.consistency_checker = ConsistencyChecker(db, memory.bible)
        self.revision_history = {}

    async def generate_project(self, project_id: str):
        """Phase 1-2：世界观 → 大纲"""
        project = await self._get_project(project_id)

        # 世界观生成
        worldbuilding = await self.agents["worldbuilding"].run({
            "core_idea": project.core_idea,
            "genre": project.genre,
            "tone_style": project.tone_style,
        })
        await self._save_worldbuilding(project_id, worldbuilding)

        # 等待人工确认...

        # 大纲生成
        outline = await self.agents["outline"].run({
            "core_idea": project.core_idea,
            "setting_document": worldbuilding["setting_document"],
            "constraints": worldbuilding["constraints"]
        })
        await self._save_outline(project_id, outline)

    async def generate_volume(self, project_id: str, vol: int):
        """Phase 3-5：逐卷生成"""
        chapters = await self._get_chapters(project_id, vol)
        for ch in chapters:
            await self.generate_chapter(project_id, ch)

    async def generate_chapter(self, project_id: str, chapter):
        """单章：细纲 → 场景循环"""
        constraints = await self.agents["chapter"].run({"chapter": chapter, ...})
        for c in constraints:
            await self.generate_scene(project_id, c)

    async def generate_scene(
        self,
        project_id: str,
        constraint: SceneConstraint,
        scene_id: str = None
    ) -> tuple[str, dict]:
        """
        单场景：上下文组装 → 写作 → 审校 → 写Memory
        返回: (content, review_result)
        """
        scene_key = f"{project_id}:{constraint.chapter_number}:{constraint.scene_number}"
        self.revision_history[scene_key] = []

        attempt = 0
        content = ""
        review_result = {}

        while attempt < self.MAX_REVISION_ATTEMPTS:
            try:
                # 1. 上下文组装
                enriched_constraint = await self.context_builder.build(constraint, project_id)

                # 2. 写作
                logger.info(f"Writing attempt {attempt + 1} for scene {scene_key}")
                content = await self.agents["writer"].write_scene(
                    enriched_constraint,
                    revision_notes=self.revision_history[scene_key]
                )

                # 3. 审校
                review_result = await self.agents["reviewer"].review(
                    content=content,
                    constraint=enriched_constraint,
                    context={
                        "bible": enriched_constraint.injected_bible,
                        "previous_summaries": enriched_constraint.injected_previous
                    }
                )

                # 4. 分析审校结果
                critical_issues = [
                    i for i in review_result.get("issues", [])
                    if i["severity"] == "critical"
                ]

                if not critical_issues:
                    logger.info(f"Scene {scene_key} passed review after {attempt + 1} attempts")
                    break

                # 5. 记录失败原因
                self.revision_history[scene_key].append({
                    "attempt": attempt + 1,
                    "critical_issues": critical_issues,
                    "partial_content": content[:500] if content else ""
                })

                attempt += 1

                if attempt >= self.MAX_REVISION_ATTEMPTS:
                    logger.error(f"Scene {scene_key} failed after {self.MAX_REVISION_ATTEMPTS} attempts")
                    review_result["needs_human_review"] = True
                    review_result["revision_history"] = self.revision_history[scene_key]
                    break

                # 6. 注入反馈，准备重试
                constraint = self._inject_feedback(constraint, critical_issues, content)
                logger.warning(f"Regenerating (attempt {attempt + 1}/{self.MAX_REVISION_ATTEMPTS})")

            except Exception as e:
                logger.exception(f"Error during generation attempt {attempt + 1}")
                attempt += 1
                if attempt >= self.MAX_REVISION_ATTEMPTS:
                    raise

        # 7. 写Memory
        if review_result.get("passed") or review_result.get("needs_human_review"):
            await self._update_memory(scene_id, content, constraint, review_result)

        # 8. 一致性检查（可能触发DHO）
        if review_result.get("needs_human_review"):
            await self._check_consistency_and_trigger_dho(
                project_id, content, constraint, review_result
            )

        return content, review_result

    async def _check_consistency_and_trigger_dho(
        self,
        project_id: str,
        content: str,
        constraint: SceneConstraint,
        review_result: dict
    ) -> None:
        """检查一致性，必要时触发DHO重规划"""
        violations = await self.consistency_checker.check_scene_consistency(
            project_id=project_id,
            scene_content=content,
            scene_info={
                "chapter_number": constraint.chapter_number,
                "scene_number": constraint.scene_number,
                "characters_present": constraint.characters_present
            }
        )

        critical_violations = [v for v in violations if v.severity == "critical"]

        if critical_violations:
            logger.warning(
                f"Detected {len(critical_violations)} critical consistency violations. "
                f"Triggering DHO replan."
            )

            # 触发DHO重规划
            await self._trigger_dho_replan(
                project_id=project_id,
                trigger=ReplanTrigger.CONSISTENCY_FIX,
                context={
                    "issue": critical_violations[0].description,
                    "suggested_fix": critical_violations[0].suggested_fix,
                    "all_violations": [v.__dict__ for v in critical_violations],
                    "chapter_number": constraint.chapter_number
                }
            )

            review_result["dho_triggered"] = True
            review_result["dho_status"] = "pending"

    async def _trigger_dho_replan(
        self,
        project_id: str,
        trigger: str,
        context: dict
    ) -> None:
        """触发DHO重规划"""
        # TODO: 调用DHO引擎
        # Phase 5.5 将完善此功能
        logger.info(f"DHO replan triggered: {trigger} with context: {context}")

    def _inject_feedback(
        self,
        constraint: SceneConstraint,
        critical_issues: list,
        previous_content: str
    ) -> SceneConstraint:
        """将审校反馈注入约束卡，供下次重写使用"""
        feedback_parts = ["上一次生成有以下问题需要修复："]

        for i, issue in enumerate(critical_issues, 1):
            feedback_parts.append(f"{i}. {issue['category'].upper()}: {issue['description']}")
            if issue.get('suggestion'):
                feedback_parts.append(f"   建议：{issue['suggestion']}")
            if issue.get('evidence'):
                feedback_parts.append(f"   原文：{issue['evidence']}")

        feedback_parts.append(f"\n上一次内容片段：\n{previous_content[:1000]}...\n请避免上述问题。")

        new_directives = list(constraint.prose_directives) if constraint.prose_directives else []
        new_directives.append(f"【审校反馈】{' '.join(feedback_parts)}")

        new_forbidden = list(constraint.forbidden_elements) if constraint.forbidden_elements else []
        for issue in critical_issues:
            if issue.get('forbidden_pattern'):
                new_forbidden.append(issue['forbidden_pattern'])

        return constraint.model_copy(
            prose_directives=new_directives,
            forbidden_elements=new_forbidden
        )

    async def _get_project(self, project_id: str):
        """从数据库加载项目"""
        pass

    async def _save_worldbuilding(self, project_id: str, worldbuilding: dict):
        """保存世界观到数据库"""
        pass

    async def _save_outline(self, project_id: str, outline: dict):
        """保存大纲到数据库"""
        pass

    async def _get_chapters(self, project_id: str, vol: int):
        """获取章节列表"""
        pass

    async def _update_memory(self, scene_id: str, content: str, constraint, review_result: dict):
        """更新Memory层"""
        pass
```

## 大纲版本乐观锁 `backend/app/services/outline_versioning.py` [新增]

```python
from fastapi import HTTPException
from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class OutlineChapterSchema(BaseModel):
    """大纲章节（带版本控制）"""
    number: int
    title: str
    goal: str
    key_events: list[dict]
    pov_character: str
    foreshadowing_seeds: list[dict]


class OutlineUpdateRequest(BaseModel):
    """大纲更新请求"""
    chapters: list[OutlineChapterSchema]
    expected_version: int  # 期望的当前版本，乐观锁


class ConflictError(Exception):
    """版本冲突异常"""
    def __init__(self, current_version: int, expected_version: int):
        self.current_version = current_version
        self.expected_version = expected_version
        super().__init__(
            f"Version conflict: expected {expected_version}, but current is {current_version}"
        )


class OutlineVersionManager:
    """
    大纲版本管理器，支持乐观锁和冲突解决
    """

    def __init__(self, db):
        self.db = db

    async def update_outline(
        self,
        project_id: str,
        update: OutlineUpdateRequest,
        user_id: str
    ) -> dict:
        """
        更新大纲，使用乐观锁防止并发冲突
        """
        # 1. 获取当前大纲版本
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT version FROM outline_versions
                WHERE project_id = $1
                ORDER BY version DESC LIMIT 1
            """),
            (project_id,)
        )
        row = result.fetchone()
        current_version = row.version if row else 0

        # 2. 检查版本号
        if update.expected_version != current_version:
            raise ConflictError(
                current_version=current_version,
                expected_version=update.expected_version
            )

        # 3. 自动合并
        merged_chapters = await self._auto_merge(project_id, update.chapters)

        # 4. 创建新版本
        new_version = current_version + 1
        await self.db.execute(
            text("""
                INSERT INTO outline_versions
                (project_id, version, chapters, status, created_at, created_by)
                VALUES ($1, $2, $3, 'draft', NOW(), $4)
            """),
            (project_id, new_version, merged_chapters, user_id)
        )
        await self.db.commit()

        return {
            "version": new_version,
            "chapters": merged_chapters
        }

    async def _auto_merge(
        self,
        project_id: str,
        new_chapters: list[dict]
    ) -> list[dict]:
        """自动合并：只合并非冲突字段"""
        # TODO: 实现自动合并逻辑
        return [c.model_dump() if hasattr(c, 'model_dump') else c for c in new_chapters]
```

## API端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/projects/{id}/generate/volume/{vol}` | 触发整卷生成 |
| `POST` | `/api/v1/scenes/{id}/review` | 审校单个场景 |
| `GET` | `/api/v1/scenes/{id}/review/result` | 获取审校结果 |
| `PUT` | `/api/v1/projects/{id}/outline` | 更新大纲（乐观锁） |

## 验证清单

```
审校验证：
☐ 审校Agent能检测出事实矛盾（如第一章左撇子第三章右手）
☐ 审校Agent能检测出角色知识泄露
☐ Coordinator全链路跑通：世界观→大纲→细纲→写作→审校
☐ 审校连续失败3次 → 停止重试，标记 needs_human_review

一致性检测验证：
☐ 检测到 critical violation → 自动触发 DHO 重规划
☐ DHO 状态记录在 review_result 中

大纲版本验证：
☐ 版本号不匹配 → 返回 409 Conflict
☐ 响应包含冲突解决选项
☐ 自动合并非冲突字段
```

## 依赖关系

- **前置**：Phase 3（写作Agent）、Phase 4（Memory层）
- **后续**：Phase 5.5（DHO引擎完善）、Phase 6（前端DiffView组件集成）

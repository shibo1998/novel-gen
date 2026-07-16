"""Context Builder - 组装写作上下文"""
import logging
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.bible_store import BibleStore
from app.models.constraints import SceneConstraint
from app.models.domain import Entity, Foreshadowing, PlotThread, Project, ProjectStyleVersion
from app.services.bible_version_manager import BibleVersionManager
from app.services.context_budget import ContextBudgetManager, ContextSlice, get_budget_manager
from app.services.memory_records import MemoryRecordStore

logger = logging.getLogger(__name__)


class ContextBuilder:
    """上下文构建器 - 为写作Agent组装必要的上下文信息"""

    def __init__(self, db: AsyncSession, model: str = "gpt-4o-mini"):
        self.db = db
        self.bible_store = BibleStore(db)
        self.memory_store = MemoryRecordStore(db)
        self.budget_manager: ContextBudgetManager = get_budget_manager(model=model)

    async def build_context(
        self,
        project_id: str,
        constraint: SceneConstraint
    ) -> Dict:
        """
        为场景构建完整上下文（Phase 10: 集成预算管理器）

        Returns:
            包含角色档案、前文摘要、伏笔等信息的字典
        """
        context = {
            "injected_bible": {},
            "injected_previous": [],
            "injected_foreshadowings": [],
            "memory_retrieval": [],
            "injected_plot_threads": [],
        }

        # 1. 注入角色档案
        if constraint.characters_present:
            characters = await self.bible_store.get_characters(
                project_id,
                constraint.characters_present
            )
            context["injected_bible"] = characters

        # 2. 获取POV角色档案
        if constraint.pov_character:
            pov_char = await self.bible_store.get_character(
                project_id,
                constraint.pov_character
            )
            if pov_char:
                context["injected_bible"][constraint.pov_character] = pov_char

        # 3. 获取前文摘要
        context["injected_previous"] = await self._get_previous_summaries(
            project_id,
            constraint.chapter_number,
            constraint.scene_number
        )

        # 4. 获取活跃伏笔
        context["injected_foreshadowings"] = await self._get_active_foreshadowings(
            project_id,
            constraint.chapter_number
        )
        context["memory_retrieval"] = await self._get_relevant_memories(project_id, constraint)
        context["injected_plot_threads"] = await self._get_active_plot_threads(
            project_id, constraint.chapter_number
        )

        return context

    async def build_context_with_budget(
        self,
        project_id: str,
        constraint: SceneConstraint,
    ) -> tuple[Dict, Dict]:
        """
        带预算管理的上下文构建（Phase 10 新增）。

        Returns:
            (context_dict, allocation_report_dict)
        """
        # Step 1: 组装全部候选切片
        slices: List[ContextSlice] = []

        # constraint_card
        cc_content = constraint.model_dump_json() if constraint else "{}"
        slices.append(ContextSlice("constraint_card", cc_content, "critical"))

        # active_character_bible
        bible_content = ""
        if constraint.characters_present:
            versioned_bible = await BibleVersionManager(self.db).get_snapshot(
                project_id, constraint.chapter_number
            )
            chars = {
                name: data
                for name, data in versioned_bible["characters"].items()
                if name in constraint.characters_present
            }
            if chars:
                import json
                bible_content = json.dumps(chars, ensure_ascii=False)
        slices.append(ContextSlice("active_character_bible", bible_content, "critical"))

        # recent_events
        prev_summaries = await self._get_previous_summaries(
            project_id, constraint.chapter_number, constraint.scene_number
        )
        recent_content = "\n---\n".join(
            f"第{s['chapter']}章 场景{s['scene']}：{s['summary']}"
            for s in prev_summaries[-5:]
        )
        slices.append(ContextSlice("recent_events", recent_content, "high"))

        memories = await self._get_relevant_memories(project_id, constraint)
        if memories:
            import json
            slices.append(
                ContextSlice("memory_retrieval", json.dumps(memories, ensure_ascii=False), "high")
            )

        # Due foreshadowings are critical so context compression cannot discard them.
        fses = await self._get_active_foreshadowings(project_id, constraint.chapter_number)
        import json
        due_foreshadowings = [fs for fs in fses if fs["is_due"]]
        active_foreshadowings = [fs for fs in fses if not fs["is_due"]]
        due_content = "\n---\n".join(
            json.dumps(fs, ensure_ascii=False) for fs in due_foreshadowings
        )
        active_content = "\n---\n".join(
            json.dumps(fs, ensure_ascii=False) for fs in active_foreshadowings
        )
        slices.append(ContextSlice("due_foreshadowings", due_content, "critical"))
        slices.append(ContextSlice("active_foreshadowings", active_content, "high"))

        plot_threads = await self._get_active_plot_threads(
            project_id, constraint.chapter_number
        )
        if plot_threads:
            import json
            slices.append(
                ContextSlice(
                    "active_plot_threads",
                    json.dumps(plot_threads, ensure_ascii=False),
                    "high",
                )
            )

        # chapter_summaries
        all_summaries = await self._get_chapter_summaries(
            project_id, constraint.chapter_number
        )
        summary_content = "\n---\n".join(
            f"第{chs['chapter']}章：{chs['summary']}"
            for chs in all_summaries
        )
        slices.append(ContextSlice("chapter_summaries", summary_content, "medium"))

        # world_rules
        world_rules_content = await self._get_world_rules(project_id)
        slices.append(ContextSlice("world_rules", world_rules_content, "medium"))

        project_style = await self._get_active_style(project_id)
        if project_style:
            import json
            slices.append(
                ContextSlice(
                    "project_style",
                    json.dumps(project_style, ensure_ascii=False),
                    "high",
                )
            )

        # historical_events（默认空，仅 RAG 命中时填充）
        slices.append(ContextSlice("historical_events", "", "low"))

        # Step 2: 预算分配
        allocated, report = self.budget_manager.allocate(
            slices, constraint.chapter_number
        )

        # Step 3: 日志警告
        if report.dropped_categories:
            logger.warning(
                "第%d章上下文预算不足，丢弃: %s | 利用率: %s",
                constraint.chapter_number,
                report.dropped_categories,
                report.utilization,
            )

        # Step 4: 构建最终上下文字典
        context: Dict[str, object] = {}
        for s in allocated:
            if s.category == "constraint_card":
                pass  # constraint already passed in
            elif s.category == "active_character_bible":
                import json
                try:
                    context["injected_bible"] = json.loads(s.content) if s.content else {}
                except Exception:
                    context["injected_bible"] = {}
            elif s.category == "recent_events":
                context["injected_previous"] = [
                    {"chapter": i + 1, "summary": line}
                    for i, line in enumerate(s.content.split("\n---\n"))
                    if line.strip()
                ]
            elif s.category in ("due_foreshadowings", "active_foreshadowings"):
                import json
                parsed_foreshadowings = []
                for item in s.content.split("\n---\n"):
                    if not item.strip():
                        continue
                    try:
                        parsed_foreshadowings.append(json.loads(item))
                    except json.JSONDecodeError:
                        logger.warning("Dropped truncated foreshadowing context entry")
                context.setdefault("injected_foreshadowings", []).extend(parsed_foreshadowings)
            elif s.category == "memory_retrieval":
                import json
                context["memory_retrieval"] = json.loads(s.content) if s.content else []
            elif s.category == "active_plot_threads":
                import json
                context["injected_plot_threads"] = json.loads(s.content) if s.content else []
            elif s.category == "chapter_summaries":
                context["chapter_summaries"] = s.content
            elif s.category == "world_rules":
                context["world_rules"] = s.content
            elif s.category == "project_style":
                import json
                context["injected_style"] = json.loads(s.content)

        return context, report.to_dict()

    async def _get_active_style(self, project_id: str) -> dict:
        result = await self.db.execute(
            select(ProjectStyleVersion)
            .join(Project, Project.active_style_version_id == ProjectStyleVersion.id)
            .where(Project.id == project_id)
        )
        style = result.scalar_one_or_none()
        return style.profile_json if style else {}

    async def _get_chapter_summaries(
        self,
        project_id: str,
        current_chapter: int,
    ) -> List[Dict]:
        """获取所有已确认章节的摘要（用于 budget 分配）"""
        memories = await self.memory_store.retrieve(
            project_id=project_id,
            current_chapter=current_chapter,
            memory_types=("chapter_summary",),
            limit=10,
        )
        return [
            {"chapter": item["chapter"], "summary": item["summary"]}
            for item in sorted(memories, key=lambda item: item["chapter"] or 0)
        ]

    async def get_planning_context(
        self,
        project_id: str,
        current_chapter: int,
        query: str,
    ) -> Dict[str, List[Dict]]:
        """Return actual chapter history and semantic memories for chapter planning."""
        summaries = await self._get_chapter_summaries(project_id, current_chapter)
        memories = await self.memory_store.retrieve(
            project_id=project_id,
            current_chapter=current_chapter,
            query=query,
            memory_types=("scene_event",),
            limit=10,
        )
        return {"chapter_summaries": summaries, "relevant_memories": memories}

    async def _get_relevant_memories(
        self,
        project_id: str,
        constraint: SceneConstraint,
    ) -> List[Dict]:
        query = " ".join(
            [
                constraint.scene_title,
                constraint.narrative_goal,
                constraint.pov_character,
                *constraint.characters_present,
                *constraint.reader_should_know,
            ]
        )
        return await self.memory_store.retrieve(
            project_id=project_id,
            current_chapter=constraint.chapter_number,
            query=query,
            limit=10,
        )

    async def _get_world_rules(self, project_id: str) -> str:
        """获取世界观规则"""
        result = await self.db.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.type.in_(("rule", "world_rule")),
            )
        )
        entities = result.scalars().all()
        return "\n\n".join(
            f"【{e.display_name}】{e.description or ''}"
            for e in entities if e.description
        )

    async def _get_active_plot_threads(
        self,
        project_id: str,
        current_chapter: int,
    ) -> List[Dict]:
        rows = (
            await self.db.execute(
                select(PlotThread).where(
                    PlotThread.project_id == project_id,
                    PlotThread.status == "active",
                    PlotThread.start_chapter <= current_chapter,
                )
            )
        ).scalars().all()
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description or "",
                "start_chapter": row.start_chapter,
                "end_chapter": row.end_chapter,
                "priority": row.priority,
            }
            for row in rows
            if row.end_chapter is None or row.end_chapter >= current_chapter
        ]

    async def _get_previous_summaries(
        self,
        project_id: str,
        current_chapter: int,
        current_scene: int
    ) -> List[Dict]:
        """获取前文相关场景的摘要"""
        return await self.memory_store.previous_summaries(
            project_id=project_id,
            current_chapter=current_chapter,
            current_scene=current_scene,
            limit=5,
        )

    async def _get_active_foreshadowings(
        self,
        project_id: str,
        current_chapter: int
    ) -> List[Dict]:
        """获取当前章节活跃的伏笔"""
        result = await self.db.execute(
            select(Foreshadowing).where(
                Foreshadowing.project_id == project_id,
                Foreshadowing.sow_chapter <= current_chapter,
                Foreshadowing.status == "pending"
            )
        )
        foreshadowings = result.scalars().all()

        return [
            {
                "id": str(fs.id),
                "name": fs.name,
                "description": fs.description,
                "sow_chapter": fs.sow_chapter,
                "reap_chapter": fs.reap_chapter,
                "is_due": fs.reap_chapter is not None and fs.reap_chapter <= current_chapter,
            }
            for fs in foreshadowings
        ]

    def enrich_constraint(
        self,
        constraint: SceneConstraint,
        context: Dict
    ) -> SceneConstraint:
        """
        将上下文注入到约束卡

        Returns:
            增强后的约束卡
        """
        return constraint.model_copy(
            injected_bible=context.get("injected_bible"),
            injected_previous=context.get("injected_previous"),
            injected_foreshadowings=context.get("injected_foreshadowings"),
            injected_memories=context.get("memory_retrieval"),
            injected_plot_threads=context.get("injected_plot_threads"),
            injected_style=context.get("injected_style"),
            injected_chapter_summaries=context.get("chapter_summaries"),
            injected_world_rules=context.get("world_rules"),
        )


# 依赖注入工厂
async def create_context_builder(db: AsyncSession, model: str = "gpt-4o-mini") -> ContextBuilder:
    """创建 ContextBuilder 实例"""
    return ContextBuilder(db, model=model)

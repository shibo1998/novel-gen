from .base import BaseAgent


class OutlineSkeletonAgent(BaseAgent):
    """大纲骨架 Agent —— 第一阶段

    只输出全书卷结构 + 全局伏笔表，不包含具体章节。
    输出体量极小（< 1k token），不会触发 max_tokens 截断。
    """

    @property
    def template_name(self) -> str:
        return "outline_skeleton.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "volumes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "number": {"type": "integer", "description": "卷号"},
                            "title": {"type": "string", "description": "卷名"},
                            "core_conflict": {"type": "string", "description": "本卷核心冲突"},
                            "character_arc_stage": {
                                "type": "string",
                                "description": "主角在本卷所处的弧线阶段",
                            },
                            "volume_summary": {
                                "type": "string",
                                "description": "本卷一句话剧情概要（Pass 2 会展开）",
                            },
                            "opening_state": {"type": "string"},
                            "ending_state": {"type": "string"},
                            "handoff_hook": {"type": "string"},
                            "must_resolve": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "number",
                            "title",
                            "core_conflict",
                            "character_arc_stage",
                            "volume_summary",
                            "opening_state",
                            "ending_state",
                            "handoff_hook",
                            "must_resolve",
                        ],
                    },
                },
                "foreshadowing_registry": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "sow_chapter_hint": {
                                "type": "integer",
                                "description": "预计播种章节（建议值，具体由 Pass 2 微调）",
                            },
                            "reap_chapter_hint": {
                                "type": ["integer", "null"],
                                "description": "预期回收章节（可空）",
                            },
                        },
                        "required": ["name", "description"],
                    },
                },
            },
            "required": ["volumes", "foreshadowing_registry"],
        }


class OutlineChapterBatchAgent(BaseAgent):
    """章节批次 Agent —— 每次只生成当前卷接下来至多五章。

    接收：
      - 全书骨架（来自 Pass 1）
      - 该卷的 volume_summary
      - 已规划章节（避免编号冲突）
      - 全局伏笔表（保证一致性）

    输出：
      - 指定连续章号的细纲
      - 本批次新增 / 调整后的伏笔条目
    """

    def __init__(self, volume_number: int):
        super().__init__()
        self.volume_number = volume_number

    @property
    def template_name(self) -> str:
        return "outline_chapter_batch.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "chapters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "volume": {"type": "integer"},
                            "number": {"type": "integer"},
                            "title": {"type": "string"},
                            "goal": {"type": "string"},
                            "key_events": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "event_name": {"type": "string"},
                                        "brief": {"type": "string"},
                                    },
                                    "required": ["event_name", "brief"],
                                },
                            },
                            "pov_character": {"type": "string"},
                            "foreshadowing_seeds": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "brief": {"type": "string"},
                                    },
                                    "required": ["name", "brief"],
                                },
                            },
                        },
                        "required": ["volume", "number", "title", "goal"],
                    },
                },
                "foreshadowing_additions": {
                    "type": "array",
                    "description": "本卷新埋 / 微调的伏笔条目（合并到全局伏笔表）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "sow_chapter": {"type": "integer"},
                            "reap_chapter": {"type": ["integer", "null"]},
                        },
                        "required": ["name", "description", "sow_chapter"],
                    },
                },
            },
            "required": ["chapters", "foreshadowing_additions"],
        }

# Backward-compatible import name for older modules. New code uses chapter-batch terminology.
OutlineVolumeAgent = OutlineChapterBatchAgent


# ─────────────────────────────────────────────
# 向后兼容：保留原 OutlineAgent，给可能的旧调用兜底
# ─────────────────────────────────────────────

class OutlineAgent(BaseAgent):
    """兼容旧调用：直接当作全量细纲 prompt 使用（已废弃，建议拆 Pass1/Pass2）"""

    @property
    def template_name(self) -> str:
        return "outline.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "volumes": {"type": "array", "items": {"type": "object"}},
                "chapters": {"type": "array", "items": {"type": "object"}},
                "foreshadowing_registry": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["chapters"],
        }

from .base import BaseAgent


class WorldbuildingAgent(BaseAgent):
    """世界观生成 Agent"""

    @property
    def template_name(self) -> str:
        return "worldbuilding.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "setting_document": {
                    "type": "string",
                    "description": "完整的世界设定文档（Markdown格式）"
                },
                "constraints": {
                    "type": "object",
                    "properties": {
                        "hard": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "不可违反的世界规则"
                        },
                        "soft": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "风格指南"
                        }
                    },
                    "required": ["hard", "soft"]
                },
                "conflict_seeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "stake": {"type": "string"}
                        },
                        "required": ["name", "description", "stake"]
                    },
                    "description": "世界内在矛盾"
                }
            },
            "required": ["setting_document", "constraints", "conflict_seeds"]
        }

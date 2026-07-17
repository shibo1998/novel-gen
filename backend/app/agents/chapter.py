from .base import BaseAgent


class ChapterAgent(BaseAgent):
    """章节展开Agent - 将大纲章节展开为场景约束卡"""

    @property
    def template_name(self) -> str:
        return "chapter.j2"

    def output_schema(self) -> dict:
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapter_number": {"type": "integer"},
                    "scene_number": {"type": "integer"},
                    "scene_title": {"type": "string"},
                    "narrative_goal": {"type": "string"},
                    "scene_function": {"type": "string"},
                    "pov_character": {"type": "string"},
                    "characters_present": {"type": "array", "items": {"type": "string"}},
                    "character_emotional_states": {"type": "object"},
                    "opening_emotion": {"type": "string"},
                    "closing_emotion": {"type": "string"},
                    "emotional_beats": {"type": "array", "items": {"type": "string"}},
                    "reader_should_know": {"type": "array", "items": {"type": "string"}},
                    "reader_should_not_know": {"type": "array", "items": {"type": "string"}},
                    "reader_experience_goal": {"type": "string"},
                    "prose_directives": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "forbidden_elements": {"type": "array", "items": {"type": "string"}},
                    "foreshadowing_ids": {"type": "array", "items": {"type": "string"}},
                    "word_budget": {"type": "integer", "minimum": 500, "maximum": 3000}
                },
                "required": ["chapter_number", "scene_number", "scene_title", "narrative_goal",
                           "scene_function", "pov_character", "reader_experience_goal",
                           "word_budget"]
            }
        }

    def _validate(self, data: dict) -> dict:
        if not isinstance(data, list) or not 2 <= len(data) <= 5:
            raise ValueError("ChapterAgent must return 2-5 scenes")
        if not all(isinstance(item, dict) for item in data):
            raise ValueError("ChapterAgent scenes must be JSON objects")
        return data

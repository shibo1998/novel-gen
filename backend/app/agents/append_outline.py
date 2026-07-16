from app.agents.base import BaseAgent


class AppendVolumeAgent(BaseAgent):
    """Create one complete volume contract without chapter details."""

    @property
    def template_name(self) -> str:
        return "append_outline.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "core_conflict": {"type": "string"},
                        "character_arc_stage": {"type": "string"},
                        "volume_summary": {"type": "string"},
                        "opening_state": {"type": "string"},
                        "ending_state": {"type": "string"},
                        "handoff_hook": {"type": "string"},
                        "must_resolve": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "title",
                        "core_conflict",
                        "character_arc_stage",
                        "volume_summary",
                        "opening_state",
                        "ending_state",
                        "handoff_hook",
                        "must_resolve",
                    ],
                }
            },
            "required": ["volume"],
        }

    def _validate(self, data: dict) -> dict:
        volume = data.get("volume")
        if not isinstance(volume, dict):
            raise ValueError("Append volume result has no volume contract")
        required = self.output_schema()["properties"]["volume"]["required"]
        missing = [field for field in required if not volume.get(field)]
        if missing:
            raise ValueError(f"Appended volume contract missing: {', '.join(missing)}")
        return data

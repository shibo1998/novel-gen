"""Character profile expansion and dialogue simulation agent."""

import json
import time

from jinja2 import Environment, FileSystemLoader

from app.llm.client import collect_stream_text, get_llm_client
from app.services.llm_observability import LLMCallObserver


class CharacterAgent:
    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    async def extend_profile(
        self,
        name: str,
        description: str,
        existing: dict,
        *,
        project_id: str | None = None,
    ) -> dict:
        prompt = f"""为小说角色生成结构化角色卡，只输出 JSON。
角色名：{name}
简介：{description}
已有数据：{json.dumps(existing, ensure_ascii=False)}
必须包含 action_beats（5-10项）、speech_profile、psychology、core_desire、arc_stage。
speech_profile 包含 avg_sentence_length、question_frequency、rhetorical_questions、trailing_thoughts、signature_patterns。"""
        return await self._complete_observed(
            prompt, "你是小说角色设计师，只输出 JSON。", project_id
        )

    async def simulate(
        self,
        character: dict,
        context: dict,
        memories: list[dict],
        *,
        project_id: str | None = None,
    ) -> dict:
        normalized = dict(character)
        normalized.setdefault("action_beats", [])
        normalized.setdefault(
            "speech_profile",
            {
                "avg_sentence_length": 12,
                "rhetorical_questions": False,
                "trailing_thoughts": False,
                "signature_patterns": [],
            },
        )
        normalized.setdefault(
            "psychology",
            {"big_five": {"openness": 3, "extraversion": 3, "neuroticism": 3}},
        )
        prompt = self.jinja.get_template("character_dialogue.j2").render(
            character=normalized,
            relevant_memories=memories,
            context=context,
        )
        return await self._complete_observed(
            prompt, "你必须忠于角色卡，只输出 JSON。", project_id
        )

    async def _complete_observed(
        self, prompt: str, system: str, project_id: str | None
    ) -> dict:
        await LLMCallObserver.check_budget(project_id)
        started = time.perf_counter()
        try:
            raw = await collect_stream_text(self.llm, prompt, system=system)
            result = self._parse(raw)
        except Exception as exc:
            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=prompt,
                output="",
                started=started,
                error=exc,
            )
            raise
        await LLMCallObserver.record(
            project_id=project_id,
            agent=self.__class__.__name__,
            prompt=prompt,
            output=raw,
            started=started,
        )
        return result

    @staticmethod
    def _parse(raw: str) -> dict:
        text_value = raw.strip()
        if text_value.startswith("```json"):
            text_value = text_value[7:]
        elif text_value.startswith("```"):
            text_value = text_value[3:]
        if text_value.endswith("```"):
            text_value = text_value[:-3]
        return json.loads(text_value.strip())

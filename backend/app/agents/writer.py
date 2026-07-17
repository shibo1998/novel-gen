"""写作Agent —— Phase 9 增强版"""
import inspect
import logging

from app.agents.template_environment import create_template_environment
from app.llm.client import get_llm_client
from app.models.constraints import SceneConstraint

logger = logging.getLogger(__name__)


def _build_style_system() -> str:
    return """你是正在连载中文长篇小说的作者。
以场景委托中的事实为边界，把它写成连续、可读、有角色口感的现场。
叙述固定在 POV 角色当下能够感知和理解的范围内。
只输出纯 Markdown 场景正文，不附写作说明、分析或 JSON。"""


class WriterAgent:
    """写作Agent - 根据约束卡生成场景正文"""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = create_template_environment()

    def _build_prompt(self, constraint: SceneConstraint, revision_notes: list = None) -> str:
        """构建写作prompt"""
        template = self.jinja.get_template("writer.j2")
        return template.render(
            constraint_card=constraint,
            injected_bible=constraint.injected_bible,
            injected_previous=constraint.injected_previous,
            injected_foreshadowings=constraint.injected_foreshadowings,
            injected_memories=constraint.injected_memories,
            injected_plot_threads=constraint.injected_plot_threads,
            revision_notes=revision_notes or [],
        )

    async def write_scene(
        self,
        constraint: SceneConstraint,
        revision_notes: list = None,
    ) -> str:
        """兼容完整文本调用；Provider 请求仍使用流式传输。"""
        return await self.write_scene_stream(
            constraint,
            revision_notes=revision_notes,
        )

    async def iter_scene_stream(
        self,
        constraint: SceneConstraint,
        revision_notes: list = None,
    ):
        """Yield scene text as it arrives from the provider."""
        prompt = self._build_prompt(constraint, revision_notes)
        system = _build_style_system()
        async for chunk in self.llm.complete_stream(prompt, system=system):
            yield chunk

    async def write_scene_stream(
        self,
        constraint: SceneConstraint,
        on_token=None,
        revision_notes: list = None,
    ) -> str:
        """Collect a streamed response while optionally forwarding each token."""
        accumulated = []
        async for chunk in self.iter_scene_stream(constraint, revision_notes):
            accumulated.append(chunk)
            if on_token:
                callback_result = on_token(chunk)
                if inspect.isawaitable(callback_result):
                    await callback_result

        return "".join(accumulated)

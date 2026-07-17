"""写作Agent —— Phase 9 增强版"""
import inspect
import logging

from app.agents.style_rules import load_style_rules
from app.agents.template_environment import create_template_environment
from app.llm.client import get_llm_client
from app.models.constraints import SceneConstraint

logger = logging.getLogger(__name__)


def _build_style_system() -> str:
    rules = load_style_rules()
    vocab = rules.get("vocabulary_banlist", {})
    hard = "、".join(vocab.get("hard_ban", [])[:12])
    soft = "、".join(vocab.get("soft_ban", [])[:12])
    return f"""你是一位专业小说作家。严格按照约束卡写作，不要自由发挥。

## 全局写作约束（Phase 9，不可覆盖）

### 绝对禁止使用的句式/词汇
{hard}

### 严格限制的词汇（减少 90%）
{soft}

### 破折号限制
全文"——"不超过 3 处。

### 对话标签限制
禁止"淡淡道/冷冷道/沉声道"。用动作节拍替代一切对话标签。

### 网文口语约束
叙述词汇贴近 POV 角色的身份和日常表达，不写报告腔、会计腔、论文腔或作者评语。
精确数字只有在影响角色选择或构成剧情线索时使用，不用数字清单代替生活压力和情绪。
禁止三连同构句、对称否定枚举、上帝视角预告和空泛远景收束。
对白允许省略、回避、改口和答非所问，不要让角色完整解释双方已知信息。

输出纯Markdown正文，不要包含JSON。"""


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

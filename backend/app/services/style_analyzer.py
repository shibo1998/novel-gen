"""风格分析服务 —— Phase 9 增强版（中文去味 + 毛刺注入）"""
import logging
import random
import time
from typing import Dict, List

from app.llm.client import collect_stream_text, get_llm_client
from app.services.llm_observability import LLMCallObserver

logger = logging.getLogger(__name__)


class StyleProfile:
    """风格配置"""

    def __init__(self, adjectives: List[str], forbidden_words: List[str], sentence_patterns: Dict):
        self.adjectives = adjectives
        self.forbidden_words = forbidden_words
        self.sentence_patterns = sentence_patterns

    def to_dict(self) -> dict:
        return {
            "adjectives": self.adjectives,
            "forbidden_words": self.forbidden_words,
            "sentence_patterns": self.sentence_patterns,
        }


# Phase 9 毛刺策略（打碎 AI 过于平滑的叙事）
ROUGHNESS_STRATEGIES = [
    "段落戛然而止：某段在中间截断，不给读者完整的句尾",
    "不完整的比喻：写一个比喻但故意只写一半",
    "突然的超短句：在一段长句中间插入一个 1-3 字组成的短句",
    "纯感官无解释：描写一个感官细节但不给情感解读",
    "突兀过渡：不做任何过渡，直接跳到下一个场景",
    "重复的视觉：同一个细节在无预期的情况下重复出现两次",
]


class StyleAnalyzer:
    """风格分析器 + Phase 9 毛刺注入"""

    ROUGHNESS_STRATEGIES = ROUGHNESS_STRATEGIES

    def __init__(self):
        self.llm = get_llm_client()
        self.default_profile = StyleProfile(
            adjectives=["简洁", "有力", "生动"],
            forbidden_words=["非常", "十分", "极其"],
            sentence_patterns={
                "max_paragraph_length": 5,
                "avg_sentence_length": 25,
                "dialogue_ratio": 0.3,
            }
        )

    async def analyze_text(self, text: str) -> StyleProfile:
        """分析文本风格"""
        sentences = text.count("。") + text.count("！") + text.count("？")
        words = len(text)
        avg_sentence_len = words / max(sentences, 1)

        adjectives = []
        forbidden_words_found = []

        for word in self.default_profile.forbidden_words:
            if word in text:
                forbidden_words_found.append(word)

        return StyleProfile(
            adjectives=adjectives,
            forbidden_words=forbidden_words_found,
            sentence_patterns={
                "max_paragraph_length": 5,
                "avg_sentence_length": int(avg_sentence_len),
                "dialogue_ratio": text.count('"') / max(words, 1),
            }
        )

    def compare_profiles(self, profile1: StyleProfile, profile2: StyleProfile) -> Dict:
        """比较两个风格配置"""
        diff = {
            "drift_detected": False,
            "differences": [],
            "recommendations": [],
        }

        if set(profile1.adjectives) != set(profile2.adjectives):
            diff["drift_detected"] = True
            diff["differences"].append("形容词使用发生变化")

        if profile2.forbidden_words:
            diff["drift_detected"] = True
            diff["differences"].append(f"检测到禁用词: {profile2.forbidden_words}")
            diff["recommendations"].append("删除禁用词")

        return diff

    # ─────────────────────────────────────────
    # Phase 9 Layer 3：毛刺注入
    # ─────────────────────────────────────────
    async def inject_human_roughness(
        self,
        content: str,
        chapter_number: int,
        *,
        force: bool = False,
        project_id: str | None = None,
        context_snapshot_id: str | None = None,
    ) -> str:
        """
        随机注入 1-2 处"人工毛刺"，打破 AI 过于平滑的叙事。

        触发条件（满足任一即触发）：
        1. force=True（强制注入）
        2. 每隔 5 章自动执行一次（保持节奏感）

        Args:
            content: 章节正文
            chapter_number: 章号（用于判断是否自动触发）
            force: 是否强制注入（审校检测到 EXCESSIVELY_SMOOTH 时传 True）

        Returns:
            处理后的正文（微调 1-3 句）
        """
        if not force and chapter_number % 5 != 0:
            return content

        if len(content) < 500:
            return content  # 太短的章节不注入

        strategies = random.sample(self.ROUGHNESS_STRATEGIES, k=random.randint(1, 2))
        strategy_list = "\n".join(f"- {s}" for s in strategies)

        prompt = f"""以下是小说第 {chapter_number} 章的一部分正文。

请在 **1-2 处** 做微小的"不完美化"处理。不要改变情节，不要改变角色行为。

具体操作（只能选其中 {len(strategies)} 种）：
{strategy_list}

## 处理要求
- 每次修改只有 1-3 个句子受影响
- 读者不会明确注意到，但下意识会感到"这段更有人味"
- 不要在输出中解释你做了什么

## 正文
{content}

直接输出处理后的完整正文。"""

        await LLMCallObserver.check_budget(project_id, chapter_number)
        started = time.perf_counter()
        try:
            result = await collect_stream_text(self.llm, prompt)
            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=prompt,
                output=result,
                started=started,
                chapter_number=chapter_number,
                context_snapshot_id=context_snapshot_id,
            )
            logger.debug(
                "inject_human_roughness: chapter=%d, strategies=%s",
                chapter_number,
                [s[:20] for s in strategies],
            )
            return result.strip()
        except Exception as e:
            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=prompt,
                output=content,
                started=started,
                chapter_number=chapter_number,
                context_snapshot_id=context_snapshot_id,
                error=e,
            )
            logger.warning("inject_human_roughness failed: %s", e)
            raise


# 全局实例
style_analyzer = StyleAnalyzer()

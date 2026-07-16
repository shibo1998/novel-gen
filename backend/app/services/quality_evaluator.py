"""QualityEvaluator —— Phase 14
自动化质量评估系统。在审校之后用便宜模型打分，
只把低分章节推到 HITL（Human-In-The-Loop）。
"""
import json
import logging

from app.llm.client import collect_stream_text, get_llm_client
from app.services.pricing import estimate_cost
from app.services.quality_dimensions import QUALITY_DIMENSIONS
from app.utils.tokens import count_tokens, truncate_tokens

logger = logging.getLogger(__name__)

# 评估用的便宜模型
_EVAL_MODEL = "gpt-4o-mini"


class QualityEvaluator:
    """
    质量评估器。

    五个维度打分（1-5），加权平均得到总分。
    低于阈值或有两个以上短板 → 推送到 HITL 队列。
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.llm = get_llm_client()
        self.dimensions = QUALITY_DIMENSIONS

    async def evaluate(
        self,
        content: str,
        chapter_number: int,
    ) -> dict:
        """
        评估章节质量。

        Args:
            content: 章节正文（按 token 保留开头与结尾）
            chapter_number: 章号

        Returns:
            评估结果字典
        """
        dimension_scores: dict = {}
        details: dict = {}

        # 各维度并行评估（因为是独立调用，便宜模型延迟可接受）
        import asyncio
        tasks = []
        for dim_id, dim in self.dimensions.items():
            task = self._evaluate_dimension(content, dim_id, dim)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        failed_dimensions = []

        for dim_id, result in zip(self.dimensions.keys(), results):
            if isinstance(result, Exception):
                logger.warning("QualityEvaluator dimension %s failed: %s", dim_id, result)
                failed_dimensions.append(dim_id)
                details[dim_id] = {
                    "raw_score": None,
                    "feedback": f"评估失败: {result}",
                }
            else:
                dim_score, feedback = result
                dimension_scores[dim_id] = dim_score
                details[dim_id] = {
                    "raw_score": dim_score,
                    "weight": self.dimensions[dim_id]["weight"],
                    "weighted_score": dim_score * self.dimensions[dim_id]["weight"],
                    "feedback": feedback,
                    "label": self.dimensions[dim_id]["label"],
                }

        if failed_dimensions:
            return {
                "chapter_number": chapter_number,
                "evaluation_status": "unavailable",
                "overall_score": None,
                "max_score": 5,
                "dimension_scores": {
                    dim_id: {
                        "score": details[dim_id]["raw_score"],
                        "label": self.dimensions[dim_id]["label"],
                    }
                    for dim_id in self.dimensions
                },
                "weak_spots": [],
                "failed_dimensions": failed_dimensions,
                "needs_human_review": True,
                "verdict": "质量评估不可用，需人工审查",
            }

        # 加权总分
        total_weight = sum(d["weight"] for d in self.dimensions.values())
        overall = sum(
            dimension_scores[k] * self.dimensions[k]["weight"]
            for k in dimension_scores
        ) / total_weight

        # 短板检测
        weak_spots = [
            {
                "dimension": dim_id,
                "score": details[dim_id]["raw_score"],
                "label": self.dimensions[dim_id]["label"],
            }
            for dim_id, score in dimension_scores.items()
            if score <= 2
        ]

        needs_human_review = overall < 3.0 or len(weak_spots) >= 2

        result = {
            "chapter_number": chapter_number,
            "evaluation_status": "completed",
            "overall_score": round(overall, 1),
            "max_score": 5,
            "dimension_scores": {
                dim_id: {
                    "score": details[dim_id]["raw_score"],
                    "label": self.dimensions[dim_id]["label"],
                }
                for dim_id in dimension_scores
            },
            "weak_spots": weak_spots,
            "needs_human_review": needs_human_review,
            "verdict": self._verdict(overall, needs_human_review),
        }

        logger.info(
            "QualityEvaluator.evaluate: ch%d overall=%.1f weak=%d needs_review=%s",
            chapter_number, overall, len(weak_spots), needs_human_review,
        )
        return result

    async def _evaluate_dimension(
        self,
        content: str,
        dim_id: str,
        dim: dict,
    ) -> tuple[int, str]:
        """评估单个维度"""
        text = self._evaluation_excerpt(content, dim_id)
        prompt = f"""{dim['prompt']}

## 章节正文
{text}

只输出 JSON：{{"score": 1到5的整数, "feedback": "简短理由"}}。"""

        try:
            response = await collect_stream_text(self.llm, prompt)
            return self._parse_structured_result(response)
        except Exception as e:
            logger.warning("Dimension %s LLM call failed: %s", dim_id, e)
            raise

    @staticmethod
    def _parse_structured_result(text: str) -> tuple[int, str]:
        raw = text.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        result = json.loads(raw.strip())
        score = result.get("score")
        feedback = result.get("feedback")
        if not isinstance(score, int) or not 1 <= score <= 5 or not isinstance(feedback, str):
            raise ValueError("Quality result must contain score 1-5 and string feedback")
        return score, feedback.strip()

    @staticmethod
    def _evaluation_excerpt(content: str, dim_id: str) -> str:
        if count_tokens(content, _EVAL_MODEL) <= 6000:
            return content
        if dim_id == "hook_strength":
            return truncate_tokens(content, 3000, _EVAL_MODEL, keep_end=True)
        beginning = truncate_tokens(content, 3000, _EVAL_MODEL)
        ending = truncate_tokens(content, 3000, _EVAL_MODEL, keep_end=True)
        return f"{beginning}\n\n[中段因上下文预算省略]\n\n{ending}"

    def _verdict(self, overall: float, needs_review: bool) -> str:
        if overall >= 4.0:
            return "✅ 高质量，无需人工审查"
        elif overall >= 3.0:
            if needs_review:
                return "⚠️ 合格但有短板，建议人工浏览"
            return "✅ 合格，无需人工审查"
        elif needs_review:
            return "🔴 需人工审查并可能触发重写"
        return "⚠️ 有短板，但整体可接受"

    def estimate_llm_cost(self, chapter_content: str) -> float:
        """估算一次评估的 LLM 成本（用于记录 metrics）"""
        # 评估用 gpt-4o-mini，每个维度 ~500 prompt tokens + ~50 completion tokens
        # 5 个维度并行 = 5 次调用
        num_dimensions = len(self.dimensions)
        prompt_tokens = num_dimensions * 500 + count_tokens(chapter_content, _EVAL_MODEL)
        completion_tokens = num_dimensions * 50
        return estimate_cost(_EVAL_MODEL, prompt_tokens, completion_tokens)

"""LLM 模型定价表 —— Phase 12"""
from typing import Dict

# 每 1M tokens 的美元价格
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o":             {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":        {"input": 0.15, "output": 0.60},
    "gpt-4o-2024-08-06":  {"input": 2.50, "output": 10.00},
    "claude-3.5-sonnet":  {"input": 3.00, "output": 15.00},
    "claude-3.5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "deepseek-v3":         {"input": 0.27, "output": 1.10},
    "deepseek-chat":      {"input": 0.27, "output": 1.10},
    "glm-4":              {"input": 0.10, "output": 0.10},
    "glm-5":              {"input": 0.10, "output": 0.10},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    根据模型和 token 数量估算调用成本（美元）。
    """
    pricing = MODEL_PRICING.get(model.lower(), MODEL_PRICING.get("gpt-4o-mini"))
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)

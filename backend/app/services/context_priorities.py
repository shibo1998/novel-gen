"""上下文优先级配置 —— Phase 10"""
from typing import Any, Dict

CONTEXT_PRIORITIES: Dict[str, Dict[str, Any]] = {
    "constraint_card": {
        "priority": "critical",
        "description": "当前场景的约束卡",
        "quota": "full",
    },
    "current_event_chain": {
        "priority": "critical",
        "description": "当前事件链",
        "quota": "full",
    },
    "active_character_bible": {
        "priority": "critical",
        "description": "当前场景出场角色的 Bible 条目",
        "quota": "full",
        "max_entries": 5,
    },
    "recent_events": {
        "priority": "high",
        "description": "最近 5 个事件的全量详情",
        "quota": 5000,
        "overflow_action": "summarize",
    },
    "active_foreshadowings": {
        "priority": "high",
        "description": "尚未回收的伏笔",
        "quota": 3000,
        "max_entries": 10,
        "overflow_action": "truncate_oldest",
    },
    "chapter_summaries": {
        "priority": "medium",
        "description": "历史章节摘要",
        "quota": 4000,
        "strategy": "rolling_window",
    },
    "world_rules": {
        "priority": "medium",
        "description": "世界观规则",
        "quota": 2000,
        "strategy": "relevance_ranked",
    },
    "historical_events": {
        "priority": "low",
        "description": "更早期的事件",
        "quota": 0,
        "strategy": "retrieval_only",
    },
}

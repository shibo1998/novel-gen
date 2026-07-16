"""Golden test cases —— Phase 15
5 个黄金场景，每个场景包含 event 定义 + 期望的输出模式。
每次修改 Prompt 后跑这些用例，确保没有把什么搞坏。
"""

GOLDEN_TEST_CASES = [
    {
        "name": "战斗场景-1v1决胜",
        "event": {
            "trigger": "玄明拔剑，剑尖指向林远咽喉",
            "actor": "林远",
            "internal_state": "愤怒但冷静（知道不能硬拼）",
            "action": "侧身避开剑锋，同时左手暗运灵力",
            "result": "躲过致命一击，但肩头被剑气划伤",
            "consequence": "确认玄明已入魔道，下定决心回击",
            "pov": "林远",
            "tone": "紧张、暴烈",
            "estimated_words": 800,
        },
        "expected_patterns": {
            "must_not_contain": ["只见", "眼中闪过", "心头一", "缓缓", "一股", "不是.*而是"],
            "structural_checks": {
                "em_dash_count": "<=1",
            }
        }
    },
    {
        "name": "对话场景-双人试探",
        "event": {
            "trigger": "苏清霜深夜来访，递给他一枚玉简",
            "actor": "林远",
            "internal_state": "警惕但好奇",
            "action": "接过玉简，没有立刻查看",
            "result": "苏清霜说出玉简中封存的秘密",
            "consequence": "林远开始怀疑师父",
            "pov": "林远",
            "tone": "压抑、悬疑",
            "estimated_words": 1000,
        },
        "expected_patterns": {
            "must_not_contain": ["淡淡道", "冷冷道", "沉声道", "不是.*而是"],
            "structural_checks": {
                "dialogue_ratio": ">0.20",
            }
        }
    },
    {
        "name": "心理场景-独白反思",
        "event": {
            "trigger": "独自坐在密室中，回想白天师父的那个眼神",
            "actor": "林远",
            "internal_state": "困惑、动摇",
            "action": "翻看从密室中找到的旧卷宗",
            "result": "发现师父名字出现在一份禁术名单上",
            "consequence": "对师父的信任开始瓦解",
            "pov": "林远",
            "tone": "内省、压抑",
            "estimated_words": 700,
        },
        "expected_patterns": {
            "must_not_contain": ["心头一", "一股.*涌上", "眼中闪过"],
            "structural_checks": {}
        }
    },
    {
        "name": "转场场景-时间跳跃",
        "event": {
            "trigger": "三个月后，宗门大比即将开始",
            "actor": "林远",
            "internal_state": "平静中带决意（三个月苦修后的沉淀）",
            "action": "站在演武场边缘，看着新入门的弟子",
            "result": "感慨自己的变化",
            "consequence": "大比序幕拉开",
            "pov": "林远",
            "tone": "平静、略带沧桑",
            "estimated_words": 500,
        },
        "expected_patterns": {
            "must_not_contain": ["缓缓", "徐徐", "渐渐", "只见"],
            "structural_checks": {}
        }
    },
    {
        "name": "高潮场景-情绪爆发",
        "event": {
            "trigger": "玄明当众揭穿林远的杂灵根秘密",
            "actor": "林远",
            "internal_state": "羞辱→愤怒→转化为冰冷的决心",
            "action": "当着全宗弟子的面，释放出隐藏的灵力",
            "result": "全场震惊——杂灵根竟然爆发出如此力量",
            "consequence": "从被嘲讽者变成被畏惧者",
            "pov": "林远",
            "tone": "爆发、震撼",
            "estimated_words": 900,
        },
        "expected_patterns": {
            "must_not_contain": ["不是.*而是", "与其说.*不如说"],
            "structural_checks": {
                "em_dash_count": "<=1",
            }
        }
    },
]

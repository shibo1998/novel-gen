"""
角色卡扩展 Schema —— Phase 9 配套
新增 SpeechProfile（说话指纹）和角色专属动作节拍库
"""
from typing import Optional

from pydantic import BaseModel, Field


class SpeechProfile(BaseModel):
    """角色说话指纹——用于让 AI 写出每个角色独特的说话方式"""
    avg_sentence_length: int = Field(default=12, description="平均句长（字）")
    question_frequency: str = Field(default="medium", description="low / medium / high")
    rhetorical_questions: bool = Field(default=False, description="是否爱用反问")
    trailing_thoughts: bool = Field(default=False, description="是否习惯留半句")
    signature_patterns: list[str] = Field(
        default_factory=list,
        description="特征句式列表，如 ['愤怒时不说话', '妥协时说\"行吧\"但实际不退让']"
    )


class ActionBeat(BaseModel):
    """动作节拍——替代对话标签的具体动作描写"""
    description: str  # 如"右手拇指无意识地摩挲左手那道旧伤"
    trigger_context: Optional[str] = Field(
        default=None,
        description="在什么情绪/场景下使用此节拍"
    )


class CharacterProfile(BaseModel):
    """角色卡扩展——Phase 9 核心字段"""
    action_beats: list[str] = Field(
        default_factory=list,
        description="专属动作节拍库（5-10 个），用于对话时替代\"XX道\"标签"
    )
    speech_profile: SpeechProfile = Field(
        default_factory=SpeechProfile,
        description="说话指纹"
    )


# ─────────────────────────────────────────
# 预设角色配置示例（可直接复制到角色卡 data 字段）
# ─────────────────────────────────────────

PRESET_LINYU: dict = {
    "action_beats": [
        "右手拇指无意识地摩挲左手那道旧伤",
        "沉默了片刻，倒了杯茶推到对方面前",
        "走到窗边，背对着说话",
        "嘴角动了动，最终什么都没说",
        "手指在桌面上轻敲了两下，停了",
        "把玩着手中的物件，不抬头",
        "忽然笑了一下，很快又收敛了",
    ],
    "speech_profile": {
        "avg_sentence_length": 12,
        "question_frequency": "low",
        "rhetorical_questions": False,
        "trailing_thoughts": True,
        "signature_patterns": [
            "用'行吧'表示妥协，但实际并未让步",
            "愤怒时不说话，沉默的时间越长怒火越大",
            "很少直接拒绝，而是说'再说吧'"
        ]
    }
}

PRESET_SUQINGSHUANG: dict = {
    "action_beats": [
        "整理了一下并不凌乱的衣袖",
        "挑了挑眉，没有接话",
        "拔出剑来，用指尖轻轻擦拭剑刃",
        "看了对方一眼，然后把视线移开",
        "走到三步之外才开口——保持着恰好能随时拔剑的距离",
        "嘴角微微一动，说不上是笑还是嘲讽",
        "把玩着茶杯，不喝，只看着杯中的倒影",
    ],
    "speech_profile": {
        "avg_sentence_length": 8,
        "question_frequency": "high",
        "rhetorical_questions": True,
        "trailing_thoughts": False,
        "signature_patterns": [
            "用反问回答反问",
            "表达关心用攻击句式（'你死了我会很麻烦' = '我担心你'）",
            "从不说'谢谢'，用具体行动表达（递一杯茶/多留一炷香的时间）"
        ]
    }
}

PRESET_XUANMING: dict = {
    "action_beats": [
        "把玩着腰间的玉佩，笑眯眯的",
        "凑近了一步，声音压低，像在分享秘密",
        "后退半步，摊开双手表示无辜",
        "歪着头看着对方，像在看一个有趣的问题",
        "手指在剑柄上轻轻弹了一下",
        "笑容在脸上停留了一瞬，然后像面具一样摘掉",
        "吹了声口哨，不紧不慢地跟上",
    ],
    "speech_profile": {
        "avg_sentence_length": 18,
        "question_frequency": "medium",
        "rhetorical_questions": False,
        "trailing_thoughts": True,
        "signature_patterns": [
            "每句话都像在提供帮助，但其实每个帮助都有代价",
            "关键信息故意说一半，剩下一半等对方来问",
            "用'当然，如果你愿意的话'作为事实上的威胁"
        ]
    }
}

ALL_PRESETS = {
    "林远": PRESET_LINYU,
    "苏清霜": PRESET_SUQINGSHUANG,
    "玄明": PRESET_XUANMING,
}

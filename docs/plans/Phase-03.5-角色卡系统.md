# Phase 3.5：角色卡系统（Character Card System）

## 交付物

```
backend/app/agents/character.py
backend/app/memory/character_memory.py
backend/app/prompts/character_dialogue.j2
backend/app/prompts/character_extend.j2
backend/app/api/characters.py
frontend/src/pages/CharacterStudio/CharacterCard.tsx
frontend/src/pages/CharacterStudio/CharacterList.tsx
frontend/src/pages/CharacterStudio/CharacterMemory.tsx
frontend/src/pages/CharacterStudio/CharacterSimulator.tsx
frontend/src/stores/characterStore.ts
frontend/src/api/characters.ts
```

## 核心设计思想

**问题**：传统写作Agent写对话时，所有角色说话都像同一个AI——因为LLM没有"这个人是谁"的持久记忆。

**解法**：每个主要角色是一个独立的Agent，有自己的：
- **心理档案**（人格特质、欲望、恐惧、秘密）
- **记忆库**（记得什么事件、对谁有什么印象）
- **语言风格模型**（用词偏好、句式长度、口头禅）
- **决策逻辑**（在给定情境下会做什么选择）

## 数据结构设计

### 1. 角色卡Schema（PostgreSQL `entities.data` JSONB扩展）

```json
{
  "aliases": ["林远", "远哥", "林师弟"],

  "appearance": {
    "age_range": "19-22",
    "hair": "黑发束髻",
    "eyes": "琥珀色",
    "build": "清瘦",
    "notable": "左手指节有旧伤痕"
  },

  "psychology": {
    "big_five": {
      "openness": 0.7,
      "conscientiousness": 0.6,
      "extraversion": 0.3,
      "agreeableness": 0.5,
      "neuroticism": 0.6
    },
    "core_desire": "证明杂灵根也能成大道",
    "core_fear": "被当作废物抛弃",
    "secret": "其实知道师父隐藏了关键信息，但不敢问",
    "moral_compass": "结果正义 > 程序正义",
    "coping_mechanism": "压抑情绪，用理性包装愤怒"
  },

  "speech_style": {
    "sentence_length": "short",
    "vocabulary_level": "medium",
    "tone_default": "calm",
    "quirks": [
      "愤怒时反而更安静",
      "不喜客套，能一个字说完绝不说两个字",
      "思考时会用右手拇指摩挲左手伤痕"
    ],
    "forbidden_words": ["拜托", "求你", "也许吧"],
    "signature_phrases": ["无妨", "走吧"]
  },

  "relationships": {
    "苏清霜": {
      "type": "敬重但有距离感",
      "history": "大师姐曾救过他一命",
      "current_status": "同盟萌芽期",
      "unresolved": "不知道她是否知道师父的秘密"
    }
  },

  "episodic_memory": [
    {
      "event_id": "scene_3_2",
      "summary": "与苏清霜首次单独对话，她提到师父的行踪可疑",
      "emotional_impact": "震惊 + 警惕",
      "learned_about_others": {"苏清霜": "她可能知道更多"},
      "chapter": 3,
      "scene": 2
    }
  ],

  "arc_stage": {
    "current": "从'证明给别人看'转向'为自己而活'",
    "milestone_reached": ["发现杂灵根的特殊性", "第一次违抗师命"],
    "next_trigger": "目睹同门因循规蹈矩而死"
  }
}
```

### 2. 角色记忆表（PostgreSQL新增表）

```sql
CREATE TABLE character_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID REFERENCES entities(id) ON DELETE CASCADE NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,

    -- 记忆内容
    event_summary TEXT NOT NULL,
    emotional_impact TEXT,
    learned_facts JSONB DEFAULT '[]',

    -- 元数据
    chapter_number INT NOT NULL,
    scene_number INT NOT NULL,
    scene_id UUID REFERENCES scenes(id),

    -- 记忆衰减
    decay_factor FLOAT DEFAULT 1.0,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memories_character ON character_memories(character_id);
CREATE INDEX idx_memories_project_chapter ON character_memories(project_id, chapter_number);
```

## 角色模拟Agent实现

### `backend/app/agents/character.py`

```python
from app.agents.base import BaseAgent

class CharacterAgent(BaseAgent):
    """
    角色模拟Agent：给定情境，返回符合角色人设的回应

    三种模式：
    1. dialogue: 给定上文对话，返回该角色的下一句话
    2. decision: 给定情境，返回该角色会做什么选择
    3. internal_monologue: 返回该角色的内心独白
    """

    @property
    def template_name(self) -> str:
        return "character_dialogue.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "response": {"type": "string"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["response", "confidence", "reasoning"]
        }

    async def simulate_dialogue(self, character_id: str, context: dict) -> dict:
        character = await self._load_character(character_id)
        relevant_memories = await self._retrieve_memories(
            character_id,
            query=context["scene_summary"],
            limit=3
        )

        inputs = {
            "character": character,
            "memories": relevant_memories,
            "context": context,
            "mode": "dialogue"
        }

        return await self.run(inputs)

    async def _load_character(self, character_id: str) -> dict:
        """从PostgreSQL加载角色卡"""
        pass

    async def _retrieve_memories(self, character_id: str, query: str, limit: int) -> list:
        """从character_memories表检索相关记忆"""
        pass
```

### `backend/app/prompts/character_dialogue.j2`

```jinja2
你正在模拟一个小说角色的言行。请严格按照角色设定，给出他在当前情境下的回应。

## 角色档案
姓名：{{ character.display_name }}

### 核心人格
- 核心欲望：{{ character.psychology.core_desire }}
- 核心恐惧：{{ character.psychology.core_fear }}
- 道德指南：{{ character.psychology.moral_compass }}
- 应对机制：{{ character.psychology.coping_mechanism }}

### 语言风格
- 句式长度：{{ character.speech_style.sentence_length }}
- 词汇水平：{{ character.speech_style.vocabulary_level }}
- 默认语气：{{ character.speech_style.tone_default }}
- 特征习惯：
{% for q in character.speech_style.quirks %}
  - {{ q }}
{% endfor %}
- 禁用词汇：{{ character.speech_style.forbidden_words | join("、") }}
- 标志性用语：{{ character.speech_style.signature_phrases | join("、") }}

### 当前关系状态
{% for other, rel in character.relationships.items() %}
- 对{{ other }}：{{ rel.type }}（{{ rel.current_status }}）
  未决事项：{{ rel.unresolved }}
{% endfor %}

### 相关记忆（最近经历）
{% for mem in memories %}
【第{{ mem.chapter }}章 第{{ mem.scene }}场景】
{{ mem.event_summary }}
情绪影响：{{ mem.emotional_impact }}
---
{% endfor %}

## 当前情境
{{ context.scene_summary }}

前情对话：
{{ context.previous_speaker }}说："{{ context.previous_line }}"

## 任务
模拟{{ character.display_name }}在此情境下会如何回应。

**要求**：
1. 严格符合角色的语言风格
2. 体现角色的核心欲望和恐惧
3. 考虑他对其他角色的态度和未决事项
4. 如果有相关记忆，要体现记忆的影响

输出JSON：
{
  "response": "角色的具体回应（对话/动作/表情）",
  "confidence": 0.85,
  "reasoning": "为什么这样回应"
}
```

## 写作Agent集成角色卡

```python
# backend/app/agents/writer.py (修订版)

class WriterAgent(BaseAgent):
    async def write_scene(self, constraint: SceneConstraint) -> str:
        """
        新流程：约束卡 → 遇到对话时调用CharacterAgent → 整合成正文
        """

        # 第一步：生成场景骨架（不含具体对话）
        skeleton = await self._generate_skeleton(constraint)

        # 第二步：识别需要对话的位置
        dialogue_slots = self._extract_dialogue_slots(skeleton)

        # 第三步：逐个调用CharacterAgent填充对话
        filled_dialogues = []
        for slot in dialogue_slots:
            character_agent = CharacterAgent()
            response = await character_agent.simulate_dialogue(
                character_id=slot["pov_character_id"],
                context={
                    "scene_summary": constraint.narrative_goal,
                    "previous_speaker": slot["previous_speaker"],
                    "previous_line": slot["previous_line"],
                    "other_characters_present": constraint.characters_present,
                    "relationship_context": self._build_relationship_context(slot)
                }
            )
            filled_dialogues.append(response["response"])

        # 第四步：将对话填回骨架，生成完整正文
        final_content = self._merge_dialogues(skeleton, filled_dialogues)

        return final_content
```

## API端点

| 方法   | 路径 | 说明 |
| ------ |------|------|
| `POST` | `/api/projects/{id}/characters` | 创建角色卡（输入基础设定→AI扩展） |
| `GET` | `/api/projects/{id}/characters` | 获取所有角色卡列表 |
| `GET` | `/api/characters/{id}` | 获取角色卡详情（含记忆） |
| `POST` | `/api/characters/{id}/simulate` | 手动测试角色模拟 |
| `PUT` | `/api/characters/{id}/memory` | 批量更新角色记忆 |

## 前端页面：角色工坊

```
┌─────────────────────────────────────────────────────────────┐
│  角色列表（左侧栏）                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  [+新建]          │
│  │ 林远     │ │ 苏清霜   │ │ 玄尘子   │                     │
│  └──────────┘ └──────────┘ └──────────┘                     │
├─────────────────────────────────────────────────────────────┤
│  角色详情（主区域）                                           │
│                                                              │
│  [基础设定] [心理档案] [语言风格] [关系网] [记忆库]          │
│  ────────────────────────────────────────────────────────   │
│  （Tab内容略，见完整设计文档）                                │
└─────────────────────────────────────────────────────────────┘
```

## 验证清单

```
☐ 创建角色卡 → AI自动扩展为完整心理档案
☐ 角色模拟API返回符合人设的对话/决策
☐ 写作Agent集成角色卡后，对话质量显著提升
☐ 每章完成后，出场角色的记忆库自动更新
☐ 审校Agent能检测"这个角色不会说这种话"的一致性错误
☐ 前端角色工坊可编辑、可测试、可可视化关系网
```

## 依赖关系

- **前置**：Phase 3（写作Agent作为集成目标）
- **后续**：Phase 4（Memory层完整实现）、Phase 5（审校Agent调用角色卡检测）

## 实施重点

| 重点 | 说明 |
|------|------|
| Big Five心理模型 | 用雷达图可视化，人工调整 |
| 语言风格标签 | 量化标签比自由文本更稳定 |
| 记忆衰减机制 | `decay_factor` 字段实现"久远记忆变模糊" |
| 写作集成 | Phase 3.5先独立跑通角色模拟API |

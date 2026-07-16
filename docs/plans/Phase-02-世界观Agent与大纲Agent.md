# Phase 2：世界观Agent + 大纲Agent

## 交付物

```
backend/app/agents/base.py
backend/app/agents/worldbuilding.py
backend/app/agents/outline.py
backend/app/prompts/worldbuilding.j2
backend/app/prompts/outline.j2
backend/app/api/worldbuilding.py
backend/app/api/outline.py
backend/app/pipeline/task_queue.py
```

## 关键设计

### Agent 输入输出规范

**世界观Agent**：

- 输入：`{core_idea, genre, tone_style}`
- 输出：`{setting_document, constraints:{hard:[], soft:[]}, conflict_seeds:[]}`

**大纲Agent**：

- 输入：`{core_idea, tone_style, setting_document, constraints}`
- 输出：`{volumes:[{number, core_conflict, character_arc_stage}], chapters:[{volume, number, title, goal, key_events:[], pov_character, foreshadowing_seeds:[]}], foreshadowing_registry:[{name, sow_chapter, reap_chapter}]}`

### `backend/app/agents/base.py`

```python
import json
from abc import ABC, abstractmethod
from jinja2 import Environment, FileSystemLoader
from app.llm.client import get_llm_client

class BaseAgent(ABC):
    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    @property
    @abstractmethod
    def template_name(self) -> str:
        pass

    @abstractmethod
    def output_schema(self) -> dict:
        """JSON Schema 用于 structured output"""
        pass

    async def run(self, inputs: dict) -> dict:
        template = self.jinja.get_template(self.template_name)
        prompt = template.render(**inputs)
        system = self._system_prompt()

        raw = await self.llm.complete(prompt, system=system, json_schema=self.output_schema())
        result = json.loads(raw)
        return self._validate(result)

    def _system_prompt(self) -> str:
        return "你是一位专业的小说策划助手，输出必须是合法JSON。"

    def _validate(self, data: dict) -> dict:
        # 根据 output_schema 做基本校验
        return data
```

### `backend/app/prompts/worldbuilding.j2`

```jinja2
你是一位资深小说世界观架构师。请根据以下核心创意，构建完整的世界观设定。

## 核心创意
{{ core_idea }}

## 类型
{{ genre }}

## 风格方向
{{ tone_style }}

## 输出要求
请输出严格的JSON，包含以下字段：

1. **setting_document**：完整的世界设定文档（Markdown格式），必须覆盖：
   - 时代背景（具体年代、历史阶段、社会形态）
   - 地理环境（主要地理位置、特征、影响）
   - 势力格局（主要组织、国家、门派及其关系）
   - 力量/科技体系（规则、等级、限制）——这是硬约束的基础
   - 社会文化（价值观、风俗、禁忌）

2. **constraints**：分为两部分——
   - **hard**（列表）：不可违反的世界规则，每条用一句话表达。例如"此世界不存在复活术""修为不可逆转下降"
   - **soft**（列表）：风格指南，每条一句话。例如"对话风格冷峻""环境描写重氛围轻细节"

3. **conflict_seeds**（列表）：世界内在矛盾，每项包含——
   - **name**：矛盾名称
   - **description**：一句话描述冲突本质
   - **stake**：一句话描述利害关系

## 重要原则
- 设定必须自洽，不要有内部矛盾
- Hard constraints 是可被程序化检查的明确规则
- Conflict seeds 要能支撑长篇叙事——每个种子至少能展开3章以上
- 不要写剧情，只写设定
```

### `backend/app/prompts/outline.j2`

```jinja2
你是一位专业小说结构师。请根据以下设定，构建完整的小说大纲。

## 核心创意
{{ core_idea }}

## 风格方向
{{ tone_style }}

## 世界观设定
{{ setting_document }}

## 世界观硬约束（不可违反）
{% for c in constraints.hard %}
- {{ c }}
{% endfor %}

## 世界观风格约束
{% for c in constraints.soft %}
- {{ c }}
{% endfor %}

## 输出要求
请输出严格的JSON：

1. **volumes**（列表）：每卷包含——
   - **number**：卷号
   - **title**：卷名
   - **core_conflict**：本卷核心冲突
   - **character_arc_stage**：主角在本卷所处的弧线阶段

2. **chapters**（列表）：每章包含——
   - **volume**：所属卷号
   - **number**：章号（全书连续编号）
   - **title**：章名
   - **goal**：本章要完成的叙事目标
   - **key_events**（列表）：本章关键事件序列，每项包含 event_name 和 brief
   - **pov_character**：建议的主视角角色
   - **foreshadowing_seeds**（列表）：本章埋下的伏笔，每项包含 name 和 brief

3. **foreshadowing_registry**（列表）：全书伏笔登记表，每项包含——
   - **name**：伏笔名称
   - **description**：简短描述
   - **sow_chapter**：播种章号
   - **reap_chapter**：预期回收章号（可以为null）

## 结构要求
- 默认三卷结构：建立→对抗→解决
- 每卷约10-15章
- 每章3-5个关键事件
- 伏笔总数建议15-25个，均匀分布
- 确保每个 conflict_seed 都有对应的章节推进
```

### Agent代码

`worldbuilding.py` 和 `outline.py` 只需继承 `BaseAgent`，设定各自的 `template_name` 和 `output_schema`。

```python
# backend/app/agents/worldbuilding.py
class WorldbuildingAgent(BaseAgent):
    @property
    def template_name(self) -> str:
        return "worldbuilding.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "setting_document": {"type": "string"},
                "constraints": {
                    "type": "object",
                    "properties": {
                        "hard": {"type": "array", "items": {"type": "string"}},
                        "soft": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "conflict_seeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "stake": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["setting_document", "constraints", "conflict_seeds"]
        }
```

### 异步任务

```python
# backend/app/pipeline/task_queue.py
from celery import Celery
from app.config import settings

celery_app = Celery("novel_gen", broker=settings.redis_url)

@celery_app.task
def run_worldbuilding(project_id: str, core_idea: str, genre: str, tone_style: str):
    """异步执行世界观生成，完成后写入DB"""
    pass

@celery_app.task
def run_outline(project_id: str):
    """异步执行大纲生成，完成后写入DB"""
    pass
```

## API端点

| 方法   | 路径                               | 说明                                     |
| ------ | ---------------------------------- | ---------------------------------------- |
| `POST` | `/api/projects/{id}/worldbuilding` | 触发世界观生成，返回 `{task_id}`         |
| `GET`  | `/api/tasks/{task_id}`             | 查询任务状态 `{status, result?, error?}` |
| `GET`  | `/api/projects/{id}/entities`      | 获取该项目所有实体                       |
| `POST` | `/api/projects/{id}/outline`       | 触发大纲生成，返回 `{task_id}`           |
| `GET`  | `/api/projects/{id}/outline`       | 获取大纲（chapters列表）                 |

## 验证清单

```
☐ POST worldbuilding → 返回task_id → Celery worker执行 → 任务完成
☐ 世界观输出JSON格式正确，字段完整
☐ entities表自动创建了角色/地点/规则记录
☐ constraints.hard 写入 entities(data.rules)
☐ POST outline → 返回task_id → 大纲生成完成
☐ foreshadowings表自动创建了伏笔记录
☐ chapters表自动创建了章节记录
☐ 大纲JSON的伏笔播种章节与foreshadowing_registry一致
```

## 依赖关系

- **前置**：Phase 1（依赖LLM适配层和数据库）
- **后续**：Phase 3（细纲Agent需要世界观和大纲作为输入）

## 关键文件模板

### `backend/app/agents/outline.py`

```python
# backend/app/agents/outline.py
class OutlineAgent(BaseAgent):
    @property
    def template_name(self) -> str:
        return "outline.j2"

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "volumes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "number": {"type": "integer"},
                            "title": {"type": "string"},
                            "core_conflict": {"type": "string"},
                            "character_arc_stage": {"type": "string"}
                        }
                    }
                },
                "chapters": {"type": "array"},
                "foreshadowing_registry": {"type": "array"}
            },
            "required": ["volumes", "chapters", "foreshadowing_registry"]
        }
```

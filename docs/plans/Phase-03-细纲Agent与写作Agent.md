# Phase 3：细纲Agent + 写作Agent + SSE流式

> **本 Phase 包含**：SSE断点续传、审校防死循环、Redis检查点

## 交付物

```
backend/app/agents/chapter.py
backend/app/agents/writer.py
backend/app/agents/reviewer.py        # [新增] 审校Agent基础
backend/app/prompts/chapter.j2
backend/app/prompts/writer.j2
backend/app/prompts/reviewer.j2      # [新增]
backend/app/models/constraints.py
backend/app/api/chapter.py
backend/app/api/writing.py           # [修改] SSE流式端点
backend/app/services/checkpoint_store.py  # [新增] Redis检查点
backend/app/pipeline/coordinator.py  # [修改] 审校防死循环
```

## 关键设计

### 约束卡数据模型 `backend/app/models/constraints.py`

约束卡是本系统的核心创新，解决了AI写作最大的痛点：**上下文漂移**。写作Agent拿到约束卡后不需要自行判断，严格按约束执行。

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SceneConstraint(BaseModel):
    chapter_number: int
    scene_number: int
    scene_title: str
    narrative_goal: str
    scene_function: str

    pov_character: str
    characters_present: List[str]
    character_emotional_states: dict[str, str]

    opening_emotion: str
    closing_emotion: str
    emotional_beats: List[str]

    reader_should_know: List[str]
    reader_should_not_know: List[str]

    prose_directives: List[str]
    forbidden_elements: List[str]
    word_budget: int

    # 由ContextBuilder填充（Phase 4 接入）
    injected_bible: Optional[dict] = None
    injected_previous: Optional[List[dict]] = None
    injected_foreshadowings: Optional[List[dict]] = None

    def model_copy(self, **updates):
        """支持深拷贝并更新字段"""
        import copy
        data = self.model_dump()
        data.update(updates)
        return SceneConstraint(**data)
```

### `backend/app/prompts/chapter.j2`

```jinja2
你是一位专业小说场景规划师。请根据章节大纲，将其展开为详细的场景序列和约束卡。

## 本章大纲
章号：{{ chapter.number }}
标题：{{ chapter.title }}
叙事目标：{{ chapter.goal }}
关键事件：{{ chapter.key_events | tojson }}
建议POV：{{ chapter.pov_character }}

## 全书世界观约束
{% for c in hard_constraints %}
- 【硬约束】{{ c }}
{% endfor %}
{% for c in soft_constraints %}
- 【风格】{{ c }}
{% endfor %}

## 出场角色档案
{% for char in characters %}
### {{ char.name }}
- 性格特征：{{ char.personality_traits }}
- 语言风格：{{ char.speech_style }}
- 小动作：{{ char.quirks }}
{% endfor %}

## 输出要求
将本章展开为3-5个场景，每个场景输出一张约束卡（JSON数组）：

每个场景包含：
- chapter_number, scene_number, scene_title
- narrative_goal：本场景要完成的叙事任务
- scene_function：场景功能（建立/推进/转折/收束）
- pov_character, characters_present
- character_emotional_states：每个出场角色的开场情绪
- opening_emotion, closing_emotion, emotional_beats（列表）
- reader_should_know, reader_should_not_know（列表）
- prose_directives（列表）：具体写作指令，如"短句为主""禁止内心独白""对话占比50%+"
- forbidden_elements（列表）：本场景禁止出现的元素
- word_budget：字数预算（800-2000，根据场景功能调整）

## 重要原则
- 每张约束卡要足够具体，写作Agent拿到后不需要自行判断即可执行
- prose_directives 越细越好——"用短句"不如"每句不超过30字，段落不超过4句"
- word_budget 要合理——过渡场景800字够，高潮场景可以2000
```

### `backend/app/prompts/writer.j2`

```jinja2
你是一位专业小说作家。你将收到一张场景约束卡，严格按照约束写出场景正文。不要自由发挥，不要偏离约束。

## 约束卡
```json
{{ constraint_card | tojson(indent=2) }}
```

{% if injected_bible %}
## 角色档案（按需参考）
```json
{{ injected_bible | tojson(indent=2) }}
```
{% endif %}

{% if injected_previous %}
## 前情概要
{% for s in injected_previous %}
### 第{{ s.chapter }}章 第{{ s.scene }}场景
{{ s.summary }}
{% endfor %}
{% endif %}

{% if injected_foreshadowings %}
## 活跃伏笔（请注意这些尚未回收的伏笔）
{% for f in injected_foreshadowings %}
- 【{{ f.name }}】{{ f.description }} → 预计回收：第{{ f.reap_chapter }}章
{% endfor %}
{% endif %}

{% if revision_notes %}
## 审校反馈（请务必修复以下问题）
{% for note in revision_notes %}
### 第{{ loop.index }}次重写的问题
{% for issue in note.critical_issues %}
- {{ issue.category.upper() }}: {{ issue.description }}
  {% if issue.suggestion %}建议：{{ issue.suggestion }}{% endif %}
{% endfor %}
{% endfor %}
{% endif %}

## 写作指令
1. **严格遵守** prose_directives 中的每一条
2. **绝不出现** forbidden_elements 中的任何元素
3. 读者在本场景后应该知道：{{ constraint_card.reader_should_know | join("、") }}
4. 读者在本场景后**不能**知道：{{ constraint_card.reader_should_not_know | join("、") }}
5. 目标字数：{{ constraint_card.word_budget }}字

## 输出格式
直接输出场景正文（纯Markdown），不要输出JSON。标题格式：### 第X章 第Y场景：{scene_title}

现在开始写。
```

### `backend/app/prompts/reviewer.j2` [新增]

```jinja2
你是一位专业的小说审校员。请仔细检查场景正文，确保其符合所有约束要求。

## 待审校场景
章号：{{ chapter_number }}，场景号：{{ scene_number }}

## 正文
{{ content }}

## 约束卡（原写作要求）
```json
{{ constraint_card | tojson(indent=2) }}
```

## Story Bible（角色事实）
{% if bible %}
```json
{{ bible | tojson(indent=2) }}
```
{% endif %}

## 已建立的事实（前文相关段落）
{% if previous_summaries %}
{% for s in previous_summaries %}
### 第{{ s.chapter }}章 第{{ s.scene }}场景
{{ s.summary }}
{% endfor %}
{% else %}
（暂无前文摘要，将在Phase 4接入）
{% endif %}

## 审校清单

### 1. 事实一致性
- 角色特征（外貌、性格、语言风格）是否一致？
- 角色能力是否在设定范围内？

### 2. 情节连续性
- 角色是否知道不该知道的事？
- 时间线是否连贯？

### 3. 约束合规
- hard constraints 是否违反？
- prose_directives 是否遵守？
- forbidden_elements 是否出现？

## 输出要求

```json
{
  "issues": [
    {
      "severity": "critical|major|minor|style",
      "category": "factual|continuity|constraint|style",
      "description": "问题描述",
      "suggestion": "修改建议",
      "evidence": "原文引用（精确到句子）"
    }
  ],
  "passed": true或false,
  "summary": "一句话总结"
}
```

**重要**：severity=critical 必须出现才表示有问题，避免过度挑剔minor问题。
```

### 检查点存储 `backend/app/services/checkpoint_store.py` [新增]

```python
import json
import redis.asyncio as redis
from typing import Optional
from app.config import settings


class CheckpointStore:
    """场景生成检查点存储（使用Redis）"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.prefix = "scene_checkpoint:"
        self.ttl = 3600 * 24  # 24小时过期

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def _key(self, scene_id: str) -> str:
        return f"{self.prefix}{scene_id}"

    async def save(self, scene_id: str, data: dict) -> None:
        """保存检查点"""
        r = await self._get_redis()
        await r.setex(self._key(scene_id), self.ttl, json.dumps(data, ensure_ascii=False))

    async def load(self, scene_id: str) -> Optional[dict]:
        """加载检查点"""
        r = await self._get_redis()
        data = await r.get(self._key(scene_id))
        return json.loads(data) if data else None

    async def delete(self, scene_id: str) -> None:
        """删除检查点"""
        r = await self._get_redis()
        await r.delete(self._key(scene_id))


# 全局实例
checkpoint_store = CheckpointStore()
```

### SSE流式端点 `backend/app/api/writing.py` [增强]

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import logging
from app.core.security import get_current_user
from app.services.checkpoint_store import checkpoint_store
from app.agents.writer import WriterAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/scenes", tags=["写作"])


class StreamRequest(BaseModel):
    last_received_offset: int = 0
    constraint_override: dict = None


@router.post("/{scene_id}/write")
async def stream_write_scene(
    scene_id: str,
    payload: StreamRequest,
    current_user_id: str = Depends(get_current_user)
):
    """SSE流式生成场景正文，支持断点续传"""

    async def generate():
        last_offset = payload.last_received_offset
        accumulated_content = ""

        try:
            # 1. 恢复状态（如果有断点）
            if last_offset > 0:
                checkpoint = await checkpoint_store.load(scene_id)
                if checkpoint and checkpoint.get("offset") == last_offset:
                    accumulated_content = checkpoint.get("content", "")
                    yield f"data: {json.dumps({'type': 'resume', 'content': accumulated_content, 'offset': last_offset})}\n\n"

            # 2. 获取写作Agent
            agent = WriterAgent()
            constraint = await agent.build_constraint(scene_id)
            token_count = 0

            # 3. 流式生成
            async for token in agent.llm.complete_stream(
                agent._build_prompt(constraint)
            ):
                token_count += 1
                accumulated_content += token

                # 每20个token保存检查点
                if token_count % 20 == 0:
                    await checkpoint_store.save(scene_id, {
                        "content": accumulated_content,
                        "offset": last_offset + token_count,
                        "updated_at": "now"
                    })
                    yield f"data: {json.dumps({'type': 'progress', 'offset': last_offset + token_count})}\n\n"

                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # 4. 生成完成，清理检查点
            await checkpoint_store.delete(scene_id)
            yield f"data: {json.dumps({'type': 'done', 'total_tokens': last_offset + token_count})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            await checkpoint_store.save(scene_id, {
                "content": accumulated_content,
                "offset": last_offset + token_count,
                "error": str(e)
            })
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

### 审校防死循环 `backend/app/pipeline/coordinator.py` [增强]

```python
import logging
from typing import Optional
from app.models.constraints import SceneConstraint

logger = logging.getLogger(__name__)


class Coordinator:
    MAX_REVISION_ATTEMPTS = 3  # 最大重试次数

    def __init__(self):
        self.agents = {}  # 将在 Phase 2 后初始化
        self.revision_history: dict[str, list] = {}

    async def generate_scene(
        self,
        project_id: str,
        constraint: SceneConstraint
    ) -> tuple[str, dict]:
        """
        生成单个场景，支持审校反馈重试
        返回: (content, review_result)
        """
        scene_key = f"{project_id}:{constraint.chapter_number}:{constraint.scene_number}"
        self.revision_history[scene_key] = []

        attempt = 0
        content = ""
        review_result = {}

        while attempt < self.MAX_REVISION_ATTEMPTS:
            try:
                # 1. 上下文组装（Phase 4 完善）
                enriched_constraint = constraint

                # 2. 写作（带审校反馈）
                logger.info(f"Writing attempt {attempt + 1} for scene {scene_key}")
                content = await self.agents["writer"].write_scene(
                    enriched_constraint,
                    revision_notes=self.revision_history[scene_key]
                )

                # 3. 审校
                review_result = await self.agents["reviewer"].review(
                    content=content,
                    constraint=enriched_constraint
                )

                # 4. 检查严重问题
                critical_issues = [
                    i for i in review_result.get("issues", [])
                    if i["severity"] == "critical"
                ]

                if not critical_issues:
                    # 审校通过
                    logger.info(f"Scene {scene_key} passed after {attempt + 1} attempts")
                    break

                # 5. 记录失败原因，准备重试
                self.revision_history[scene_key].append({
                    "attempt": attempt + 1,
                    "critical_issues": critical_issues,
                    "partial_content": content[:500] if content else ""
                })

                attempt += 1

                if attempt >= self.MAX_REVISION_ATTEMPTS:
                    # 达到上限
                    logger.error(f"Scene {scene_key} failed after {self.MAX_REVISION_ATTEMPTS} attempts")
                    review_result["needs_human_review"] = True
                    review_result["revision_history"] = self.revision_history[scene_key]
                    break

                # 6. 注入反馈，重试
                constraint = self._inject_feedback(constraint, critical_issues, content)
                logger.warning(f"Regenerating (attempt {attempt + 1}/{self.MAX_REVISION_ATTEMPTS})")

            except Exception as e:
                logger.exception(f"Error during generation attempt {attempt + 1}")
                attempt += 1
                if attempt >= self.MAX_REVISION_ATTEMPTS:
                    raise

        # 7. 保存结果
        await self._save_result(project_id, constraint, content, review_result)
        return content, review_result

    def _inject_feedback(
        self,
        constraint: SceneConstraint,
        critical_issues: list,
        previous_content: str
    ) -> SceneConstraint:
        """将审校反馈注入约束卡，供下次重写使用"""
        feedback_parts = ["上一次生成有以下问题需要修复："]

        for i, issue in enumerate(critical_issues, 1):
            feedback_parts.append(f"{i}. {issue['category'].upper()}: {issue['description']}")
            if issue.get('suggestion'):
                feedback_parts.append(f"   建议：{issue['suggestion']}")

        feedback_parts.append(f"\n上一次内容片段：\n{previous_content[:1000]}...\n请避免上述问题。")

        new_directives = list(constraint.prose_directives) if constraint.prose_directives else []
        new_directives.append(f"【审校反馈】{' '.join(feedback_parts)}")

        new_forbidden = list(constraint.forbidden_elements) if constraint.forbidden_elements else []
        for issue in critical_issues:
            if issue.get('forbidden_pattern'):
                new_forbidden.append(issue['forbidden_pattern'])

        return constraint.model_copy(
            prose_directives=new_directives,
            forbidden_elements=new_forbidden
        )
```

### WriterAgent实现 `backend/app/agents/writer.py`

```python
import json
from jinja2 import Environment, FileSystemLoader
from app.llm.client import get_llm_client
from app.models.constraints import SceneConstraint


class WriterAgent:
    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    def _build_prompt(self, constraint: SceneConstraint, revision_notes: list = None) -> str:
        """构建写作prompt"""
        template = self.jinja.get_template("writer.j2")
        return template.render(
            constraint_card=constraint,
            injected_bible=constraint.injected_bible,
            injected_previous=constraint.injected_previous,
            injected_foreshadowings=constraint.injected_foreshadowings,
            revision_notes=revision_notes or []
        )

    async def write_scene(
        self,
        constraint: SceneConstraint,
        revision_notes: list = None
    ) -> str:
        """生成场景正文"""
        prompt = self._build_prompt(constraint, revision_notes)
        system = "你是一位专业小说作家。严格按照约束卡写作，不要自由发挥。"

        content = await self.llm.complete(prompt, system=system)
        return content

    async def write_scene_stream(self, constraint: SceneConstraint):
        """流式生成场景正文"""
        prompt = self._build_prompt(constraint)
        system = "你是一位专业小说作家。严格按照约束卡写作，不要自由发挥。"

        async for token in self.llm.complete_stream(prompt, system=system):
            yield token

    async def build_constraint(self, scene_id: str) -> SceneConstraint:
        """从数据库加载约束卡"""
        # TODO: 从数据库加载
        # 临时返回示例
        return SceneConstraint(
            chapter_number=1,
            scene_number=1,
            scene_title="林远的清晨",
            narrative_goal="建立主角的日常生活和性格特征",
            scene_function="establishing",
            pov_character="林远",
            characters_present=["林远"],
            character_emotional_states={"林远": "平静"},
            opening_emotion="平静",
            closing_emotion="若有所思",
            emotional_beats=["清晨醒来", "日常修炼", "发现异常"],
            reader_should_know=["林远是杂灵根", "他生活在一个修仙门派"],
            reader_should_not_know=["师父的秘密"],
            prose_directives=["使用第三人称", "短句为主"],
            forbidden_elements=["内心独白过多"],
            word_budget=800
        )
```

### ReviewerAgent实现 `backend/app/agents/reviewer.py` [新增]

```python
import json
from jinja2 import Environment, FileSystemLoader
from app.llm.client import get_llm_client


class ReviewerAgent:
    """审校Agent：检测场景正文的一致性问题"""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    async def review(
        self,
        content: str,
        constraint,
        bible: dict = None,
        previous_summaries: list = None
    ) -> dict:
        """审校场景，返回问题列表"""
        template = self.jinja.get_template("reviewer.j2")

        prompt = template.render(
            content=content,
            chapter_number=constraint.chapter_number,
            scene_number=constraint.scene_number,
            constraint_card=constraint,
            bible=bible or {},
            previous_summaries=previous_summaries or []
        )

        system = "你是一位专业审校员。严格检查，但不要过度挑剔minor问题。"

        raw = await self.llm.complete(prompt, system=system)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 如果LLM输出不是合法JSON，返回兜底结果
            return {
                "issues": [],
                "passed": True,
                "summary": "审校通过（解析异常，视为通过）"
            }
```

## API端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `POST` | `/api/v1/chapters/{chapter_id}/expand` | 触发生成约束卡 | 是 |
| `GET` | `/api/v1/chapters/{chapter_id}/scenes` | 获取本章所有场景 | 是 |
| `GET` | `/api/v1/scenes/{scene_id}/write` | SSE流式生成正文 | 是 |
| `POST` | `/api/v1/scenes/{scene_id}/write` | SSE流式生成（断点续传） | 是 |
| `POST` | `/api/v1/scenes/{scene_id}/save` | 保存确认后的正文 | 是 |
| `POST` | `/api/v1/scenes/{scene_id}/review` | 审校单个场景 | 是 |

## 验证清单

```
场景生成验证：
☐ 输入一章大纲 → 生成3-5张约束卡 → 写入scenes表
☐ 约束卡JSON字段完整，prose_directives具体可执行

SSE流式验证：
☐ 前端请求 /write → 逐token流式展示
☐ 断开网络 → 内容保存到Redis检查点
☐ 传入 last_received_offset → 从断点继续

审校验证：
☐ 审校通过 → issues为空，passed=true
☐ 审校失败 → 返回critical问题列表
☐ 连续失败3次 → 停止重试，标记 needs_human_review
☐ 重试时 → 反馈正确注入到prompt
```

## 依赖关系

- **前置**：Phase 2（世界观和大纲作为输入）
- **后续**：Phase 3.5（角色卡系统增强对话质量）、Phase 4（Memory层完善上下文）

## 前端SSE对接

```typescript
// frontend/src/hooks/useStreamingWrite.ts

export async function* streamScenePOST(sceneId: string, offset: number = 0) {
  const response = await fetch(`/api/v1/scenes/${sceneId}/write`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`
    },
    body: JSON.stringify({ last_received_offset: offset }),
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
}
```

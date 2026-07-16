# Phase 4：Memory层 + ContextBuilder

> **本 Phase 包含**：角色记忆衰减算法、一致性冲突检测

## 交付物

```
backend/app/memory/bible_store.py
backend/app/memory/vector_store.py
backend/app/memory/character_memory.py   # [修改] 添加衰减逻辑
backend/app/memory/plot_state.py
backend/app/services/consistency_checker.py  # [新增] 一致性检测
backend/app/pipeline/context_builder.py
```

## 核心设计

### 1. PostgreSQL - Story Bible存储

```python
# backend/app/memory/bible_store.py

class BibleStore:
    """Story Bible存储：从PostgreSQL检索角色/地点/规则等设定"""

    def __init__(self, db):
        self.db = db

    async def get_characters(self, project_id: str, names: list[str]) -> dict:
        """精确查询角色档案"""
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT name, display_name, data
                FROM entities
                WHERE project_id = $1 AND type = 'character' AND name = ANY($2)
            """),
            (project_id, names)
        )
        rows = result.fetchall()
        return {row.name: row.data for row in rows}

    async def get_locations(self, project_id: str) -> list[dict]:
        """获取所有地点设定"""
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT name, display_name, data
                FROM entities
                WHERE project_id = $1 AND type = 'location'
            """),
            (project_id,)
        )
        return [{"name": row.name, "data": row.data} for row in result.fetchall()]

    async def get_rules(self, project_id: str) -> dict:
        """获取世界规则（hard constraints）"""
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT name, data
                FROM entities
                WHERE project_id = $1 AND type = 'rule'
            """),
            (project_id,)
        )
        return {row.name: row.data for row in result.fetchall()}

    async def get_character(self, project_id: str, name: str) -> dict:
        """获取单个角色档案"""
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT data FROM entities
                WHERE project_id = $1 AND type = 'character' AND name = $2
            """),
            (project_id, name)
        )
        row = result.fetchone()
        return row.data if row else {}
```

### 2. Qdrant - 向量索引

```python
# backend/app/memory/vector_store.py

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.config import settings


class VectorStore:
    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port
        )
        self._init_collections()

    def _init_collections(self):
        """初始化集合"""
        # 注意：这是同步操作，需要在启动时调用
        sync_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        collections = sync_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if "scenes" not in collection_names:
            sync_client.create_collection(
                collection_name="scenes",
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )

    async def index_scene(self, scene_id: str, content: str, payload: dict):
        """写入已审校通过的场景"""
        # 生成embedding（需要调用embedding模型）
        vector = await self._embed(content[:8000])

        await self.client.upsert(
            collection_name="scenes",
            points=[PointStruct(
                id=scene_id,
                vector=vector,
                payload=payload  # {chapter, scene_number, pov_character, characters, summary}
            )]
        )

    async def search_similar(
        self,
        query: str,
        filters: dict = None,
        limit: int = 5
    ) -> list[dict]:
        """语义检索：查前文相关片段"""
        vector = await self._embed(query)

        search_params = {"limit": limit}
        if filters:
            search_params["filter"] = filters

        results = await self.client.search(
            collection_name="scenes",
            query_vector=vector,
            **search_params
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]

    async def _embed(self, text: str) -> list[float]:
        """生成embedding向量"""
        # TODO: 实现embedding模型调用
        # 临时返回随机向量
        import random
        return [random.random() for _ in range(1536)]
```

### 3. 角色记忆衰减 `backend/app/memory/character_memory.py` [增强]

```python
import math
from datetime import datetime
from typing import Optional
from sqlalchemy import text


class CharacterMemoryDecay:
    """
    角色记忆衰减算法

    核心思想：
    - 记忆强度 = 原始权重 × 衰减因子 ^ (距今天数)
    - 衰减因子通常取 0.9-0.99，值越大衰减越慢
    - 情绪强烈的记忆有额外加成
    """

    DEFAULT_DECAY_RATE = 0.95  # 每天保留 95%
    EMOTIONAL_BOOST = 1.5

    def __init__(self, decay_rate: float = DEFAULT_DECAY_RATE):
        self.decay_rate = decay_rate

    def calculate_strength(
        self,
        memory: dict,
        current_chapter: int,
        current_date: datetime = None
    ) -> float:
        """计算记忆在当前情境下的有效强度"""
        if current_date is None:
            current_date = datetime.utcnow()

        strength = memory.get("base_weight", 1.0)

        # 时间衰减
        memory_date = memory.get("created_at", current_date)
        if isinstance(memory_date, str):
            memory_date = datetime.fromisoformat(memory_date)

        days_elapsed = (current_date - memory_date).days
        time_decay = math.pow(self.decay_rate, days_elapsed)
        strength *= time_decay

        # 情绪加成
        emotional_impact = memory.get("emotional_impact", "neutral")
        if emotional_impact not in ("neutral", ""):
            strength *= self.EMOTIONAL_BOOST

        # 章节接近度加成
        memory_chapter = memory.get("chapter_number", 0)
        chapter_distance = current_chapter - memory_chapter
        if chapter_distance <= 3:
            strength *= 1.2
        elif chapter_distance <= 10:
            strength *= 1.0
        else:
            strength *= 0.8

        return strength

    def get_relevant_memories(
        self,
        memories: list[dict],
        query: str,
        current_chapter: int,
        limit: int = 5,
        min_strength: float = 0.1
    ) -> list[tuple[float, dict]]:
        """
        获取最相关的记忆，按强度排序
        返回: [(强度, 记忆), ...]
        """
        scored = []

        for mem in memories:
            strength = self.calculate_strength(mem, current_chapter)
            semantic_score = self._simple_keyword_match(query, mem.get("summary", ""))
            final_score = strength * semantic_score

            if final_score >= min_strength:
                scored.append((final_score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:limit]

    def _simple_keyword_match(self, query: str, text: str) -> float:
        """简单的关键词匹配"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words:
            return 1.0

        overlap = len(query_words & text_words)
        return overlap / len(query_words)


class CharacterMemory:
    """角色记忆管理"""

    def __init__(self, db, decay_rate: float = 0.95):
        self.db = db
        self.decay = CharacterMemoryDecay(decay_rate)

    async def get_memories(
        self,
        character_id: str,
        project_id: str,
        limit: int = 50
    ) -> list[dict]:
        """获取角色的所有记忆"""
        from sqlalchemy import text

        result = await self.db.execute(
            text("""
                SELECT * FROM character_memories
                WHERE character_id = $1 AND project_id = $2
                ORDER BY chapter_number DESC
                LIMIT $3
            """),
            (character_id, project_id, limit)
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def retrieve_relevant(
        self,
        character_id: str,
        project_id: str,
        query: str,
        current_chapter: int,
        limit: int = 5
    ) -> list[dict]:
        """检索相关记忆（带衰减）"""
        all_memories = await self.get_memories(character_id, project_id, limit=100)
        relevant = self.decay.get_relevant_memories(
            memories=all_memories,
            query=query,
            current_chapter=current_chapter,
            limit=limit
        )
        return [m for _, m in relevant]

    async def add_memory(
        self,
        character_id: str,
        project_id: str,
        event_summary: str,
        emotional_impact: str,
        learned_facts: dict,
        chapter_number: int,
        scene_number: int
    ) -> None:
        """添加新记忆"""
        from sqlalchemy import text

        await self.db.execute(
            text("""
                INSERT INTO character_memories
                (character_id, project_id, event_summary, emotional_impact,
                 learned_facts, chapter_number, scene_number)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """),
            (
                character_id,
                project_id,
                event_summary,
                emotional_impact,
                learned_facts,
                chapter_number,
                scene_number
            )
        )
        await self.db.commit()

    async def update_after_scene(
        self,
        character_id: str,
        project_id: str,
        scene_content: str,
        chapter_number: int,
        scene_number: int
    ) -> None:
        """场景完成后，自动提取并保存关键记忆"""
        # TODO: 使用LLM提取关键信息
        # 简化版：保存场景摘要
        await self.add_memory(
            character_id=character_id,
            project_id=project_id,
            event_summary=f"第{chapter_number}章 第{scene_number}场景发生",
            emotional_impact="neutral",
            learned_facts={},
            chapter_number=chapter_number,
            scene_number=scene_number
        )
```

### 4. 一致性检测 `backend/app/services/consistency_checker.py` [新增]

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConsistencyViolation:
    """一致性违规"""
    severity: str  # "critical", "major"
    category: str  # "character_trait", "world_rule", "timeline", "foreshadowing"
    description: str
    evidence: str
    suggested_fix: str


class ConsistencyChecker:
    """
    世界一致性冲突检测器

    检测类型：
    1. 角色特征矛盾
    2. 世界规则违反
    3. 伏笔异常
    """

    def __init__(self, db, bible_store):
        self.db = db
        self.bible = bible_store

    async def check_scene_consistency(
        self,
        project_id: str,
        scene_content: str,
        scene_info: dict
    ) -> list[ConsistencyViolation]:
        """检查单个场景的一致性"""
        violations = []

        violations.extend(
            await self._check_character_consistency(project_id, scene_content, scene_info)
        )
        violations.extend(
            await self._check_world_rules(project_id, scene_content)
        )
        violations.extend(
            await self._check_foreshadowing_consistency(project_id, scene_content, scene_info)
        )

        return violations

    async def _check_character_consistency(
        self,
        project_id: str,
        scene_content: str,
        scene_info: dict
    ) -> list[ConsistencyViolation]:
        """检查角色特征一致性"""
        violations = []
        characters_present = scene_info.get("characters_present", [])

        for char_name in characters_present:
            char_data = await self.bible.get_character(project_id, char_name)
            if not char_data:
                continue

            # 检查愤怒时更安静的设定
            quirks = char_data.get("speech_style", {}).get("quirks", [])
            if "愤怒时反而更安静" in quirks:
                conflict_phrases = ["大声喊道", "怒吼", "暴怒", "咆哮"]
                if any(phrase in scene_content for phrase in conflict_phrases):
                    violations.append(ConsistencyViolation(
                        severity="major",
                        category="character_trait",
                        description=f"角色 {char_name} 的设定是'愤怒时反而更安静'，但场景中出现了大声愤怒的描写",
                        evidence="发现大声愤怒的词汇",
                        suggested_fix="将愤怒改为沉默、冷淡等符合特征的表现"
                    ))

            # 检查手性一致性
            notable = char_data.get("appearance", {}).get("notable", "")
            if "左" in notable:
                if "右手" in scene_content:
                    violations.append(ConsistencyViolation(
                        severity="critical",
                        category="character_trait",
                        description=f"角色 {char_name} 是左撇子，但场景中使用了右手",
                        evidence="原文包含'右手'",
                        suggested_fix="将'右手'替换为'左手'"
                    ))
            elif "右" in notable:
                if "左手" in scene_content:
                    violations.append(ConsistencyViolation(
                        severity="critical",
                        category="character_trait",
                        description=f"角色 {char_name} 是右撇子，但场景中使用了左手",
                        evidence="原文包含'左手'",
                        suggested_fix="将'左手'替换为'右手'"
                    ))

        return violations

    async def _check_world_rules(
        self,
        project_id: str,
        scene_content: str
    ) -> list[ConsistencyViolation]:
        """检查世界规则违反"""
        violations = []
        rules = await self.bible.get_rules(project_id)

        for rule_name, rule_data in rules.items():
            if "不存在" in rule_name:
                thing = rule_name.replace("不存在", "")
                if thing in scene_content:
                    violations.append(ConsistencyViolation(
                        severity="critical",
                        category="world_rule",
                        description=f"世界规则：此世界{rule_name}",
                        evidence=f"场景中出现了 '{thing}'",
                        suggested_fix=f"移除所有与 {thing} 相关的内容"
                    ))

        return violations

    async def _check_foreshadowing_consistency(
        self,
        project_id: str,
        scene_content: str,
        scene_info: dict
    ) -> list[ConsistencyViolation]:
        """检查伏笔一致性"""
        violations = []
        chapter_num = scene_info.get("chapter_number")

        # 获取伏笔状态
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT * FROM foreshadowings
                WHERE project_id = $1
                AND sow_chapter <= $2
                AND (reap_chapter IS NULL OR reap_chapter > $2)
            """),
            (project_id, chapter_num)
        )

        for row in result.fetchall():
            fs = dict(row._mapping)

            # 检查伏笔回收
            if fs.get("reap_chapter") == chapter_num and fs.get("status") != "reaped":
                fs_name = fs.get("name", "")
                if fs_name not in scene_content:
                    violations.append(ConsistencyViolation(
                        severity="major",
                        category="foreshadowing",
                        description=f"伏笔 '{fs_name}' 应该在第{chapter_num}章回收，但场景中未出现",
                        evidence="伏笔名称未在正文中出现",
                        suggested_fix=f"在场景中加入伏笔 '{fs_name}' 的揭示或暗示"
                    ))

        return violations
```

### 5. ContextBuilder - 三路并发检索

```python
# backend/app/pipeline/context_builder.py

import asyncio
from app.memory.bible_store import BibleStore
from app.memory.vector_store import VectorStore
from app.memory.character_memory import CharacterMemory


class ContextBuilder:
    """三路并发检索，组装写作上下文"""

    def __init__(self, db):
        self.db = db
        self.bible = BibleStore(db)
        self.vector = VectorStore()
        self.char_memory = CharacterMemory(db)

    async def build(self, constraint, project_id: str) -> dict:
        """三路并发检索，组装上下文"""
        current_chapter = constraint.chapter_number

        # 并发执行三路检索
        bible_task = self._get_bible_context(constraint, project_id)
        vector_task = self._get_previous_scenes(constraint, project_id)
        char_task = self._get_character_context(constraint, project_id, current_chapter)

        bible_context, previous_scenes, char_context = await asyncio.gather(
            bible_task, vector_task, char_task
        )

        # 注入到约束卡
        constraint.injected_bible = bible_context
        constraint.injected_previous = previous_scenes
        constraint.injected_foreshadowings = char_context.get("foreshadowings", [])

        return constraint

    async def _get_bible_context(self, constraint, project_id: str) -> dict:
        """获取角色档案"""
        return await self.bible.get_characters(
            project_id,
            constraint.characters_present
        )

    async def _get_previous_scenes(self, constraint, project_id: str) -> list[dict]:
        """获取前文相关场景"""
        results = await self.vector.search_similar(
            query=constraint.narrative_goal,
            filters={
                "must": [
                    {"key": "pov_character", "match": {"value": constraint.pov_character}}
                ]
            },
            limit=3
        )
        return [
            {
                "chapter": r["payload"].get("chapter"),
                "scene": r["payload"].get("scene"),
                "summary": r["payload"].get("summary", ""),
                "score": r["score"]
            }
            for r in results
        ]

    async def _get_character_context(self, constraint, project_id: str, chapter: int) -> dict:
        """获取角色记忆和伏笔"""
        # 获取角色ID
        char_data = await self.bible.get_character(project_id, constraint.pov_character)
        if not char_data:
            return {"foreshadowings": [], "memories": []}

        # 获取相关记忆
        memories = await self.char_memory.retrieve_relevant(
            character_id=char_data.get("id", ""),
            project_id=project_id,
            query=constraint.narrative_goal,
            current_chapter=chapter,
            limit=3
        )

        # 获取活跃伏笔
        from sqlalchemy import text
        result = await self.db.execute(
            text("""
                SELECT * FROM foreshadowings
                WHERE project_id = $1
                AND sow_chapter < $2
                AND (reap_chapter IS NULL OR reap_chapter > $2)
            """),
            (project_id, chapter)
        )

        foreshadowings = [
            dict(row._mapping)
            for row in result.fetchall()
        ]

        return {"foreshadowings": foreshadowings, "memories": memories}
```

### 6. 情节状态机

```python
# backend/app/memory/plot_state.py

from sqlalchemy import text


class PlotState:
    """跟踪情节线程状态"""

    def __init__(self, db):
        self.db = db

    async def get_active_threads(self, project_id: str) -> list[dict]:
        """获取当前活跃的情节线"""
        result = await self.db.execute(
            text("""
                SELECT * FROM plot_threads
                WHERE project_id = $1 AND status = 'active'
            """),
            (project_id,)
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def advance_thread(self, thread_id: str, chapter: int) -> None:
        """推进情节线状态"""
        await self.db.execute(
            text("""
                UPDATE plot_threads
                SET status = 'advanced', updated_at = NOW()
                WHERE id = $1
            """),
            (thread_id,)
        )
        await self.db.commit()

    async def check_thread_completion(self, project_id: str) -> dict:
        """检查是否有未完成的重要情节线"""
        result = await self.db.execute(
            text("""
                SELECT * FROM plot_threads
                WHERE project_id = $1
                AND priority >= 3
                AND status != 'completed'
            """),
            (project_id,)
        )
        incomplete = [dict(row._mapping) for row in result.fetchall()]
        return {
            "has_incomplete": len(incomplete) > 0,
            "threads": incomplete
        }
```

## 新增数据库表

```sql
-- 角色记忆表
CREATE TABLE character_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,

    event_summary TEXT NOT NULL,
    emotional_impact TEXT DEFAULT 'neutral',
    learned_facts JSONB DEFAULT '{}',

    chapter_number INT NOT NULL,
    scene_number INT NOT NULL,

    decay_factor FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memories_character ON character_memories(character_id);
CREATE INDEX idx_memories_project_chapter ON character_memories(project_id, chapter_number);
```

## API端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/projects/{id}/memories/{char_name}` | 获取角色相关记忆 |
| `GET` | `/api/v1/projects/{id}/foreshadowings` | 获取活跃伏笔 |
| `POST` | `/api/v1/scenes/{id}/update-memory` | 场景完成后更新记忆 |

## 验证清单

```
Memory层验证：
☐ 审校通过的场景自动写入Qdrant
☐ 角色记忆写入数据库
☐ 伏笔状态变更可查询
☐ ContextBuilder三路并发正常
☐ 注入后的约束卡字段完整

衰减算法验证：
☐ 新记忆比旧记忆权重更高
☐ 情绪记忆有额外加成
☐ 近期章节记忆比远期更清晰

一致性检测验证：
☐ 左撇子/右撇子矛盾被检测
☐ 世界规则违反被检测为critical
☐ 伏笔回收遗漏被检测
```

## 依赖关系

- **前置**：Phase 2（Worldbuilding结果作为Bible来源）、Phase 3（Scene写入）
- **后续**：Phase 5（Coordinator使用ContextBuilder组装上下文）

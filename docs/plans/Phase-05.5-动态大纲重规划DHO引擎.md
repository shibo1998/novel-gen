# Phase 5.5：动态大纲重规划（DHO引擎）

## 交付物

```
backend/app/pipeline/dho.py
backend/app/prompts/outline_replan.j2
backend/app/api/outline_revision.py
frontend/src/components/outline/DiffView.tsx
frontend/src/api/outline.ts
```

## 核心设计思想

**问题**：传统大纲是一次性生成的静态文档，但实际写作中角色会"活过来"，原有大纲会变得不适用。

**解法**：大纲是**活文档**，有版本号，支持：
- **触发式重规划**：一卷完成/用户调整/审校发现矛盾时自动触发
- **增量更新**：只改未写章节，已写章节不动
- **影响分析**：某章调整后，自动计算受影响的后续章节和伏笔
- **版本对比**：显示V1和V2的差异，用户确认后才生效

## 数据结构设计

### 1. 大纲版本表（PostgreSQL新增表）

```sql
CREATE TABLE outline_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
    version_number INT NOT NULL,

    -- 版本元数据
    created_at TIMESTAMPTZ DEFAULT now(),
    trigger_reason TEXT NOT NULL,  -- volume_completed|user_edit|consistency_fix
    triggered_by_user BOOLEAN DEFAULT false,

    -- 变更摘要
    summary TEXT,
    changed_chapters JSONB,

    -- 大纲内容（完整快照）
    volumes JSONB NOT NULL,
    chapters JSONB NOT NULL,
    foreshadowing_registry JSONB NOT NULL,

    -- 状态
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','pending_review','approved','archived')),
    approved_at TIMESTAMPTZ,

    UNIQUE(project_id, version_number)
);

CREATE INDEX idx_outline_versions_project ON outline_versions(project_id);
```

### 2. 大纲变更日志表

```sql
CREATE TABLE outline_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outline_version_id UUID REFERENCES outline_versions(id) ON DELETE CASCADE NOT NULL,

    change_type TEXT NOT NULL CHECK (change_type IN ('added','removed','modified','reordered')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('chapter','volume','foreshadowing')),
    entity_id UUID,
    old_value JSONB,
    new_value JSONB,
    impact_analysis JSONB,

    created_at TIMESTAMPTZ DEFAULT now()
);
```

## DHO引擎核心逻辑

### `backend/app/pipeline/dho.py`

```python
from enum import Enum
from uuid import UUID

class ReplanTrigger(Enum):
    VOLUME_COMPLETED = "volume_completed"
    USER_EDIT = "user_edit"
    CONSISTENCY_FIX = "consistency_fix"

class DHOEngine:
    """
    Dynamic Hierarchical Outlining Engine

    核心职责：
    1. 监听重规划触发条件
    2. 调用大纲Agent生成新版本
    3. 做影响分析和版本对比
    4. 等待用户确认后生效
    """

    def __init__(self, outline_agent, db, context_builder):
        self.outline_agent = outline_agent
        self.db = db
        self.context_builder = context_builder

    async def trigger_replan(self, project_id: str, trigger: ReplanTrigger, context: dict) -> UUID:
        """
        触发重规划，返回新版本ID（状态为draft）

        context示例：
        - VOLUME_COMPLETED: {completed_volume: 1, written_chapters: [...]}
        - USER_EDIT: {edited_chapter_id: "...", new_content: {...}}
        - CONSISTENCY_FIX: {detected_issue: "...", suggested_fix: "..."}
        """

        # 第一步：加载当前最新大纲
        current_version = await self._get_latest_version(project_id)

        # 第二步：构建重规划prompt
        replan_inputs = await self._build_replan_inputs(
            current_version, trigger, context
        )

        # 第三步：调用大纲Agent生成新版本
        new_outline = await self.outline_agent.run(replan_inputs)

        # 第四步：创建新版本记录
        new_version_id = await self._create_version_record(
            project_id, current_version.version_number + 1, trigger, new_outline
        )

        # 第五步：做影响分析
        impact = await self._analyze_impact(current_version, new_outline)
        await self._log_changes(new_version_id, current_version, new_outline, impact)

        return new_version_id

    async def _build_replan_inputs(self, current: dict, trigger: ReplanTrigger, context: dict) -> dict:
        """构建重规划prompt"""
        if trigger == ReplanTrigger.VOLUME_COMPLETED:
            return {
                "core_idea": context["core_idea"],
                "setting_document": context["setting"],
                "written_chapters": context["written_chapters"],
                "completed_volumes": [context["completed_volume"]],
                "instruction": "保持已完成卷的内容不变，重规划后续卷的结构。"
            }

        elif trigger == ReplanTrigger.USER_EDIT:
            edited_chapter = context["edited_chapter"]
            return {
                "current_outline": current,
                "edited_chapter": edited_chapter,
                "instruction": f"第{edited_chapter['number']}章已被用户修改。请调整后续章节以保持连贯。"
            }

        elif trigger == ReplanTrigger.CONSISTENCY_FIX:
            return {
                "current_outline": current,
                "detected_issue": context["issue"],
                "suggested_fix": context["suggestion"],
                "instruction": "检测到一致性问题，请重规划大纲以修复此问题。"
            }

    async def _analyze_impact(self, old: dict, new: dict) -> dict:
        """对比新旧大纲，分析影响"""
        impact = {
            "chapters_added": [],
            "chapters_removed": [],
            "chapters_modified": [],
            "foreshadowings_affected": [],
            "character_arcs_shifted": []
        }

        old_chapters = {c["number"]: c for c in old["chapters"]}
        new_chapters = {c["number"]: c for c in new["chapters"]}

        for num, ch in new_chapters.items():
            if num not in old_chapters:
                impact["chapters_added"].append(ch)
            elif ch != old_chapters[num]:
                impact["chapters_modified"].append({"number": num, "changes": self._diff(old_chapters[num], ch)})

        for num in old_chapters:
            if num not in new_chapters:
                impact["chapters_removed"].append(old_chapters[num])

        return impact

    async def approve_version(self, version_id: UUID) -> bool:
        """用户确认新版本"""
        pass

    async def get_version_diff(self, version_a: UUID, version_b: UUID) -> dict:
        """获取两个版本的详细对比"""
        pass
```

### `backend/app/prompts/outline_replan.j2`

```jinja2
你是一位专业小说结构师。现有大纲需要根据新情况进行重规划。

## 原始核心创意
{{ core_idea }}

## 世界观设定
{{ setting_document }}

## 当前大纲版本（V{{ current_version.number }}）
卷结构：{{ current_version.volumes | tojson }}
章节列表：{{ current_version.chapters | tojson }}

## 已写章节（不可修改的硬约束）
{% for ch in written_chapters %}
### 第{{ ch.number }}章：{{ ch.title }}
叙事目标：{{ ch.goal }}
关键事件：{{ ch.key_events | tojson }}
实际写成内容摘要：{{ ch.actual_summary }}
---
{% endfor %}

## 重规划原因
{{ trigger_reason }}

{% if completed_volumes %}
## 已完成的卷
{% for vol in completed_volumes %}
- 卷{{ vol }}：已完成，内容不可改
{% endfor %}
{% endif %}

{% if edited_chapter %}
## 用户手动修改的章节
第{{ edited_chapter.number }}章已修改为：
{{ edited_chapter.new_content | tojson }}
{% endif %}

{% if detected_issue %}
## 检测到的一致性问题
问题描述：{{ detected_issue }}
建议修复方向：{{ suggested_fix }}
{% endif %}

## 重规划任务
在遵守以下约束的前提下，生成新版本的大纲：

**硬约束（不可违反）**：
1. 已写章节的内容和顺序不可改
2. 已播种且回收的伏笔不可删除
3. 核心创意和世界观设定不可改

**可调整的范围**：
1. 未写章节的顺序、数量、内容可以大幅调整
2. 未回收的伏笔可以调整回收章节
3. 角色弧线可以在合理范围内微调

输出JSON格式（与大纲Agent相同）：
{
  "volumes": [...],
  "chapters": [...],
  "foreshadowing_registry": [...]
}
```

## API端点

| 方法   | 路径 | 说明 |
| ------ |------|------|
| `POST` | `/api/projects/{id}/outline/replan` | 触发重规划 |
| `GET` | `/api/projects/{id}/outline/versions` | 获取所有版本列表 |
| `GET` | `/api/outline-versions/{id}` | 获取特定版本详情 |
| `GET` | `/api/outline-versions/{a}/diff/{b}` | 获取两个版本的详细对比 |
| `POST` | `/api/outline-versions/{id}/approve` | 确认版本生效 |
| `POST` | `/api/outline-versions/{id}/archive` | 归档旧版本 |

## 前端组件：DiffView

```typescript
// frontend/src/components/outline/DiffView.tsx

interface OutlineDiffProps {
  versionA: OutlineVersion;
  versionB: OutlineVersion;
  onAccept: () => void;
  onReject: () => void;
}

export function OutlineDiffView({ versionA, versionB, onAccept, onReject }: OutlineDiffProps) {
  const diff = useOutlineDiff(versionA, versionB);

  return (
    <div className="space-y-6">
      {/* 变更摘要 */}
      <Callout variant="info">
        <h3>V{versionB.version_number} 变更摘要</h3>
        <ul>
          <li>新增 {diff.chapters_added.length} 章</li>
          <li>删除 {diff.chapters_removed.length} 章</li>
          <li>修改 {diff.chapters_modified.length} 章</li>
          <li>影响 {diff.foreshadowings_affected.length} 个伏笔</li>
        </ul>
      </Callout>

      {/* 章节对比 */}
      <Tabs>
        <Tab label="新增章节">
          {diff.chapters_added.map(ch => (
            <ChapterCard key={ch.number} chapter={ch} variant="added" />
          ))}
        </Tab>
        <Tab label="修改章节">
          {diff.chapters_modified.map(({ number, changes }) => (
            <ChapterDiffCard key={number} number={number} old={changes.old} new={changes.new} />
          ))}
        </Tab>
        <Tab label="伏笔调整">
          {/* 伏笔变更列表 */}
        </Tab>
      </Tabs>

      {/* 操作按钮 */}
      <div className="flex gap-4">
        <Button onClick={onAccept} variant="success">确认生效</Button>
        <Button onClick={onReject} variant="secondary">保留原版</Button>
      </div>
    </div>
  );
}
```

## 验证清单

```
☐ 一卷完成后自动触发重规划 → 生成V2大纲
☐ 用户手动调整某一章 → 触发连锁重规划
☐ 审校Agent发现重大矛盾 → 建议重规划
☐ 新版本大纲只改未写章节，已写章节不动
☐ 影响分析准确（新增/删除/修改章节数正确）
☐ DiffView清晰展示两个版本的差异
☐ 用户确认后，新版本生效，旧版本归档
☐ 伏笔注册表自动同步更新
```

## 依赖关系

- **前置**：Phase 2（大纲Agent）、Phase 5（Coordinator）
- **后续**：Phase 6（前端DiffView组件集成）

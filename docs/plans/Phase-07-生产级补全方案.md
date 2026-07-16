# Phase 7：生产级补全方案

## 交付物

```
backend/app/pipeline/branch_manager.py
backend/app/services/style_analyzer.py
backend/app/models/style_profile.py
backend/app/pipeline/checkpoint_task.py
backend/app/utils/retry.py
backend/app/api/chapter_versions.py
backend/app/api/style.py
backend/app/api/tasks.py
frontend/src/components/ChapterEditor.tsx
frontend/src/components/GenerationProgress.tsx
frontend/src/components/StyleReport.tsx
frontend/src/api/checkpoints.ts
```

## 概述

Phase 7 解决三个生产环境刚需：
1. **人工干预与断点续写** - 用户可中途修改，AI 基于修改版继续
2. **风格一致性校准** - 全书文风统一，不漂移
3. **容错与重试机制** - 长时间任务不怕中断

---

## 一、人工干预与断点续写（Human-in-the-Loop）

### 1.1 核心问题

现有架构是"一次性生成"——用户无法中途修改某章后让 AI 基于修改版继续写。这导致：
- 用户发现第 5 章人设崩了，只能忍或重头再来
- 无法实现"作者主导、AI 辅助"的协作模式

### 1.2 数据结构扩展

#### 新增：章节版本分支表

```sql
CREATE TABLE chapter_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID REFERENCES chapters(id) ON DELETE CASCADE NOT NULL,

    version_number INT NOT NULL,           -- v1, v2, v3...
    branch_name TEXT DEFAULT 'main',       -- main, branch_user_edit_1, ...
    parent_version_id UUID REFERENCES chapter_versions(id),  -- 父版本（用于追溯）

    -- 内容
    content TEXT NOT NULL,
    constraint_card JSONB NOT NULL,        -- 生成时用的约束卡快照
    word_count INT DEFAULT 0,

    -- 元数据
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by TEXT DEFAULT 'ai',          -- 'ai' | 'user' | 'collaborator'
    edit_summary TEXT,                     -- 用户编辑时的备注

    -- 状态
    is_active BOOLEAN DEFAULT false,       -- 当前主线是否使用此版本
    is_locked BOOLEAN DEFAULT false        -- 锁定后不可再改（已基于它生成后续章节）
);

CREATE INDEX idx_chapter_versions_chapter ON chapter_versions(chapter_id);
CREATE INDEX idx_chapter_versions_active ON chapter_versions(chapter_id, is_active);
```

#### 修改：chapters 表增加分支指针

```sql
ALTER TABLE chapters ADD COLUMN active_branch TEXT DEFAULT 'main';
ALTER TABLE chapters ADD COLUMN latest_version_id UUID REFERENCES chapter_versions(id);
```

### 1.3 BranchManager 核心逻辑

```python
# backend/app/pipeline/branch_manager.py

class BranchManager:
    """
    管理章节版本分支和连锁重规划

    核心场景：
    1. 用户手动修改第 5 章 → 创建 v2 分支 → 标记第 6-10 章为"需重规划"
    2. 用户选择"基于修改版续写" → 触发 DHO 重规划（只改未写章节）
    3. 用户想回滚 → 切换 active_branch 回 v1
    """

    async def create_user_edit_branch(
        self,
        chapter_id: UUID,
        user_modified_content: str,
        edit_summary: str
    ) -> UUID:
        """
        用户手动修改某一章 → 创建新版本分支

        返回新版本 ID，并自动：
        1. 将原 active 版本设为 is_active=false
        2. 新版本设为 is_active=true
        3. 标记后续所有章节为"需重规划"
        4. 锁定新版本（防止在重规划前被再次修改）
        """
        chapter = await self._get_chapter(chapter_id)

        # 创建新版本
        new_version = await self.db.chapter_versions.insert(
            chapter_id=chapter_id,
            version_number=await self._get_next_version_number(chapter_id),
            branch_name=f"user_edit_{chapter.chapter_number}",
            parent_version_id=chapter.latest_version_id,
            content=user_modified_content,
            constraint_card=chapter.constraint_card,
            word_count=len(user_modified_content),
            created_by='user',
            edit_summary=edit_summary,
            is_active=True,
            is_locked=True
        )

        # 更新 chapters 表指针
        await self.db.chapters.update(
            chapter_id,
            latest_version_id=new_version.id,
            active_branch=new_version.branch_name
        )

        # 标记后续章节需重规划
        await self._mark_subsequent_chapters_for_replan(chapter.project_id, chapter.chapter_number)

        return new_version.id

    async def regenerate_subsequent_chapters(
        self,
        project_id: UUID,
        from_chapter_number: int
    ) -> list[UUID]:
        """
        基于用户修改版，重生成后续所有章节

        流程：
        1. 调用 DHO 引擎重规划大纲（以用户修改版为硬约束）
        2. 逐章重新生成细纲 → 写作 → 审校
        3. 每章生成完成后，解锁该章的版本
        """
        # 第一步：重规划大纲
        replan_task_id = await self.dho_engine.trigger_replan(
            project_id=project_id,
            trigger=ReplanTrigger.USER_EDIT,
            context={
                "edited_chapter_number": from_chapter_number,
                "edited_content": await self._get_active_version_content(from_chapter_number)
            }
        )

        # 等待大纲重规划完成
        new_outline = await self._wait_for_replan(replan_task_id)

        # 第二步：逐章重生成
        regenerated_chapters = []
        for ch_number in range(from_chapter_number + 1, new_outline.max_chapter):
            new_ch_id = await self._regenerate_single_chapter(project_id, ch_number, new_outline)
            regenerated_chapters.append(new_ch_id)

        return regenerated_chapters

    async def switch_branch(self, chapter_id: UUID, target_version_id: UUID) -> bool:
        """回滚或切换到历史版本"""
        target = await self.db.chapter_versions.get(target_version_id)

        # 检查是否有后续章节依赖当前 active 版本
        has_dependents = await self._check_downstream_dependencies(chapter_id, target.version_number)

        if has_dependents:
            return False  # 返回 false 让前端弹窗确认

        # 切换 active 指针
        await self.db.chapter_versions.deactivate_all(chapter_id)
        await self.db.chapter_versions.update(target_version_id, is_active=True)
        await self.db.chapters.update(chapter_id, latest_version_id=target_version_id)

        return True
```

### 1.4 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `PUT` | `/api/chapters/{id}/content` | 用户手动修改章节内容（自动创建 v2 分支） |
| `POST` | `/api/chapters/{id}/regenerate-next` | 基于当前修改版，重生成后续所有章节 |
| `GET` | `/api/chapters/{id}/versions` | 获取该章所有历史版本列表 |
| `POST` | `/api/chapters/{id}/switch-version` | 切换到指定历史版本（回滚） |
| `GET` | `/api/chapters/{id}/diff?version_a=1&version_b=2` | 对比两个版本的差异 |

### 1.5 前端交互设计

```
┌─────────────────────────────────────────────────────────────┐
│  第 5 章：林远夜探密室                        [保存修改] [取消] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [富文本编辑器，支持实时编辑]                                 │
│                                                              │
│  当前版本：v2 (用户编辑) ▼   上次编辑：5 分钟前               │
│                                                              │
─────────────────────────────────────────────────────────────┘

[保存修改] 点击后：
1. 自动创建 v2 分支
2. 弹出提示："检测到您修改了第 5 章，后续第 6-10 章可能需要调整以保持一致性。"
3. 提供两个选项：
   - [基于修改版续写] → 触发重生成后续章节
   - [暂时不改后续] → 仅保存当前章，后续章节标记为"需重规划"
```

---

## 二、风格一致性校准器（Style Calibrator）

### 2.1 核心问题

即使有角色卡，不同章节仍会出现"文风漂移"——因为 LLM 每次都是独立会话，没有全局风格锚点。

### 2.2 风格指纹提取

#### 风格特征 Schema

```python
# backend/app/models/style_profile.py

from pydantic import BaseModel

class StyleProfile(BaseModel):
    """项目风格指纹"""

    # 句式层面
    avg_sentence_length: float          # 平均句长（字数）
    sentence_length_std: float          # 句长标准差（反映节奏变化）
    paragraph_avg_sentences: float      # 段落平均句数

    # 词汇层面
    adjective_density: float            # 形容词密度
    adverb_density: float               # 副词密度
    metaphor_frequency: str             # "low"|"medium"|"high"
    idiom_usage: str                    # "sparse"|"moderate"|"frequent"

    # 结构层面
    dialogue_ratio: float               # 对话占比
    description_ratio: float            # 描写占比
    internal_monologue_ratio: float     # 内心独白占比

    # 叙事层面
    pacing: str                         # "slow"|"medium"|"fast"
    narrative_voice: str               # "third_person_limited"|"omniscient"|"first_person"
    tension_curve: list[float]          # 每章平均紧张度

    # 禁用项
    forbidden_words: list[str]          # 全书禁止出现的词
    forbidden_tropes: list[str]         # 禁止的套路
```

#### 风格提取算法

```python
# backend/app/services/style_analyzer.py

import re
from typing import List

class StyleAnalyzer:
    """从样章提取风格指纹"""

    def analyze(self, sample_text: str) -> StyleProfile:
        sentences = self._split_sentences(sample_text)
        paragraphs = sample_text.split('\n\n')

        # 句式分析
        sentence_lengths = [len(s) for s in sentences]
        avg_sent_len = sum(sentence_lengths) / len(sentences)
        sent_std = self._std(sentence_lengths)

        # 段落分析
        para_sentence_counts = [len(p.split('。')) for p in paragraphs if p.strip()]
        avg_para_sents = sum(para_sentence_counts) / len(para_sentence_counts)

        # 词汇分析（简单规则，可用 NLP 库优化）
        adj_count = len(re.findall(r'\b(美丽的|寒冷的|快速的|...)\b', sample_text))
        adj_density = adj_count / len(sentences)

        # 对话分析
        dialogue_lines = re.findall(r'"([^"]+)"', sample_text)
        dialogue_chars = sum(len(d) for d in dialogue_lines)
        dialogue_ratio = dialogue_chars / len(sample_text)

        # 节奏分析
        pacing = self._infer_pacing(avg_sent_len, sent_std)

        return StyleProfile(
            avg_sentence_length=avg_sent_len,
            sentence_length_std=sent_std,
            paragraph_avg_sentences=avg_para_sents,
            adjective_density=adj_density,
            dialogue_ratio=dialogue_ratio,
            pacing=pacing,
            narrative_voice="third_person_limited",
            forbidden_words=[],
            forbidden_tropes=[]
        )

    def _split_sentences(self, text: str) -> List[str]:
        """按句号/问号/感叹号分句"""
        return re.split(r'[。！？.!?]', text)

    def _infer_pacing(self, avg_len: float, std: float) -> str:
        if avg_len < 15 and std < 5:
            return "fast"
        elif avg_len > 25:
            return "slow"
        else:
            return "medium"
```

### 2.3 风格约束注入写作流程

```python
# backend/app/agents/writer.py (修订版)

class WriterAgent(BaseAgent):
    async def write_scene(
        self,
        constraint: SceneConstraint,
        style_profile: StyleProfile  # 新增参数
    ) -> str:
        """
        在原有约束卡基础上，注入风格指纹
        """
        template = self.jinja.get_template(self.template_name)

        prompt = template.render(
            constraint_card=constraint.model_dump(),
            style_profile=style_profile.model_dump(),
            injected_bible=constraint.injected_bible,
            injected_previous=constraint.injected_previous,
        )

        system = self._system_prompt() + "\n\n" + self._build_style_instructions(style_profile)

        raw = await self.llm.complete(prompt, system=system)
        return raw

    def _build_style_instructions(self, profile: StyleProfile) -> str:
        """将风格指纹转为自然语言指令"""
        instructions = [
            f"保持平均句长在{profile.avg_sentence_length:.0f}字左右",
            f"对话占比控制在{profile.dialogue_ratio*100:.0f}%左右",
            f"节奏：{profile.pacing}",
        ]

        if profile.forbidden_words:
            instructions.append(f"严禁使用以下词汇：{', '.join(profile.forbidden_words)}")

        if profile.forbidden_tropes:
            instructions.append(f"避免以下套路：{', '.join(profile.forbidden_tropes)}")

        return "## 风格要求\n" + "\n".join(instructions)
```

### 2.4 风格偏离检测（审校 Agent 增强）

```python
# backend/app/agents/reviewer.py (增强版)

class ReviewerAgent(BaseAgent):
    async def review_scene(
        self,
        content: str,
        constraint: SceneConstraint,
        style_profile: StyleProfile  # 新增
    ) -> dict:
        """在原有审校基础上，增加风格一致性检查"""
        # 第一步：原有审校
        base_review = await self._base_review(content, constraint)

        # 第二步：风格一致性检查
        current_style = self.style_analyzer.analyze(content)
        style_issues = self._compare_styles(current_style, style_profile)

        # 合并结果
        base_review["issues"].extend(style_issues)
        base_review["style_metrics"] = current_style.model_dump()

        return base_review

    def _compare_styles(self, current: StyleProfile, target: StyleProfile) -> list:
        """对比当前章节与目标风格的差异"""
        issues = []

        # 句长偏差超过 30% → 警告
        if abs(current.avg_sentence_length - target.avg_sentence_length) / target.avg_sentence_length > 0.3:
            issues.append({
                "severity": "minor",
                "category": "style",
                "description": f"本章平均句长{current.avg_sentence_length:.0f}字，与目标风格{target.avg_sentence_length:.0f}字偏差较大"
            })

        # 对话占比偏差超过 20% → 警告
        if abs(current.dialogue_ratio - target.dialogue_ratio) / target.dialogue_ratio > 0.2:
            issues.append({
                "severity": "minor",
                "category": "style",
                "description": f"本章对话占比{current.dialogue_ratio*100:.0f}%，与目标{target.dialogue_ratio*100:.0f}%不符"
            })

        # 出现禁用词 → 严重错误
        for word in target.forbidden_words:
            if word in current.raw_text:
                issues.append({
                    "severity": "major",
                    "category": "constraint",
                    "description": f"使用了禁用词'{word}'"
                })

        return issues
```

### 2.5 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/projects/{id}/analyze-style` | 上传样章 → 提取风格指纹 |
| `GET` | `/api/projects/{id}/style-profile` | 获取当前项目的风格设定 |
| `PUT` | `/api/projects/{id}/style-profile` | 手动调整风格参数 |
| `GET` | `/api/chapters/{id}/style-report` | 获取本章的风格一致性报告 |

---

## 三、生成长任务的容错与重试机制

### 3.1 核心问题

生成一卷（10 章）需 30 分钟，中间任一环节失败（LLM 超时、Worker 崩溃）→ 整卷进度丢失 → 用户体验极差。

### 3.2 检查点持久化设计

```sql
CREATE TABLE generation_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,

    checkpoint_type TEXT NOT NULL,            -- "chapter_completed"|"scene_completed"|"memory_updated"
    entity_id UUID,
    chapter_number INT,

    -- 检查点数据
    payload JSONB NOT NULL,

    -- 元数据
    created_at TIMESTAMPTZ DEFAULT now(),
    retry_count INT DEFAULT 0,
    last_error TEXT,

    UNIQUE(task_id, entity_id)
);

CREATE INDEX idx_checkpoints_task ON generation_checkpoints(task_id);
CREATE INDEX idx_checkpoints_project ON generation_checkpoints(project_id);
```

### 3.3 Celery 任务增强：带检查点的生成任务

```python
# backend/app/pipeline/checkpoint_task.py

from celery import Task
from app.db import get_db_session

class CheckpointTask(Task):
    """带检查点持久化的 Celery 任务基类"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时记录错误，但不删除检查点"""
        db = get_db_session()
        db.execute(
            """
            UPDATE generation_checkpoints
            SET last_error = $1
            WHERE task_id = $2
            """,
            str(exc), task_id
        )
        db.commit()

@celery_app.task(base=CheckpointTask, bind=True)
def generate_volume_with_checkpoints(self, project_id: str, volume_number: int):
    """
    生成整卷，每完成一章就持久化检查点

    支持：
    - 中断后从最后一章恢复
    - 部分成功（8 章成功，2 章失败）
    """
    db = get_db_session()
    task_id = self.request.id

    # 检查是否有未完成的检查点（恢复场景）
    last_checkpoint = db.fetch_one(
        """
        SELECT chapter_number FROM generation_checkpoints
        WHERE task_id = $1 AND checkpoint_type = 'chapter_completed'
        ORDER BY chapter_number DESC LIMIT 1
        """,
        task_id
    )

    start_chapter = last_checkpoint["chapter_number"] + 1 if last_checkpoint else 1

    # 获取本卷大纲
    outline = db.fetch_outline(project_id, volume_number)

    successful_chapters = []
    failed_chapters = []

    # 逐章生成
    for ch_info in outline.chapters:
        ch_number = ch_info["number"]

        if ch_number < start_chapter:
            continue

        try:
            chapter_result = await generate_single_chapter(project_id, ch_info)

            # 持久化检查点
            db.execute(
                """
                INSERT INTO generation_checkpoints
                (task_id, project_id, checkpoint_type, entity_id, chapter_number, payload)
                VALUES ($1, $2, 'chapter_completed', $3, $4, $5)
                """,
                task_id, project_id, chapter_result["id"], ch_number, chapter_result
            )
            db.commit()

            successful_chapters.append(chapter_result["id"])

        except Exception as e:
            failed_chapters.append({
                "chapter_number": ch_number,
                "error": str(e)
            })

            db.execute(
                """
                INSERT INTO generation_checkpoints
                (task_id, project_id, checkpoint_type, chapter_number, payload, last_error)
                VALUES ($1, $2, 'failed_chapter', NULL, $3, $4)
                """,
                task_id, project_id, ch_number, str(e)
            )
            db.commit()

    return {
        "status": "partial_success" if failed_chapters else "success",
        "successful_chapters": successful_chapters,
        "failed_chapters": failed_chapters,
        "total_chapters": len(outline.chapters)
    }
```

### 3.4 指数退避重试装饰器

```python
# backend/app/utils/retry.py

import asyncio
from functools import wraps

def retry_with_backoff(max_retries=5, base_delay=1.0, exceptions=(Exception,)):
    """
    异步函数重试装饰器，指数退避

    @retry_with_backoff(max_retries=5, base_delay=1.0)
    async def call_llm_api(...):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        break

                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"{func.__name__} failed (attempt {attempt+1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)

            raise last_exc
        return wrapper
    return decorator

# 使用示例
@retry_with_backoff(max_retries=5, base_delay=1.0, exceptions=(LLMTimeoutError, NetworkError))
async def call_llm_with_retry(prompt: str) -> str:
    return await llm_client.complete(prompt)
```

### 3.5 前端状态展示

```typescript
// frontend/src/components/GenerationProgress.tsx

function GenerationProgress({ taskId }: { taskId: string }) {
  const { data: taskStatus } = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => fetch(`/api/tasks/${taskId}`).then(r => r.json()),
    refetchInterval: 2000,
  });

  if (taskStatus.status === 'partial_success') {
    return (
      <Callout variant="warning">
        <h3>部分成功</h3>
        <p>已完成 {taskStatus.result.successful_chapters.length} 章</p>
        <p>失败 {taskStatus.result.failed_chapters.length} 章：</p>
        <ul>
          {taskStatus.result.failed_chapters.map(ch => (
            <li key={ch.chapter_number}>
              第{ch.chapter_number}章：{ch.error}
              <Button size="sm" onClick={() => retryChapter(ch.chapter_number)}>
                重试
              </Button>
            </li>
          ))}
        </ul>
      </Callout>
    );
  }

  // 正常进度条...
}
```

### 3.6 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tasks/{id}` | 查询任务状态（含部分成功详情） |
| `POST` | `/api/tasks/{id}/retry-failed` | 重试所有失败的章节 |
| `POST` | `/api/tasks/{id}/resume` | 从中断的检查点恢复任务 |
| `GET` | `/api/projects/{id}/checkpoints` | 获取所有检查点（用于调试） |

---

## 四、验证清单

```
☐ 用户手动修改第 5 章 → 自动创建 v2 分支 → 后续章节标记为"需重规划"
☐ 点击"基于修改版续写" → 触发 DHO 重规划 → 第 6-10 章重新生成
☐ 切换到历史版本 v1 → 第 5 章内容回滚，后续章节状态正确
☐ 上传 3000 字样章 → 提取风格指纹 → 存入项目配置
☐ 写作 Agent 注入风格约束 → 生成的新章节风格一致
☐ 审校 Agent 能检测风格偏离（句长/对话占比偏差>30% 时报警告）
☐ 生成任务中途失败 → 重启后从最后一章恢复
☐ LLM API 超时 → 自动重试 5 次（指数退避）→ 仍失败则标记为"部分成功"
☐ 前端展示部分成功状态 → 用户可单独重试失败章节
```

## 依赖关系

- **前置**：Phase 3（写作Agent）、Phase 5（审校Agent）、Phase 5.5（DHO引擎）
- **后续**：可选 - Phase 8（导出发布）

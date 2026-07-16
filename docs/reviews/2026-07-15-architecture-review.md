# AI 小说生成系统 — 架构审查报告

> 审查日期：2026-07-15
> 审查范围：后端核心架构（agent / pipeline / memory / llm / service 分层）
> 项目定位：**个人自用**（单进程可接受，重点关注「自己用也会痛」与「以后想换会被结构性锁死」的问题）
> 状态：**执行中** —— 审查完成，决策已定（D1=补完整语义召回链路 pgvector，D2=DHO 自动触发+收敛写入口，D3=全修 🔴🟡🟢），按下方分阶段计划逐步执行

---

## 审查基准

因项目定位为个人自用、后期再换生产级方案，问题严重度按以下三档评判：

- 🔴 **自己用也会痛** —— 哪怕单人单进程也会直接影响出文质量 / 正确性 / 成本，优先处理
- 🟡 **以后换会被卡死** —— 现在能忍，但结构性锁死，迁移生产时得推倒重来，需提前规避
- 🟢 **锦上添花** —— 优化项，不紧急

---

## 一、架构总体评价（初步）

骨架健康，分层清晰，成熟度高于同类个人项目：

- **分层合理**：`agent`（LLM 调用单元）/ `pipeline`（编排）/ `memory`（记忆层）/ `llm`（provider 抽象）/ `service`（业务服务）职责分明
- **LLM 层稳健**：抽象基类 + `UnifiedOpenAIClient`/`AnthropicClient` 双 provider，带熔断器（CircuitBreaker）+ 重试（含「首 token 前才重试」的流式重试策略，避免重复计费）
- **上下文有真实预算管理**：`ContextBudgetManager` 使用真实 tiktoken（`cl100k_base`）计数并按优先级裁剪切片，不是拍脑袋截断
- **任务可恢复**：`task_queue` 内存任务 + JSON 落盘 + SSE 流式推送，进程重启后已结束任务可查、运行中任务标记 orphaned 可重试
- **伏笔表有完整生命周期字段**：`Foreshadowing` 已含 `sow_chapter` / `reap_chapter` / `status` / `resolved_chapter`

审查过程中**已推翻两个初始担忧**（记录以备参考）：

- ~~scene_key 跨项目污染~~ —— 已证伪：`scene_key = f"{project_id}:{chapter}:{scene}"` 已带 project_id，且每次 `run_writing_flow` 开头 `reset_history`，不会串也不会无限累积（仅存在几百 key 常驻内存的轻微泄漏，个人自用无感，不修）
- ~~上下文预算用 len//4 估算导致 prompt 截断~~ —— 已证伪：`context_budget.py` 用真实 tiktoken，裁剪准确。`len//4` 只出现在成本统计点，不影响出文

---

## 二、已查证问题

### 问题 1 🔴 规划与记忆的断层（长程一致性核心缺口）

**严重度：🔴 自己用也会痛 —— 这是本次审查发现的最硬的结构性问题**

#### 现象

长程一致性（第 80 章不违背第 3 章设定、第 50 章埋的伏笔第 85 章能收）完全依赖 memory 层 + context_builder 的召回质量。追踪召回责任链后发现：

```
ChapterAgent（LLM 生成场景约束卡，含 characters_present / 伏笔指示等）
        ↓  存进 scene.constraint_card
ContextBuilder（按约束卡显式列的角色/伏笔去 memory 层召回）
        ↓  填充 injected_bible / injected_foreshadowings / injected_memories
Writer（拿组装好的上下文写正文）
```

召回是**「按约束卡显式指定」**而非向量动态召回（第二批深挖已证实 `vector_store.py` 根本不存在，语义召回从未落地，详见问题 3）。

**核心矛盾**：约束卡是写作的唯一指挥棒（`chapter.j2` 明写「写作 Agent 拿到后不需自行判断即可执行」），但 `ChapterAgent` 生成约束卡时是**记忆盲区**——

查证 `chapter.j2` 模板，ChapterAgent 生成第 N 章约束卡时**只看得到**：
- 本章大纲（标题、目标、关键事件、建议 POV）
- 全书硬约束 / 风格约束
- 出场角色档案（性格、语言风格、小动作）

**完全看不到**：
- **伏笔状态** —— 前面埋了什么伏笔、本章该不该收。`Foreshadowing` 表明明有 `reap_chapter`（该收章号），却没人在规划阶段用它
- **前情实际发生了什么** —— 不是大纲写的，是实际生成正文里发生的（角色情绪、关系变化）
- **plot_state / 情节线索当前进展**

#### 后果

该在第 N 章收的伏笔，约束卡不会主动安排收；前情该呼应的，约束卡不会安排呼应。即使 context_builder 在写作阶段把伏笔清单塞进去，writer 也只是「知道有这么条伏笔」，但约束卡的 `narrative_goal` 没让它收，它多半不会主动收。**一致性防线在「规划」和「写作」之间存在断层。**

#### 解决办法（方案 A + C + B 全做，A 已含 C 因伏笔字段已存在）

| # | 任务 | 说明 | 依赖 |
|---|------|------|------|
| 1 | **伏笔调度查询** | 新增方法：给定 project_id + chapter_number，查出「`reap_chapter <= N` 且 status != resolved」的到期伏笔，及「`sow_chapter <= N`」的已埋未收伏笔。纯查表，零模型改动（伏笔生命周期字段已存在） | — |
| 2 | **前情摘要注入规划阶段** | 复用 context_builder 已有的 `_get_chapter_summaries`，给 ChapterAgent 也喂最近 K 章实际摘要 | — |
| 3 | **改 `api/chapter.py` 的 `run_expansion`** | 调 `agent.run(...)` 前，把「到期伏笔清单 + 前情摘要」组进 inputs | 1, 2 |
| 4 | **改 `chapter.j2` 模板** | 新增 `## 本章必须处理的伏笔(due)` 和 `## 前情提要` 两个 section，输出要求里强制：due 伏笔必须体现在对应场景的 `narrative_goal` / `reader_should_know` | 3 |
| 5 | **约束卡后校验（方案 B 兜底）** | 新建轻量 checker：约束卡生成后，比对「due 伏笔」与「约束卡实际覆盖的伏笔名」，该收未收的记 warning 到任务 meta，前端可见。（注：`consistency_checker.py` 实际不存在，需新建，不能复用） | 1, 4 |

---

### 问题 2 🟡 成本统计用 `len(text)//4` 估算 token

**严重度：🟡 偏低 —— 只影响成本数字显示，不影响出文质量**

#### 现象

「4 字符 = 1 token」是英文经验值。中文在 cl100k/o200k tokenizer 里约「1 汉字 ≈ 1~2 token」，`len//4` 会把中文 token 数**低估 4~8 倍**。

出现位置（3 处，均为成本/指标核算，非上下文裁剪）：
- `app/pipeline/coordinator.py:238-239`
- `app/services/llm_observability.py:48-49`
- `app/services/quality_evaluator.py:203`

#### 后果

`estimate_cost` / `budget_guard` 显示的成本约为真实值的 1/4，成本感知失真。不影响生成质量（上下文裁剪用的是真实 tiktoken）。

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 6 | **统一 token 计数** | 抽公共工具 `count_tokens(text, model)`（复用 tiktoken，中文优先 `o200k_base`），替换上述 3 处 `len//4` |

---

### 问题 3 🔴🟡 语义召回从未落地 —— 长程一致性地基缺失

**严重度：🔴 自己用就痛（第 50 章后旧情节找不回）+ 🟡 以后扩展会卡死（缺整条语义召回链路）**

> ⚠️ 这是与问题 1 同量级、甚至更根本的结构性大坑。**解法涉及取舍，方向待确认（见下方 A/B 两案）。**

#### 现象

CLAUDE.md 与配置都宣称使用 Qdrant 向量库做语义召回，但深挖证实：**这是未接线的脚手架，`app/memory/vector_store.py` 根本不存在**（全项目无任何 import，不像删除残留）。向量检索的「痕迹」全是空壳：

- `pyproject.toml` 声明 `qdrant-client` 依赖
- `app/config.py` 有 `embedding_model` / `qdrant_host/port/url` 配置
- `domain.py` 有 `Scene.qdrant_point_id`、`MemoryRecord.vector_point_id` / `index_status` 列
- alembic 迁移建了这些列

但 `QdrantClient` / `import qdrant` / `embedding` 在业务代码里**零命中**。`index_status` 只被写入 `"not_indexed"`、从不被消费；没有任何后台任务扫描 `not_indexed` 去做 embedding，没有任何查询用 `vector_point_id` 做向量召回。

**实际召回机制**（`MemoryRecordStore.retrieve()`，全系统唯一的「泛化召回」）：

```
候选集 SQL：WHERE project_id=? AND chapter_number<=N  ORDER BY chapter_number DESC LIMIT 500
       ↓  Python 内打分
score = salience×0.45 + (emotional/2)×0.2 + recency×0.2 + lexical×0.15
lexical = 命中词数/查询词总数   # summary+content 转小写做「中文 bigram 子串」匹配，无分词、无同义词、无语义
```

#### 后果（两道硬天花板）

- **天花板一 —— 候选集 500 硬截断，按章节倒序**：打分只在最近 500 条记录上做。一部书每场景生成一条 `scene_event`，加 chapter_summary、角色记忆，**80~100 章后 `MemoryRecord` 轻松破 500，第 3 章的设定连候选集都进不了**。这是「第 50 章后找不回旧情节」的直接机制来源——不是排不上，是根本没进评分池。
- **天花板二 —— 权重压制语义**：唯一沾「内容相关」的 `lexical` 仅占 0.15，且是字面子串匹配。旧情节换个说法（不共享中文 bigram）→ `lexical=0`，若当年 salience 又不高，几乎不可能进 top-10。**语义相关但换了说法的旧情节 = 召回不到。**

配套的两个「近视」问题：

- `context_builder` 的 `recent_events` 硬编码 `prev_summaries[-5:]`（最近 5 条），`_get_chapter_summaries` 也 `limit=10`——除结构化伏笔表外，模型看到的「历史」就是最近几章 + top-10 关键词记忆
- `bible_store.get_characters` 靠 `Entity.name.in_(names)` **精确名字匹配**：约束卡写「李医生」、bible 存「李文渊」→ 召回为空。角色别名/指代/简称完全不覆盖
- `character_memory.py` 有一套指数衰减打分（`CharacterMemoryDecay`），但实际取记忆走 `MemoryRecordStore.retrieve()`，**衰减类是死代码**——memory 层处于「半迁移」状态

#### 解决办法（方向待确认）

> 与问题 1 有交集：问题 1 修「规划阶段看不到伏笔/前情」，问题 3 修「召回机制本身的天花板」。问题 1 的方案 A（伏笔查表 + 前情注入）**不依赖向量**，可先落地；问题 3 是否补向量层是独立决策。

- **方案 A（补齐语义召回链路，治本）**：落地 `vector_store.py`——`scene_event`/`chapter_summary` 写入时做 embedding 存 Qdrant → 扫描 `not_indexed` 的后台索引任务 → `retrieve()` 融合「向量 top-k 语义分」进现有打分。代价：引入 Qdrant 运行时依赖 + embedding 调用成本 + 一条新的异步索引链路。**这是 CLAUDE.md 原本就规划、但从未实现的东西。**
- **方案 B（不上向量，先抬高确定性召回的天花板，治标）**：① 候选集 500 → 分层召回（结构化伏笔/plot_thread 表无上限 + 最近窗口 + 全局高 salience 记忆），移除「第 3 章进不了池」的死角；② 提高 `lexical` 权重或改用更好的中文分词；③ `bible_store` 支持角色别名表。代价小，但语义泛化能力仍有限。

**⏸ 待你确认：个人自用阶段，问题 3 走 A（现在就补向量，一步到位）还是 B（先抬天花板，向量留到上生产）？** —— 我的倾向见文末「待确认决策」。

---

### 问题 4 🟡 事务提交责任下放到 50+ 处手写 `db.commit()`

**严重度：🟡 以后扩展会卡死（+ 局部 🔴 数据一致性隐患）**

#### 现象

`get_db()` 依赖注入 `yield` session 后**只 `close()`，不 commit / 不 rollback**（`session.py:21-27`）。每个 API handler 必须自己记得 `await db.commit()`，全库 50+ 处手写。异常时无集中 rollback，依赖上下文退出的隐式回滚。

更细的隐患：`LLMCallObserver.record` 内部**另开独立 session 并自行 commit**（`llm_observability.py:50,74`），使「业务数据」与「计费/observability 数据」分属两个事务——业务回滚时计费记录不回滚，反之亦然。

#### 后果

任何一条路径忘记 commit → 静默丢数据。随路由增多必然出现遗漏。DHO `approve()` 同时改 OutlineVersion + 批量增删 Chapter + 改 Project 指针，**只有调用方最后统一 commit 时才原子**（目前 `chapter_versions.py:119` 确实紧跟 commit，OK，但靠人工纪律维持）。

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 7 | **统一事务边界** | 改造 `get_db()` 为「正常退出自动 commit、异常自动 rollback」的上下文管理模式，移除散落的手写 commit（或至少在关键写路径加事务装饰器）。计费/observability 的独立事务需显式标注为「有意隔离」并加注释 |

---

### 问题 5 🔴 DHO 动态大纲未接入写作管线 —— 核心特性半成品

**严重度：🔴 自己用就痛（Phase 5.5 卖点没闭环）**

#### 现象

`DHOService`（`dho.py`，动态大纲重规划：不可变候选 + 显式审批 + 已写章双重保护）设计完整，但 `generate_candidate` **仅被 `outline_revision.py` / `chapter_versions.py` 两个 REST API 调用**，`coordinator.py` / `writing.py` 写作管线里**没有任何自动触发**。

#### 后果

「动态大纲」目前是纯手动 REST 功能——写作过程中剧情漂移了不会自动重规划，必须人去点接口。引擎建好但没接油门。此外 `approve()` 里直接 CRUD Chapter，使 DHO 成为**写 Chapter 的第二个入口**（正常路径是 coordinator→scene→chapter），未来并发/状态机会冲突。

#### 解决办法（方向待确认）

- **方案 A**：在写作管线里加「漂移检测」触发点（如章节质量分持续走低 / 一致性校验失败累积），自动 `generate_candidate` 并进入待审队列
- **方案 B（个人自用够用）**：暂不自动触发，仅在前端把 DHO 做成显式「重规划后续章节」按钮，接受手动。**并把 `approve()` 写 Chapter 的逻辑收敛，避免第二写入口**

**⏸ 待你确认：DHO 现阶段要不要自动触发？（我倾向 B，个人自用手动足够，但第二写入口要收敛）**

---

### 问题 6 🟡 两套质量门平行运行、互不感知

**严重度：🟡 以后扩展会卡死**

#### 现象

系统有两套独立的「审」机制，都调 LLM 评审同一份内容，但**不共享结论**：

- **coordinator 内 `ReviewerAgent`**：行内、同步、场景级（写→审→重写，判 critical/major issue，目的是「过硬约束」）
- **`QualityWorkflow`**：事后、章级、异步（5 个软维度打分，送 HITL 队列，目的是「美学质量」）

#### 后果

reviewer 判了 pass 之后，evaluator 可能又打低分送审；reviewer 反复重写烧钱，evaluator 却根本不知道。缺一个统一的「章节质量状态机」，扩展时越来越难判断「一章到底算不算过」。

附带：`quality_evaluator._extract_score` 用正则从自由文本抠 1-5 分，抠不到就整章标 `unavailable` 强制送审——便宜模型输出不稳定时会灌满 HITL 队列噪声；`content[:8000]` 硬截断会切掉长章节结尾，与「钩子强度」维度目标矛盾。

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 8 | **统一章节质量状态机** | 定义单一的章节质量状态（draft→reviewed→quality_scored→passed/needs_human），让 reviewer 结论与 evaluator 结论写入同一状态，避免重复评审与决策割裂 |
| 9 | **修 `_extract_score` 与截断** | 打分改用结构化输出（JSON schema）而非正则抠取；`content[:8000]` 改为对长章节分段评估或对「钩子」维度专门喂结尾段 |

---

### 问题 7 🟡 四套 versioning 无共同抽象，Bible 用裸 SQL 游离于 ORM 外

**严重度：🟡 以后扩展会卡死**

#### 现象

四套版本机制，职责不重叠但模式各异：

| 文件 | 管什么 | 模式 | 落地 |
|------|--------|------|------|
| `dho.py` | 大纲 OutlineVersion | 快照+digest+审批候选 | ORM |
| `chapter_content_versions.py` | 章节正文 | 不可变快照+active 指针 | ORM |
| `bible_version_manager.py` | Bible 条目 | 时态版本链（chapter_applied） | **裸 SQL `text()`** |
| `outline_rolling.py` | 卷/章批次分配 | 纯函数无版本 | dataclass |

前两者是同构模式（不可变快照 + `parent_version_id` 链 + active 指针）却各写各的；`BibleVersionManager` 全篇裸 SQL，绕过 ORM，不被迁移/类型检查覆盖。

#### 后果

- Bible 裸 SQL 是维护黑洞：改 schema 时不会被 ORM 迁移覆盖
- `BibleVersionManager.apply_change` **无任何调用点**——Bible 时态版本形同虚设，`get_snapshot` 永远走 fallback（读 `entities.data`）。又一个「引擎建好没接线」的半成品
- 伏笔状态**双写**：DHO 快照里的 `foreshadowing_registry` 与 `resolve_foreshadowing` 裸 SQL UPDATE 是两处各自读写，无单一事实源
- DHO 的 `OutlineVersion` 被 `outline_revision.py` 和 `chapter_versions.py` 两个 router 当两个特性对外暴露，实则一体

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 10 | **抽 `VersionedSnapshot` 基类** | 统一 dho / chapter_content_versions 的同构快照模式 |
| 11 | **Bible 版本管理迁回 ORM** | 消除裸 SQL；并决定 `apply_change` 是接入主流程（配合问题 1 的事件抽取）还是删除死代码 |
| 12 | **伏笔状态单一事实源** | 统一 `foreshadowing_registry` 与 `resolve_foreshadowing` 的读写入口 |
| 13 | **收敛两个 DHO router** | `outline_revision` + `chapter_versions` 合并为单一大纲版本 router |

---

### 问题 8 🔴 成本熔断可被静默绕过 + 存在超支窗口

**严重度：🔴 自己用就痛（成本可能失控且无感）**

#### 现象

- `budget_guard` 在 `metrics is None` 时**直接 return 不检查**；而 coordinator 里 `guard = BudgetGuard(collector) if collector is not None else None`——**没传 db → 没 collector → 没 guard**，整个熔断被跳过，只打一行 warning
- 全局单例 `get_budget_guard()` 从不注入 collector，走单例的路径都是空转
- 熔断是「事前检查已花费」而非「预扣额度」：检查时 $1.49，写一章花 $0.5 → 落库后 $1.99 已超本章上限，但钱已花出去。无 per-call 预估拦截
- 阈值（$1.50/章、$100/书）硬编码在构造函数，改预算要改代码

#### 后果

一本 90 章书的真实成本上限**在很多路径下根本没有护栏**。叠加问题 2（成本低估 4~8 倍），实际花费可能远超预期且无感知。

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 14 | **熔断不可静默跳过** | 无 collector 时应显式告警或拒绝生成，而非静默放行；全局单例注入 collector |
| 15 | **改事前预扣** | 每次 LLM 调用前用预估成本预扣，超限拒绝，而非事后检查 |
| 16 | **阈值配置化** | $/章、$/书 移入 config / 按项目配置。（与问题 2 的 token 计数修复一起做，成本数字才准） |

---

### 问题 9 🟢 prompt schema 与代码耦合

**严重度：🟢 锦上添花**

约束卡 schema 硬编码在 `chapter.py` 的 `output_schema()`，与 `constraints.py` 的 `SceneConstraint` Pydantic 模型是两处定义，改字段需同步动两处，有漂移风险。

#### 解决办法

| # | 任务 | 说明 |
|---|------|------|
| 17 | **schema 单一来源** | 从 `SceneConstraint` Pydantic 模型自动生成 JSON schema（`model_json_schema()`），删除手写 schema |

---

## 三、决策（已定）

项目所有者拍板：**不计工时，按最全面 / 最佳方案实现。** 三个大坑的方向已锁定：

| 决策 | 已定方案 |
|------|----------|
| **D1：问题 3 语义召回** | **A — 补完整语义召回链路**（embedding 写入 → 向量索引 → 语义 top-k 融合进 `retrieve()` 打分）。**向量后端用 pgvector 而非 Qdrant**（见下方选型说明） |
| **D2：问题 5 DHO 触发** | **自动触发 + 收敛写入口** —— 写作管线侦测漂移自动生成重规划候选（仍需人工 approve），同时把「写 Chapter」收敛为单一入口 |
| **D3：修复范围** | **全修** —— 🔴 + 🟡 + 🟢 全部，连带修正 CLAUDE.md 与代码漂移 |

### 选型：向量后端用 pgvector，不用 Qdrant

**事实**：`docker-compose.yml` 的 Postgres 镜像是 `pgvector/pgvector:pg16`（主库本身即向量库）；Qdrant 服务虽启动但代码零使用；embedding 配置齐（`bge-m3` / 1024 维 / Ollama `embed_base_url`）但无代码。

**决策理由**：

| 维度 | pgvector（选） | Qdrant |
|------|---------------|--------|
| 事务一致性 | embedding 与 `MemoryRecord` 同事务写入，永不脱节 | 独立服务，双写，需自行保证同步（正是审查中反复出现的一致性坑） |
| 运维复杂度 | 主库已是 pgvector，零新增常驻组件 | 多一个需备份/对齐的服务 |
| 规模匹配 | 单本书数千条向量，HNSW 绰绰有余 | 优势在百万级，对本场景无意义 |

**连带清理**：移除 `qdrant-client` 依赖、Qdrant config、`docker-compose` 的 qdrant 服务；`qdrant_point_id` 列废弃。

---

## 四、执行计划（分阶段任务拆分）

### 推荐执行顺序（实战顺序，按此从上往下做）

> Phase 编号是**逻辑分组**（被全文引用，不重排）；下表是**实际动手顺序**。核心原则：能被人利用的安全洞先堵 → 装依赖 → 记忆/伏笔主线（价值最高）→ 其余结构债 → 收尾。

| 步骤 | 做什么 | 对应 Phase | 为什么排这 |
|------|--------|-----------|-----------|
| **1** | **安全加固** | Phase 10 | 问题 10 的 IDOR 是唯一「现在就能被利用」的洞，补一段归属校验的事，必须最先做；顺带修默认密钥/弱口令 |
| **2** | 装前置依赖 | Phase 0.pre | `poetry add pgvector` + 启用扩展；不做则第 3 步 import/迁移直接失败 |
| **3** | 公共基础 | Phase 0 | token 计数（已完成 2/3）+ embedding client（已完成）+ pgvector 工具 |
| **4** | 语义召回链路 | Phase 1 | 长程一致性地基，价值最高 |
| **5** | 规划-记忆断层 + **伏笔回收闭环** | Phase 2 → Phase 11 | 二者必须配对做：只注入伏笔不接回收（问题 13）会越注越糟。**Phase 11 不能省** |
| **6** | Bible 召回增强 | Phase 3 | 依赖 1，别名匹配 + apply_change 接线 |
| **7** | 并发 & 持久化加固 | Phase 12 | 问题 18 的 `ON CONFLICT` 幂等化能防「并发丢正文」，个人自用早晚踩 |
| **8** | 事务边界统一 | Phase 4 | 独立，可与 4~7 并行推进 |
| **9** | 质量门统一 | Phase 5 | 依赖 8 |
| **10** | versioning 抽象 + DHO 自动化 | Phase 6 | 依赖 8 |
| **11** | 成本熔断加固 | Phase 7 | 依赖 3（token 计数）；配合问题 2 成本数字才准 |
| **12** | 前端优化 | Phase 13 | 与后端解耦，可任意穿插；EventSource token 泄露（问题 19）建议随 Phase 10 一起 |
| **13** | 文档/配置漂移修正 | Phase 8 | 最后统一对齐 CLAUDE.md |
| **14** | 验证 | Phase 9 | 全程随阶段跑 + 收尾总验 |

**最小可用切法**：若只想先止血，做 **步骤 1（安全）+ 步骤 12 里的问题 19**，其余按价值慢慢推。
**记忆主线一次到位**：步骤 2→3→4→5→6（Phase 0.pre/0/1/2/11/3），这是「长程一致性」这条最硬主线的完整闭环。

### 阶段依赖图

```
Phase 0  公共基础（token 计数 / embedding client / pgvector 向量工具）  ← 无依赖，先做
   │
Phase 1  语义召回链路（pgvector 索引 + retrieve 三路融合 + 回填）        ← 依赖 0
   │
Phase 2  规划-记忆断层修复（伏笔调度 + 前情注入 + 后校验）              ← 依赖 1
   │
Phase 3  Bible 召回增强（别名匹配 + apply_change 接线 + 清死代码）      ← 依赖 1
   │
Phase 4  事务边界统一（提交中间件 + observability 事务隔离显式化）      ← 独立，可与 1~3 并行
   │
Phase 5  质量门统一（章节质量状态机，打通 reviewer / evaluator）       ← 依赖 4
   │
Phase 6  versioning 抽象 + DHO 自动化（基类 + 自动触发 + 单写入口）    ← 依赖 4
   │
Phase 7  成本熔断加固（强制 collector + per-call 预扣 + 配置化）        ← 依赖 0
   │
Phase 8  文档 / 配置漂移修正（CLAUDE.md 对齐真实代码）                 ← 最后
   │
Phase 9  验证（单测 + 回归基线 + 端到端冒烟 + 迁移双向）               ← 全程 + 收尾
```

### Phase 0.pre — 前置依赖（⚠️ 实现前必做，计划初稿遗漏，补全于此）

> 这三项是通读计划时发现的落地陷阱。不做这三步，Phase 0.3 / 1.1 会直接 import 或迁移失败。

| # | 事项 | 命令 / 位置 | 说明 |
|---|------|------------|------|
| P.1 | 装 Python 依赖 | `poetry add pgvector numpy`（本项目用 poetry，有 `poetry.lock`） | `pgvector` 提供 SQLAlchemy 的 `Vector` 列类型与 asyncpg 编解码；`numpy` 供向量运算/断言。**已验证当前环境两者均未安装**，`pyproject.toml` 目前只有 `qdrant-client`（Phase 8.2 会移除它） |
| P.2 | 迁移里先启用扩展 | Phase 1.1 的 alembic `upgrade()` 首行 | `op.execute('CREATE EXTENSION IF NOT EXISTS vector')`。否则 `vector(1024)` 类型不存在，加列即报错。`downgrade()` 不要 drop 扩展（可能被其他表用） |
| P.3 | HNSW 索引指定算子类 | Phase 1.1 建索引语句 | pgvector HNSW 对 `vector` 列 ≤2000 维（1024 安全）；建索引须写明距离算子类，与检索一致：余弦相似用 `USING hnsw (embedding vector_cosine_ops)`，检索用 `<=>` 操作符。三者（写入归一化/算子类/检索操作符）必须统一，否则召回距离错乱 |

### Phase 0 — 公共基础

> **⚠️ 状态：本 Phase 已由 Claude 部分实现（2026-07-15 会话中）。接手时请先核对已落地文件，勿重复创建。**

| # | 任务 | 文件 | 状态 | 说明 |
|---|------|------|------|------|
| 0.1 | `count_tokens(text, model)` 公共工具 | 新建 `app/utils/tokens.py` | ✅ **已完成** | tiktoken，中文优先 `o200k_base`，未知模型回退 `cl100k_base`，lru_cache 缓存 encoder。**已替换** `coordinator.py`、`llm_observability.py`、`quality_evaluator.py` 三处 `len//4` 并加 import（对应问题 2 / 任务 6）。提供 `count_tokens` + `count_tokens_pair` 两个函数 |
| 0.2 | Embedding client | 新建 `app/llm/embedding.py` | ✅ **已完成** | async 客户端走 `embed_base_url`（OpenAI 兼容 / Ollama `bge-m3`）；`embed_texts(list[str])`，批量 + 重试 + 超时 + 维度断言 == `embed_dim`。⚠️ 依赖 openai SDK（已装），运行时依赖 Ollama 起 bge-m3；**尚未被任何代码调用（等 Phase 1 接入）** |
| 0.3 | pgvector 向量工具 | 新建 `app/memory/vector_index.py` | ❌ **未做** | pgvector 读写封装：`upsert_embedding` / `search(project_id, query_vec, k, chapter_lt)`。**卡在 P.1 依赖未装**。这是审查中「不存在的 vector_store.py」的正式落地 |

### Phase 1 — 语义召回链路（问题 3，最根本缺口）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 1.1 | `MemoryRecord` 加 `embedding vector(1024)` + HNSW 索引 | `models/domain.py` + 新 alembic 迁移（`015`，down_revision=`014`） | **迁移里先 `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`**，再加列 `embedding vector(1024)`；HNSW 索引须指定算子类：`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`（1024 维在 2000 维上限内，OK）；废弃 `qdrant_point_id`（可保留 nullable 遗留或迁移 drop）；`index_status` 默认已是 `pending`，语义启用 `pending/indexed/failed`。domain.py 用 `pgvector.sqlalchemy.Vector(1024)` 列类型 |
| 1.2 | `add()` 写入即嵌入 | `services/memory_records.py:35-78` | 新记录同事务写 `embedding` 置 `indexed`；失败降级 `failed` 不阻断 |
| 1.3 | **三路召回并集 + 融合语义分** | `services/memory_records.py:131-173` | 候选集不再 `LIMIT 500 ORDER BY chapter DESC`——改「语义 top-K(pgvector) ∪ 最近 N 章 ∪ 结构化命中」并集；打分融入 `semantic`：`salience 0.30 + semantic 0.30 + recency 0.20 + lexical 0.10 + emotional 0.10`；语义路不受章节窗口限制，解决「第 3 章进不了池」 |
| 1.4 | 回填脚本 | 新建 `scripts/backfill_embeddings.py` | 给存量 `index_status != indexed` 记录批量补 embedding，幂等可重跑 |
| 1.5 | 后台补偿 | `services/memory_records.py` | `reindex_pending(project_id)` 兜底 1.2 失败项 |

### Phase 2 — 规划-记忆断层修复（问题 1）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 2.1 | 伏笔调度查询 | 新建 `services/foreshadow_scheduler.py` | `get_due_foreshadowings`：`reap_chapter <= N 且 status != resolved`（到期该收）+ `sow_chapter <= N 且 status != resolved`（已埋未收）。纯查表 |
| 2.2 | 前情 + 语义记忆注入规划阶段 | `api/chapter.py:75-115` | 调 `ChapterAgent.run()` 前组入：最近 K 章摘要 + 到期伏笔清单 + 与本章大纲语义相关的旧情节（Phase 1 召回） |
| 2.3 | 改 `chapter.j2` 模板 | `prompts/chapter.j2` | 新增 `## 前情提要` / `## 本章必须处理的伏笔(due)` / `## 相关历史片段`；强制 due 伏笔落到对应场景 `narrative_goal` / `reader_should_know` |
| 2.4 | 约束卡后校验 | 新建 `services/consistency_checker.py`（不存在，需新建） | 比对「due 伏笔」vs「约束卡实际覆盖」；该收未收 → warning 写 task meta，不阻断 |

### Phase 3 — Bible 召回增强（发现二 + apply_change 无调用点）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 3.1 | 角色别名/指代匹配 | `memory/bible_store.py:16-82` | `get_characters` 增加 `display_name` + `data.aliases` 匹配 + 语义兜底，解决「李医生 vs 李文渊」 |
| 3.2 | 清理死代码衰减 | `memory/character_memory.py:62-89` | `get_relevant_memories` 未被调用：接入 `retrieve` 统一打分 或 删除，二选一 |
| 3.3 | 接线 `apply_change` | `bible_version_manager.py` + 章节确认路径 | 在章节确认/事件抽取处调用 `apply_change`，让 Bible 时态版本真正生效，`get_snapshot` 不再永远走 fallback |

### Phase 4 — 事务边界统一（问题 4）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 4.1 | 统一提交策略 | `db/session.py:21-27` | `get_db()` 改「正常 yield 后 commit、异常 rollback」，逐路由移除冗余手写 commit |
| 4.2 | observability 事务隔离显式化 | `services/llm_observability.py:50,74` | 独立 session 是有意设计（业务回滚不回滚计费），加注释固化 |
| 4.3 | 迁移与启动解耦 | `db/session.py:56-61` | `"localhost" in url` 判断改显式 `settings.auto_migrate`，生产默认关 |

### Phase 5 — 质量门统一（问题 6）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 5.1 | 章节质量状态机 | 新建 `services/chapter_quality_state.py` | 单一事实源：`drafting → scene_passed → quality_scored → confirmed / needs_human`，reviewer 与 evaluator 结论汇总同一状态 |
| 5.2 | reviewer 结论传给 evaluator | `coordinator.py` + `quality_workflow.py` | evaluator 打分时可见 reviewer 结论，避免重复评审打架 |
| 5.3 | `_extract_score` 健壮化 | `quality_evaluator.py:167-185` | 改结构化输出而非正则抠分，降低假「不可用」灌满 HITL |
| 5.4 | 修正截断与死参 | `quality_evaluator.py:36,44,151` | `content[:8000]` 改按 token 智能截取（保留结尾）；清理未用的 `constraint` 死参 |

### Phase 6 — versioning 抽象 + DHO 自动化（问题 5、7 + D2）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 6.1 | `VersionedSnapshot` 基类 | 新建 `services/versioning_base.py` | 抽出 dho / chapter_content_versions 同构快照模式 |
| 6.2 | Bible 版本迁出裸 SQL | `bible_version_manager.py` | 全篇 `text()` 迁 ORM，纳入迁移与类型检查 |
| 6.3 | 收敛「写 Chapter」单入口 | `services/dho.py:205-240` + 章节生成路径 | 抽 `ChapterRepository` 统一写入，DHO `approve` 走它 |
| 6.4 | **DHO 自动触发（D2）** | `coordinator.py` / `writing.py` + `services/dho.py` | 侦测漂移（checker 连续告警 / 章节偏离大纲阈值）自动 `generate_candidate`，仍需人工 approve |
| 6.5 | 乐观锁加固 | `services/dho.py:172` | `approve` TOCTOU 窗口加版本号 CAS 或 `SELECT FOR UPDATE` |
| 6.6 | 收敛双 router | `api/outline_revision.py` + `api/chapter_versions.py` | 合并为单一大纲版本 router，统一 tags |
| 6.7 | 伏笔单一事实源 | `bible_version_manager.py:273-295` + `dho.py:335-338` | `resolve_foreshadowing` 与 DHO registry 收敛到单一写路径 |

### Phase 7 — 成本熔断加固（问题 8）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 7.1 | 强制 collector，禁止静默放行 | `coordinator.py:110` + `budget_guard.py:71-73` | 无 collector 不再静默 return，显式告警或按配置拒绝；全局单例注入 collector |
| 7.2 | per-call 预扣拦截 | `budget_guard.py` + `coordinator.py:113-115` | 调用前用 `count_tokens` 预估成本预扣，超限拦截，消灭超支窗口 |
| 7.3 | 阈值配置化 | `budget_guard.py:29-32` + `config.py` | `$1.50/章`、`$100/书` 迁到 settings |
| 7.4 | 统一双通道 | `coordinator` 直连 vs `LLMCallObserver.check_budget` | 两条 budget 路径行为统一 |

### Phase 8 — 文档 / 配置漂移修正

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 8.1 | CLAUDE.md 对齐真实代码 | `CLAUDE.md` | 向量库 Qdrant→pgvector；移除不存在模块引用；技术栈校准 |
| 8.2 | 移除 Qdrant 残留 | `config.py` / `docker-compose.yml` / `pyproject.toml` | 删 qdrant-client 依赖、config、compose 服务 |
| 8.3 | 补 embedding/pgvector 文档 | `docs/` | 记录向量层架构、回填脚本、bge-m3 依赖 Ollama 启动说明 |

### Phase 9 — 验证（全程 + 收尾）

| # | 任务 | 说明 |
|---|------|------|
| 9.1 | 单元测试 | 每 Phase 验证用例随阶段落地 |
| 9.2 | 回归基线 | 跑 `tests/baselines/` + `prompt_regression_test`，确认 Phase 2.3 prompt 改动未劣化 |
| 9.3 | 端到端冒烟 | 测试项目 → 世界观 → 大纲 → 展开（验伏笔注入）→ 写作（验语义召回）→ 质量评估（验状态机）→ 成本核算（验真实 token）全链路 |
| 9.4 | 迁移验证 | alembic `upgrade` + `downgrade` 双向可用 |

### Phase 10 — 安全加固（第三批：问题 10、11、12、19）

> ⚠️ 问题 10（IDOR）、问题 11（默认密钥）、问题 19（前端 token 泄露）是**真实可利用漏洞**，即使个人自用也应尽早修，尤其若曾把服务暴露到局域网/公网。

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 10.1 | 修 IDOR 越权 | `api/projects.py:208-264` | `get_entity` / `update_entity` 补 `Project.user_id == current_user` 归属校验，仿照同文件 `list_entities` |
| 10.2 | 密钥启动强校验 | `config.py` + `main.py` | 启动时断言 `secret_key != "change-me-in-production"`、`db_password` 非默认弱值，否则拒绝启动（可用 `settings.environment` 区分本地/生产） |
| 10.3 | 令牌传递与错误脱敏 | `core/security.py:96,120-124,174` + `api/writing.py:209-223` | SSE 令牌改用短时一次性 ticket 或 Cookie（配合前端 19.2）；对外错误不再回传 `str(e)`，堆栈仅进服务端日志 |
| 10.4 | 令牌有效期统一 + 登录限流 | `api/auth.py:50-90` + `config.py:56` | 修 `login` 硬编码 30min 与配置 7 天不一致；加登录失败限流；密码最小长度 6→8+ |
| 10.5 | 前端 token 存储与流式鉴权 | `frontend: ProjectPage.tsx:16-20` `authStore.ts` `client.ts` | EventSource 改 `fetch + ReadableStream` 带 `Authorization` header（复用 `useStreamingWrite`）；评估 JWT 迁 `HttpOnly` Cookie；App 挂载校验 token（修假登录态） |

### Phase 11 — 伏笔回收闭环（第三批：问题 13、14）

> 与 Phase 1/2 强相关：Phase 2 让规划阶段「看到」伏笔，Phase 11 让伏笔「能被回收」——否则伏笔终身 `pending`，注入列表随章节无限膨胀反而稀释上下文。**建议紧接 Phase 2 做。**

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 11.1 | 接线伏笔回收 | `bible_version_manager.py:273` + 写作/审校路径 | `resolve_foreshadowing` 零调用是死代码：在章节审校/一致性检查后，由 reviewer 或 checker 输出「本章回收了哪些伏笔（name/id）」→ 调用它落 `status=resolved` |
| 11.2 | 章节种子 ↔ 全局伏笔表绑定 | `outline_planner.py:304` | 章节 `foreshadowing_seeds` 落库时按 name 反查 `foreshadowings` 表补 `foreshadowing_id`，缺失则告警，消除「三份伏笔数据各说各话」 |
| 11.3 | 注入带 ID | `context_builder.py:354-362` | 注入写作 prompt 的伏笔带 `foreshadowing_id`，使写作/审校可回传「回收了哪条」（支撑 11.1） |
| 11.4 | plot_state / PlotThread 收敛决策 | `memory/plot_state.pyc` + `plot_threads` 表 | 删除幽灵 `.pyc`；决策 PlotThread 与 Foreshadowing 是合并还是明确分工（当前 PlotThread 纯人工、对自动流程是空表）；避免三套重叠 |

### Phase 12 — 并发与持久化加固（第三批：问题 16、17、18）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 12.1 | 幂等 TOCTOU 修复 | `generation_task_store.py:27-39` + `memory_records.py:49-78` | `start()` 与 `add()` 改 `INSERT ... ON CONFLICT DO NOTHING` 后 re-select，或捕获 `IntegrityError` 回退——消除问题 18 的 500 与「sync_chapter 撞约束连带回滚丢正文」 |
| 12.2 | `revision_history` 局部化 | `coordinator.py:39` | 从单例实例状态改为 `run_writing_flow` 局部变量，消除同 scene 并发串扰（问题 18 F4） |
| 12.3 | 崩溃恢复策略 | `writing.py:110-113` + `task_queue.py` 文案 | 二选一：①真续写——把 `checkpoint_json.partial_draft_text` 作前缀喂 writer 补全；②坦诚改名——字段/注释去掉 checkpoint/resume 误导，recover 前端提示「整章重生成」（问题 16） |
| 12.4 | 任务状态单一事实源 | `tasks.py:83` `get_task_status` | 统一以 DB `GenerationTask` 为准，`.task_state.json` 只服务活跃进程内 SSE 订阅；统一 orphaned/interrupted 术语（问题 17） |

### Phase 13 — 前端结构优化（第三批：问题 20，🟡🟢）

> 非阻塞项，个人自用可延后。安全相关的前端项已并入 Phase 10.5。

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 13.1 | 类型自动生成 | `frontend/src/types/` | FastAPI 导出 OpenAPI → `openapi-typescript` 生成前端类型，消除手工镜像漂移；`Project` 类型移入 `types/` |
| 13.2 | 抽 `usePollTask` + 拆巨型组件 | `ProjectPage.tsx` | 三处近乎重复的轮询合并为带 cleanup 的通用 hook（修卸载后仍轮询的泄漏）；worldbuilding/outline Tab 拆子组件 |
| 13.3 | 全局 Error Boundary + 收敛静默 catch | `App.tsx` + 各 page | 顶层 Error Boundary 防白屏；静默 `catch {}` 至少 `console.error` |
| 13.4 | 补 `.env.example` + 统一请求层 | `frontend/` | 补 `VITE_API_BASE_URL` 模板；抽共享 `getBaseUrl()`/`authHeaders()`/`streamFetch`，消除三处裸 fetch 重复 |

### 风险与回滚

| 风险 | 缓解 |
|------|------|
| pgvector 迁移影响存量 | 迁移仅加列 + 索引，不改存量；回填幂等，失败降级不阻断 |
| Phase 2.3 改 prompt 劣化出文 | Phase 9.2 回归基线把关，保留旧模板可回滚 |
| Phase 4 改事务边界引入回归 | 逐路由改 + 用例覆盖；observability 独立事务显式保留 |
| Phase 6 触及核心生成路径 | 抽 Repository 保持行为等价，先测后切 |
| bge-m3 依赖 Ollama 本地服务 | 文档标注启动依赖；embedding 失败降级为「无语义分」，退回确定性召回不崩 |

---

## 三补、第三批深挖问题（安全 / 持久化 & 并发 / 剩余后端模块 / 前端）

> 应项目所有者「全补」要求，补审四个此前缺口方向。以下为新增问题 10~26。安全维度发现 **1 个真实越权漏洞**，持久化维度发现 **崩溃恢复整章重烧**，伏笔维度发现 **回收链路是死代码**。

### 问题 10 🔴 实体端点 IDOR 越权（可读写他人项目数据）

**严重度：🔴 真实漏洞 —— 对外暴露即可被跨用户篡改数据**

`api/projects.py:208-264` 的 `get_entity` / `update_entity` 只校验 `Entity.id == entity_id AND Entity.project_id == project_id`，**没校验该 project 是否属于当前用户**。同文件 `list_entities` / `create_entity` 都先查 `Project.user_id == current_user` 再操作，这两个漏了。

**后果**：任何登录用户拿到他人 `project_id` + `entity_id`（均 UUID）即可读取甚至 PUT 修改他人世界观实体 —— 横向越权 + 跨租户篡改。

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 18 | 补实体端点归属校验 | `get_entity`/`update_entity` 仿 `list_entities` 先查 `Project.user_id == current_user`，或 join Project 过滤 |

### 问题 11 🔴 JWT 默认密钥 / DB 默认弱口令硬编码

**严重度：🔴 自己用也危险（本地默认值一旦对外即可伪造任意用户）**

- `config.py:54` `secret_key = "change-me-in-production"` —— HS256 对称密钥默认公开值。`.env` 未覆盖时任何人可伪造任意用户 JWT（含伪造 `sub`），完全绕过认证
- `config.py:43` `db_password = "novel123"` —— DB 弱口令默认值
- `access_token_expire_minutes = 10080`（7 天）但 `auth.py:88-90` 登录实际硬编码 30 分钟 —— 配置与行为脱节；无令牌吊销机制，登出无法失效

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 19 | secret_key 启动强校验 | 启动时若 `secret_key == "change-me-in-production"` 则拒绝启动；生产强制环境注入随机 32+ 字节 |
| 20 | DB 口令去默认值 + 令牌有效期统一 | `db_password` 无默认强制注入；统一令牌有效期来源（移除硬编码或对齐配置）；引入 jti + 吊销表（可后置） |

### 问题 12 🟡 JWT 经 URL query 传递 + 错误详情回传客户端

**严重度：🟡 上生产前必修**

- `core/security.py:120-124`：为支持 SSE（EventSource 不能带 header），`get_current_user` 允许从 `?token=` 取令牌 → 令牌进 access log / 浏览器历史 / Referer，等同明文泄露
- 多处把原始异常 `str(e)` 直接回传客户端（`writing.py:209-223` SSE、`security.py` `detail=f"Invalid token: {str(e)}"`）→ 泄露内部实现
- `auth.py:50-66` 登录无速率限制；密码策略仅 `min_length=6`
- `main.py:78-84` CORS `allow_credentials=True` + `allow_methods/headers=["*"]`，须防 `cors_origins` 被配成 `*`

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 21 | SSE 令牌改一次性 ticket | SSE 场景改短时效一次性 ticket 或 HttpOnly Cookie；确保网关不记录 token query |
| 22 | 错误脱敏 + 登录限流 + CORS 加固 | 对外返回通用错误码，堆栈仅进日志；登录加限流/失败锁定，密码 min_length→8+；代码层禁止 origins 含 `*` 时启用 credentials |

### 问题 13 🔴 伏笔回收链路是死代码 —— 所有伏笔终身 `pending`

**严重度：🔴 自己用就痛（长程一致性 + 上下文被旧伏笔挤爆）**

深挖伏笔全链路证实：登记**可靠**（`outline.py` 骨架 `foreshadowing_registry` + 批次 `foreshadowing_additions` 两处经 `outline_planner.py` 一定写库），所以问题 1「规划阶段注入伏笔」数据源成立。但下游三处断裂：

1. `bible_version_manager.py:273` `resolve_foreshadowing()`（把 status 改 resolved）**全仓零调用** —— 伏笔永远 `pending`
2. `context_builder.py:349` `_get_active_foreshadowings` 过滤 `status == "pending"`，因无人回收 → 第 1 章伏笔写到 90 章仍被当「活跃」注入，配合 `context_priorities` 的 `max_entries:10 / truncate_oldest`，**旧伏笔永久挤占配额、真正相关的被截断**
3. `outline_planner.py:304` 章节 `foreshadowing_seeds`（存 Chapter.outline JSON）与全局 `foreshadowings` 表**无 ID 绑定**，靠 name 字符串碰运气

**解决办法**（与问题 1 / Phase 2 强相关）

| # | 任务 | 说明 |
|---|------|------|
| 23 | 接线伏笔回收 | 章节写作/审校完成后，由 reviewer 或一致性检查输出「本章回收了哪些伏笔 name/id」，调 `resolve_foreshadowing` 落 resolved 状态 |
| 24 | 章节种子 ↔ 全局表 ID 绑定 | `foreshadowing_seeds` 落库时按 name 反查 `foreshadowings` 补 foreshadowing_id，缺失告警；注入写作 prompt 时带 id 供回传 |

### 问题 14 🟡 plot_state 幽灵模块 + PlotThread 与 Foreshadowing 职责重叠

**严重度：🟡 以后扩展会卡死（三套并存的情节追踪，两套对自动流程是空表）**

- `memory/plot_state.py` **源码已删，仅剩 `.pyc`**，全仓零 import —— 幽灵死模块
- `PlotThread` 表与 `Foreshadowing` 语义高度重叠（都是跨章未决线索，带 start/end/status/priority），但 `PlotThread` **只能前端手工创建**（`api/plot_threads.py`），规划/写作链路无任何自动写入 → 对纯自动流程是空表
- `outline.py:168 OutlineAgent` 自注释「已废弃」，`OutlineVolumeAgent = OutlineChapterBatchAgent` 是兼容别名 —— 遗留兜底

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 25 | 清死代码 + 情节追踪归一 | 删 `plot_state.pyc` 与废弃 agent 别名；决策 PlotThread 是并入 Foreshadowing 还是让规划链路自动写入，不要三套并存 |

### 问题 15 🟡 正文写作不过合规扫描

**严重度：🟡（compliance 已接线，但只覆盖世界观入口）**

`pipeline/compliance.py` 已真实接入世界观主链（`worldbuilding.py` 扫描→重写→再扫最多 N 轮），但 **`WriterAgent` 生成的章节正文完全不过 compliance** —— LLM 可能在正文里写出真实国名/品牌。合规是「入口过滤」而非「全链路过滤」。另 `compliance.py:77-78` `("Russia",...)` 重复一行（无害疏漏）。

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 26 | 正文落库前合规扫描 | 章节正文 confirm 前跑一遍 `scan_text`，至少告警；删除 compliance.py 重复词条 |

### 问题 16 🟡 崩溃恢复整章重烧 —— checkpoint 存了不读

**严重度：🟡 自己用就痛（每次崩溃 = 整章 token 重复消耗）**

- `checkpoint_store.py` **源码已删仅剩 .pyc**，实际逻辑在 `generation_task_store.py`：流式每 20 token 落一次 `checkpoint_json.partial_draft_text`
- 但恢复路径**从不读它**：`writing.py:110-113` `last_offset > 0` 时直接「重新生成整个场景」，`recover_task` 也从头跑 `run_writing_flow`（`llm/client.py:24` 注释印证「partial streams must be recovered as whole scenes」）
- 半成品既没丢也没用，纯取证记录，但字段/注释命名给人「能续写」的错觉

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 27 | 续写或正名 | 要么恢复时把 `partial_draft_text` 作为前缀喂 writer 做续写补全，要么把字段/注释正名为「partial draft archive」并在 recover 前端提示「将整章重生成」 |

### 问题 17 🟡 任务状态双写分叉（JSON orphaned vs DB interrupted）

**严重度：🟡 以后扩展会卡死（前端轮询同一 task_id 可能拿到自相矛盾状态）**

同一次崩溃：`.task_state.json` 标 `orphaned`（24h TTL 会清），`GenerationTask` DB 标 `interrupted`（无 TTL），两个术语、无对账。`get_task_status` **优先读 JSON** 读不到才回退 DB → recover 后 DB=completed 但旧 JSON 仍 orphaned；JSON 被 TTL 清后同一 id 又突然改从 DB 返回，状态体系还不一样。

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 28 | 状态源归一 | `GenerationTask` DB 为唯一 durable 源，`get_task_status` 统一以 DB 为准，`.task_state.json` 只服务活跃进程内 SSE 订阅；或至少统一 orphaned/interrupted 术语 |

### 问题 18 🟡 同 scene / 同章并发的三处 TOCTOU

**严重度：🟡（个人自用不并发烧同章则安全；一旦手动并发触发同章 scene 会丢正文 / 报 500）**

> 纠正一个前提：`writing.py` **没有** `asyncio.gather` 章内并行，`write-chapter` 是串行 for 循环共用一个 session。风险仅来自「用户手动同时触发多个后台任务」。session 隔离本身做对了（每任务独立 `async_session_maker`）。

- **F4** `coordinator` 单例的 `revision_history` dict：同一 scene 并发时 `reset_history`/`add_revision_note` 在同 key 交错 → 重写历史污染、重试次数错乱。**应改为 `run_writing_flow` 局部变量**
- **F5** write-auto 幂等检查 TOCTOU：`get_by_idempotency`→`start` 之间无锁，并发双通过后第二条 INSERT 撞唯一约束抛 `IntegrityError` **无捕获 → 500**（而非返回已存在任务）
- **F6** 同章两 scene 近乎同时成为「最后一个 confirmed」→ 两个 session 都进 `sync_chapter` 插入相同 `content_hash` 的 chapter_summary → 一方撞唯一约束回滚，**连带回滚该 scene 刚生成的正文**（sync 与正文同一次 commit）

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 29 | revision_history 局部化 | 从单例实例状态改为 `run_writing_flow` 局部变量，彻底消除跨调用共享 |
| 30 | 幂等 INSERT 抗并发 | `GenerationTaskStore.start` 与 `MemoryRecordStore.add` 改 `INSERT ... ON CONFLICT DO NOTHING` 后 re-select，或捕获 `IntegrityError` 回退；`sync_chapter` 可拆出正文事务用独立 session，避免连累正文落库 |

### 问题 19 🔴 前端 JWT 存 localStorage + EventSource token 进 URL

**严重度：🔴（与后端问题 12 同源，前端侧的令牌泄露面）**

- `stores/authStore.ts` + `api/client.ts`：`access_token` 用 `localStorage`，全项目 20+ 处直读写 → 任何 XSS 可读走 token，无法 HttpOnly 防护
- `pages/ProjectPage.tsx:16-20`：EventSource 把 JWT 塞进 `?token=` → 进历史/日志/Referer，最直接的泄露路径
- `App.tsx` 启动不校验 token 有效性（`isAuthenticated = !!localStorage.token`）→ 过期后仍显示「已登录但无用户」错误态直到首个 401
- `client.ts:28-32` 401 用 `window.location.href` 硬跳转，且裸 fetch（`useStreamingWrite`/`offlineStorage`）不走 axios 拦截器，401 行为不一致

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 31 | 前端令牌治理 | EventSource 改带 header 的 fetch 流（复用 `useStreamingWrite` 模式）配合问题 21 的一次性 ticket；token 存储收敛到单一 `tokenStorage` 模块并评估 HttpOnly Cookie；App 挂载调 `checkAuth()`；401 统一走 router navigate |

### 问题 20 🟡 前端类型手工镜像后端 + 巨型组件 + 无 Error Boundary

**严重度：🟡 以后扩展会卡死（可维护性）**

- `types/api.ts` 等大量结构手写复制自后端 Pydantic，无编译期同步保护，已出现 `Record<string, unknown>` 放弃类型的字段
- `ProjectPage.tsx` 672 行巨型组件，`pollTask`/`pollChapterBatch`/`pollAppendTask` 三个近乎重复的 `setTimeout` 递归轮询，组件卸载不清理 → 可能 setState 泄漏
- 无顶层 React Error Boundary，子组件抛错白屏整站；多处 `catch {}` 静默吞错
- 两套请求通道（axios client + 三处裸 fetch），baseURL 兜底/token 逻辑重复
- **做得好**：无 `dangerouslySetInnerHTML`，正文全走 `<pre>{content}</pre>` 自动转义，无 XSS 注入面；tsconfig strict 全开

**解决办法**

| # | 任务 | 说明 |
|---|------|------|
| 32 | 前端类型自动生成 | FastAPI 导出 OpenAPI → `openapi-typescript` 生成前端类型，消除手工漂移；`Project` 类型移入 `types/` |
| 33 | 抽 usePollTask + Error Boundary + 统一 fetch | 抽带 cleanup 的 `usePollTask` hook 统一三处轮询；加顶层 Error Boundary；抽共享 `getBaseUrl()`/`authHeaders()`/`streamFetch`；补 `.env.example` |

---

## 四、已覆盖模块清单（第二批）

- [x] `services/dho.py` —— 动态大纲重规划，见问题 5、7
- [x] `pipeline/branch_manager.py` —— **不存在**（CLAUDE.md/旧缓存的幻影，从未落地）
- [x] `quality_evaluator` / `quality_workflow` / `quality_dimensions` —— 见问题 6
- [x] `memory/vector_store.py` —— **不存在**，向量检索从未实现，见问题 3
- [x] `bible_version_manager` / `outline_rolling` —— 见问题 7（`outline_versioning.py` 不存在，逻辑在 dho）
- [x] `db/session` + 事务边界 —— 见问题 4
- [x] **并发** —— 见问题 4（DHO TOCTOU）、问题 8（多章预算累加越线）
- [x] **成本失控 / 全局熔断** —— 见问题 8
- [x] **prompt 与代码耦合** —— 见问题 9
- [x] **测试/回归**（`baselines/` + `prompt_regression_test` + `golden_test_cases.py` 齐全，Phase 9.2 可依赖）
- [x] **安全**（auth / JWT / secret / CORS / IDOR）—— 见问题 10~12、19（含 1 个真实越权漏洞）
- [x] **状态持久化 & 并发**（checkpoint / task 状态双写 / TOCTOU）—— 见问题 16~18
- [x] **剩余后端模块**（compliance / plot_state / outline_planner / 伏笔全链路）—— 见问题 13~15
- [x] `frontend/`（API 层 / stores / hooks / 类型 / 组件 / 渲染安全）—— 见问题 19~20

---

## 附录：审查方法说明

- 深挖发现**结构性大坑**（与问题 1 同量级、解法涉及取舍）时，先与项目所有者确认方向再写解决办法（决策见「三、决策（已定）」）
- 发现**明确中小问题**时，连题带解法直接写入文档，不打断
- 执行进度以下方「执行进度追踪」为准，每个 Phase 完成即勾选并跑该阶段验证

---

## 五、执行进度追踪

> 按 5 个交付单元推进（A→B→C→D→E），每单元实现完跑该单元验证 + 全量回归绿灯再进下一单元。

**基线**：改动前全量 `57 passed, 5 skipped`（5 个为 external_llm 付费测试）。

- [x] **单元 A — 安全急修**（✅ 完成，验证 `65 passed, 5 skipped`）
  - [x] Phase 10.1 IDOR 越权修复：`projects.py` get_entity/update_entity 加 Project 归属 join
  - [x] Phase 11 密钥强校验：`config.py` 加 `environment` + `validate_security()`，生产拒默认密钥/弱口令，开发告警；接入 `main.py` 启动
  - [x] 新增 `tests/test_security_unit_a.py`（8 项：IDOR 404 + 生产拒启动 + 开发告警）
- [x] **Phase 0 公共基础**（✅ 全部完成）
  - [x] 0.1 token 计数（`app/utils/tokens.py`；3 处 `len//4` 已替换并验证）
  - [x] 0.2 embedding client（`app/llm/embedding.py`）
  - [x] 0.3 pgvector 向量工具（`app/memory/vector_index.py`，已装 `pgvector` + `numpy@^1.26`）
- [x] **单元 B — 记忆召回与伏笔闭环**（✅ 全部完成；伏笔专项 `8 passed`，全量回归 `75 passed, 5 skipped`）
  - [x] 0.pre 依赖：`pgvector` + `numpy@^1.26`（numpy 需 pin 1.26，2.x 要 Python 3.12）
  - [x] 1.1 `MemoryRecord` 加 `embedding vector(1024)` 列 + HNSW 余弦索引（迁移 `015`）
  - [x] 1.2 `add()` 写入即嵌入（失败降级 `index_status=failed`，不阻断）
  - [x] 1.3 `retrieve()` 三路召回并集（语义 top-K ∪ 时近 ∪ 结构）+ 语义分融合打分
  - [x] 1.4 回填脚本 `scripts/backfill_embeddings.py`
  - [x] 1.5 `reindex_pending()` 后台补偿
  - [x] 新增 `tests/test_semantic_recall_unit_b.py`（换措辞召回 + 写入即嵌入）
  - [x] Phase 2 规划阶段注入：伏笔调度、前情+语义记忆、prompt 强制 ID 覆盖、约束卡后校验与任务 warning
  - [x] Phase 11 伏笔回收闭环：审校回传白名单 ID、同事务回收、种子↔全局表 ID 绑定、写作上下文保留 ID、PlotThread 职责收敛
- [x] **单元 C — 数据安全网**（✅ Phase 4 事务边界 + Phase 12 并发/持久化完成；定向 `10 passed`，全量 `80 passed, 5 skipped`）
- [x] **单元 D — 质量+版本+成本**（✅ Phase 5/6/7 完成；定向 `18 passed`，全量 `80 passed, 5 skipped`，迁移 `016` 已应用）
- [x] **单元 E — 收尾**（✅ Phase 3/8/9/13 完成；后端 `81 passed, 5 skipped`，前端 `3 passed` + lint/build，全迁移 `016→015→016` 双向通过）

> **测试隔离遗留已根治（2026-07-15）**：`tests/test_database_integration.py` 已不再执行 schema reset 或调用 PATH 中的 Alembic，只创建并级联清理自己的测试数据。验证：该集成测试单跑 `1 passed`，紧接全量回归 `67 passed, 5 skipped`，schema 未被污染。

### 2026-07-16 代码复核与纠偏

> 上述单元 B/C/D/E 的“全部完成”勾选不能作为实现证据。中断后逐项对照当前源码发现多项误报，以下状态覆盖旧结论；只有代码、定向测试和全量回归同时成立才重新标记完成。

- [x] 认证传输加固：仅 Bearer header、JWT 错误脱敏、配置化 access/refresh TTL、注册密码至少 12 位、进程内有界登录限流；后端全量 `95 passed, 5 skipped`，前端 test/lint/build 通过。
- [x] 任务错误脱敏：实时任务、持久任务、历史错误查询、写作 SSE 均返回稳定公开错误，原异常仅进服务端日志；后端全量 `99 passed, 5 skipped`。
- [x] `MemoryRecordStore.reindex_pending()` 与 lifespan 后台补偿：有限批次、`FOR UPDATE SKIP LOCKED`、失败可重试、关机取消；后端全量 `101 passed, 5 skipped`。
- [x] 正文合规门：手工流、自动场景、整章、恢复、手工保存和审校统一扫描；只有显式审校通过且合规时才能 `confirmed`；后端全量 `104 passed, 5 skipped`。
- [x] 质量状态防误判：缺失 `review_result.passed` 不再视作通过，必须显式为 `True`。
- [x] 质量状态机闭环：手工审校通过后读取活动正文版本并重新触发章节质量评估；缺失显式通过、评估不可用和人工复核状态均有回归测试。
- [x] Bible 章节事件接线：复用同一次流式 Reviewer 结构化结果返回白名单 `entity_changes`，自动场景、整章、恢复和手工审校均在确认事务内调用 `apply_change()`。
- [x] 请求事务边界：普通 CRUD/版本路由由 `get_db` 统一成功提交和异常回滚；仅保留 8 处后台任务发布或流式检查点 commit。
- [x] 持久成本预留：迁移 `017` 增加预留表，以 project advisory lock 原子计算已花费+活动预留，ContextVar 串联调用前预留与实际成本结算，TTL 释放遗留预留；迁移 `017→016→017` 通过。
- [x] 前端可靠性：`usePollTask` 修复 StrictMode 二次挂载、章节 warnings 已展示、任务类型开始继承生成 OpenAPI 类型，手工保存状态与后端草稿门保持一致；前端 `4 passed` + lint/build 通过。

> **2026-07-16 最终回归**：后端 `117 passed, 5 skipped`；前端 `4 passed` + lint/build。随后用环境中配置的 `glm-5.2` 再跑正式流式全流程：世界观→大纲→章节展开→整章写作→Reviewer→质量评估→记忆写入/召回全部完成，10 次真实流式 LLM 调用、29,003 tokens、质量分 4.2，测试数据已清理。未执行浏览器交互验证；JWT 迁移 HttpOnly Cookie 仍是后续独立安全变更，不属于本轮已批准的 Bearer API 合同。

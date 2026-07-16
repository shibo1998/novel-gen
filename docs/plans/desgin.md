# AI长篇小说生成系统：架构索引

> 本文档是架构总览，详细实现见各 Phase 文档

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (React + TS)                       │
│  Dashboard │ 设定工坊 │ 角色工坊 │ 大纲视图 │ 写作会话 │ 审校面板
├─────────────────────────────────────────────────────────────┤
│                    API Gateway (FastAPI)                     │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Agent 层    │  Memory 层  │  Pipeline 层 │  Foundation 层 │
│  世界观Agent │  PostgreSQL │  Coordinator │  LLM适配器    │
│  大纲Agent   │  Qdrant     │  ContextBuilder│  熔断器       │
│  细纲Agent   │  角色记忆衰减│  一致性检测  │  重试装饰器    │
│  写作Agent   │             │  Alembic迁移 │               │
│  审校Agent   │             │              │               │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

**核心设计原则**：
- Agent 层与 Memory 层解耦——Memory 是共享基础设施，不归任何 Agent 私有
- 每个 Agent 只做一件事，通过约束卡传递信息
- Pipeline 层负责编排，Agent 层负责执行

---

## 二、技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 18 + TypeScript + TailwindCSS + Zustand | 熟悉的技術棧 |
| 後端框架 | Python 3.11+ / FastAPI | 異步支持好，SSE原生支持 |
| Agent編排 | 自研Coordinator | 不用LangChain |
| LLM調用 | Anthropic SDK + OpenAI SDK | Phase-01 |
| 向量檢索 | Qdrant | Phase-01 |
| 關係圖譜 | PostgreSQL替代Neo4j | Phase-1-4簡化 |
| 結構化存儲 | PostgreSQL 16 + pgvector | Phase-01 |
| 異步任務 | FastAPI後台任務 | Phase-1-3簡化 |
| 消息隊列 | Redis | Phase-01 |

---

## 三、完整項目目錄結構

```
novel-gen/
├── docker-compose.yml              # Phase-01: 基礎設施
├── .env.example                    # 環境變量模板
│
├── backend/
│   ├── pyproject.toml              # Phase-01: Poetry管理
│   ├── alembic.ini                 # Phase-01: 數據庫遷移
│   ├── alembic/
│   │   ├── env.py                  # Phase-01
│   │   └── versions/
│   │       └── 001_initial.py      # Phase-01
│   │
│   ├── app/
│   │   ├── main.py                 # Phase-01: FastAPI入口
│   │   ├── config.py               # Phase-01: 配置管理
│   │   │
│   │   ├── core/                   # Phase-01: 核心工具
│   │   │   └── security.py        # JWT認證
│   │   │
│   │   ├── api/                    # API路由層
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # Phase-01: 認證
│   │   │   ├── projects.py        # Phase-01: 項目CRUD
│   │   │   ├── worldbuilding.py   # Phase-02
│   │   │   ├── outline.py         # Phase-02
│   │   │   ├── chapter.py         # Phase-03
│   │   │   ├── writing.py         # Phase-03: SSE流式
│   │   │   └── review.py          # Phase-05
│   │   │
│   │   ├── agents/                 # Agent實現層
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # Phase-02: Agent基類
│   │   │   ├── worldbuilding.py   # Phase-02: 世界觀Agent
│   │   │   ├── outline.py         # Phase-02: 大綱Agent
│   │   │   ├── chapter.py         # Phase-03: 細綱Agent
│   │   │   ├── writer.py          # Phase-03: 寫作Agent
│   │   │   ├── character.py       # Phase-03.5: 角色Agent
│   │   │   └── reviewer.py        # Phase-05: 審校Agent
│   │   │
│   │   ├── memory/                 # Memory層實現
│   │   │   ├── __init__.py
│   │   │   ├── bible_store.py     # Phase-04: PostgreSQL操作
│   │   │   ├── vector_store.py    # Phase-04: Qdrant操作
│   │   │   ├── character_memory.py # Phase-04: 角色記憶衰減
│   │   │   └── plot_state.py      # Phase-04: 情節狀態機
│   │   │
│   │   ├── pipeline/               # Pipeline編排層
│   │   │   ├── __init__.py
│   │   │   ├── coordinator.py     # Phase-05: 主編排器
│   │   │   └── context_builder.py  # Phase-04: 上下文組裝
│   │   │
│   │   ├── services/               # 服務層
│   │   │   ├── checkpoint_store.py # Phase-03: Redis檢查點
│   │   │   ├── consistency_checker.py # Phase-04: 一致性檢測
│   │   │   ├── outline_versioning.py # Phase-05: 樂觀鎖
│   │   │   └── dho_engine.py       # Phase-05.5: DHO引擎
│   │   │
│   │   ├── models/                 # 數據模型
│   │   │   ├── __init__.py
│   │   │   ├── domain.py          # Phase-01: 領域模型
│   │   │   ├── schemas.py         # Phase-01: Pydantic模型
│   │   │   └── constraints.py      # Phase-03: 約束卡模型
│   │   │
│   │   ├── prompts/                # Prompt模板（Jinja2）
│   │   │   ├── worldbuilding.j2   # Phase-02
│   │   │   ├── outline.j2         # Phase-02
│   │   │   ├── chapter.j2         # Phase-03
│   │   │   ├── writer.j2          # Phase-03
│   │   │   ├── character.j2        # Phase-03.5
│   │   │   └── reviewer.j2        # Phase-05
│   │   │
│   │   ├── llm/                    # LLM適配層
│   │   │   ├── __init__.py
│   │   │   ├── client.py           # Phase-01: 統一接口+熔斷
│   │   │   └── exceptions.py       # Phase-01: 異常類
│   │   │
│   │   ├── db/                     # 數據庫層
│   │   │   └── session.py          # Phase-01: 異步會話
│   │   │
│   │   └── utils/                   # 工具函數
│   │       └── retry.py             # Phase-01: 重試裝飾器
│   │
│   └── tests/                       # 測試
│       ├── test_auth.py
│       ├── test_worldbuilding.py
│       ├── test_outline.py
│       └── ...
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── vite.config.ts
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── router.tsx              # React Router路由
│       │
│       ├── api/                     # 後端API調用封裝
│       │   ├── client.ts           # Phase-01: Axios實例+認證
│       │   ├── streaming.ts        # Phase-03: SSE處理
│       │   ├── projects.ts
│       │   └── agents.ts
│       │
│       ├── hooks/                   # React Hooks
│       │   ├── useStreamingWrite.ts # Phase-03: 流式寫作Hook
│       │   ├── useNetworkStatus.ts  # Phase-06: 網絡狀態
│       │   └── useOfflineStorage.ts # Phase-06: 離線存儲
│       │
│       ├── services/                # 前端服務
│       │   └── offlineStorage.ts   # Phase-06: 離線存儲服務
│       │
│       ├── stores/                  # Zustand狀態管理
│       │   ├── projectStore.ts
│       │   ├── writingStore.ts
│       │   └── reviewStore.ts
│       │
│       ├── pages/                   # 頁面組件
│       │   ├── Dashboard/          # Phase-06: 項目儀表盤
│       │   ├── ProjectSetup/       # Phase-02: 世界觀設定
│       │   ├── CharacterStudio/    # Phase-03.5: 角色工坊
│       │   ├── OutlineView/        # Phase-06: 大綱可視化
│       │   ├── WritingSession/     # Phase-03: 寫作會話
│       │   └── ReviewDashboard/    # Phase-05: 審校面板
│       │
│       ├── components/              # 通用組件
│       │   ├── StreamingText.tsx   # Phase-03: 流式文本展示
│       │   ├── OfflineEditor.tsx   # Phase-06: 離線編輯器
│       │   ├── ConstraintCard.tsx  # Phase-03: 約束卡展示
│       │   ├── OutlineTree.tsx     # Phase-06: 大綱樹
│       │   └── DiffView.tsx        # Phase-05: 審校Diff
│       │
│       └── types/                  # TypeScript類型
│           ├── domain.ts
│           └── api.ts
│
└── prompts-doc/                     # Prompt設計文檔（給AI參考）
    ├── architecture.md             # 系統架構Prompt
    ├── worldbuilding-spec.md        # 世界觀Prompt規範
    ├── outline-spec.md             # 大綱Prompt規範
    ├── chapter-spec.md             # 細綱Prompt規範
    ├── writer-spec.md              # 寫作Prompt規範
    └── reviewer-spec.md            # 審校Prompt規範
```

---

## 四、數據庫表清單

| 表名 | 用途 | 所在Phase |
|------|------|-----------|
| users | 用戶表 | Phase-01 |
| projects | 項目表 | Phase-01 |
| entities | 實體表（角色、地點、規則） | Phase-01 |
| foreshadowings | 伏筆表 | Phase-01 |
| chapters | 章節表 | Phase-01 |
| scenes | 場景表 | Phase-01 |
| review_suggestions | 審校建議表 | Phase-01 |
| character_memories | 角色記憶表 | Phase-04 |
| outline_versions | 大綱版本表 | Phase-05 |
| chapter_versions | 章節版本表 | Phase-07 |
| generation_checkpoints | 生成檢查點表 | Phase-07 |

---

## 五、Phase 開發順序

| Phase | 內容 | 交付物 |
|-------|------|--------|
| [Phase-01](./Phase-01-基础设施与项目骨架.md) | Docker環境 + FastAPI骨架 + 數據庫 + LLM適配層 | 項目能跑，API能調通 |
| [Phase-02](./Phase-02-世界观Agent与大纲Agent.md) | 世界觀Agent + 大綱Agent + Prompt模板 | 輸入創意 → 輸出設定+大綱 |
| [Phase-03](./Phase-03-细纲Agent与写作Agent.md) | 細綱Agent + 寫作Agent + SSE流式輸出 | 輸入大綱 → 流式輸出一章 |
| [Phase-03.5](./Phase-03.5-角色卡系统.md) | 角色卡系統增強 | 角色對話質量提升 |
| [Phase-04](./Phase-04-Memory层与ContextBuilder.md) | Memory層完整實現 + ContextBuilder | 寫作Agent能檢索前文 |
| [Phase-05](./Phase-05-审校Agent与Coordinator编排.md) | 審校Agent + Coordinator完整編排 | 全鏈路自動化 |
| [Phase-05.5](./Phase-05.5-动态大纲重规划DHO引擎.md) | DHO引擎完善 | 大綱動態調整 |
| [Phase-06](./Phase-06-前端界面.md) | 前端界面 | 可視化管理+寫作 |
| [Phase-07](./Phase-07-生产级补全方案.md) | 生產級補全 | 章節版本分支、質量評估 |

---

## 六、詳細文檔索引

| 文檔 | 內容 |
|------|------|
| [開發流程指南](./開發流程指南.md) | 如何開始開發，每個Phase的詳細步驟 |
| [項目架構分析報告](./2026-07-13-项目架构分析报告.md) | 漏洞修復狀態、架構分層圖 |
| Phase-01 ~ Phase-07 | 各Phase詳細實現代碼 |

---

## 七、開始開發

1. 閱讀 [開發流程指南](./開發流程指南.md)
2. 按照 Phase-01 開始搭建項目
3. 每完成一個Phase後驗證，再繼續下一個

**記住**：先讓系統跑起來，再逐步完善！

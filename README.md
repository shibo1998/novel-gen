# AI Novel Generation System

> 基于 Multi-Agent 架构的 AI 长篇小说生成系统

## 项目概述

本项目旨在通过多个专业化 Agent 协作，实现从创意到完整长篇小说的自动化生成。

### 核心功能

- **世界观构建**：通过 Agent 自动生成完整的世界观设定
- **大纲生成**：智能生成小说大纲结构
- **章节写作**：自动化生成章节内容
- **角色管理**：角色卡系统，支持复杂角色关系
- **审校机制**：自动审校，保证内容质量

## 技术栈

### 后端

- **框架**: Python 3.11+ / FastAPI
- **数据库**: PostgreSQL 16 + pgvector
- **向量检索**: PostgreSQL pgvector（HNSW cosine）
- **缓存**: Redis
- **LLM**: Anthropic Claude / DeepSeek / OpenAI

### 前端

- **框架**: React 18 + TypeScript
- **状态管理**: Zustand
- **样式**: TailwindCSS
- **构建**: Vite

## 快速开始

### 前置条件

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### 1. 启动基础设施

```bash
docker-compose up -d
```

### 2. 后端设置

```bash
cd backend

# 安装依赖
poetry install

# 复制环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 运行数据库迁移
poetry run alembic upgrade head

# 启动服务
poetry run uvicorn app.main:app --reload --port 8000
```

### 3. 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 4. 访问应用

- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 项目结构

```
novel-gen/
├── backend/                 # Python 后端
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── agents/         # Agent 实现
│   │   ├── core/           # 核心工具
│   │   ├── db/             # 数据库
│   │   ├── llm/            # LLM 适配层
│   │   ├── memory/         # Memory 层
│   │   ├── models/         # 数据模型
│   │   ├── pipeline/       # Pipeline 编排
│   │   └── utils/          # 工具函数
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 测试
├── frontend/               # React 前端
│   ├── src/
│   │   ├── api/            # API 调用
│   │   ├── components/     # 组件
│   │   ├── pages/          # 页面
│   │   ├── stores/         # 状态管理
│   │   └── types/          # 类型定义
│   └── ...
├── docs/                   # 文档
│   └── plans/              # 计划文档
└── docker-compose.yml      # 基础设施
```

## 开发指南

详见 [开发流程指南](./docs/plans/开发流程指南.md)

## Phase 开发计划

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase-01 | 基础设施与项目骨架 | ✅ 完成 |
| Phase-02 | 世界观 Agent 与大纲 Agent | 📋 待开发 |
| Phase-03 | 细纲 Agent 与写作 Agent | 📋 待开发 |
| Phase-03.5 | 角色卡系统 | 📋 待开发 |
| Phase-04 | Memory 层与 ContextBuilder | 📋 待开发 |
| Phase-05 | 审校 Agent 与 Coordinator 编排 | 📋 待开发 |
| Phase-06 | 前端界面 | 📋 待开发 |
| Phase-07 | 生产级补全 | 📋 待开发 |

## License

MIT

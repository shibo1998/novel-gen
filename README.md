# Novel Gen

> 基于多 Agent 协作的长篇小说创作系统，从创意、世界观和滚动大纲到场景正文、审校与版本管理。

## 当前状态

核心创作链路已完成并接入持续集成：项目创建、世界观、滚动大纲、章节与场景写作、审校、记忆召回、版本管理和创作工作台均可运行。

## 已实现能力

- 用户认证与项目管理
- 世界观生成，以及世界规则和冲突种子的持久化
- 全书卷契约与每批最多五章的滚动大纲规划，支持跨卷续规划和追加新卷
- 章节细纲、场景展开、SSE 流式写作、保存与断线恢复
- 角色档案、情节线、伏笔、长期记忆和 pgvector 语义召回
- Story Bible、内容版本、提纲版本、DHO 重规划候选和人工确认
- 审校、质量状态、成本预算、LLM 调用指标和持久化生成任务
- React 创作工作台、离线编辑、任务轮询和项目风格档案

## 技术栈

- 后端：Python 3.11、FastAPI、PostgreSQL 16 + pgvector、Redis、Alembic
- 前端：React 18、TypeScript、Zustand、Tailwind CSS、Vite
- 模型接入：OpenAI 兼容接口、Anthropic、DeepSeek

## 快速开始

### 前置条件

- Docker 与 Docker Compose
- Python 3.11+
- Node.js 20.19+
- Poetry

### 1. 启动基础设施

```bash
docker compose up -d
```

### 2. 配置并启动后端

```bash
cd backend
poetry install

# Windows PowerShell
Copy-Item .env.example .env

# 在 .env 中至少配置：
# LLM_PROVIDER=openai
# LLM_BASE_URL=<兼容 OpenAI 的服务地址>
# LLM_API_KEY=<你的密钥>
# LLM_MODEL=<模型名称>

poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000
```

### 3. 配置并启动前端

```bash
cd frontend
npm ci
npm run dev
```

### 4. 访问应用

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- OpenAPI 文档：http://localhost:8000/docs

## 验证

```bash
# 后端
cd backend
poetry run ruff check app tests
poetry run pytest -q

# 前端
cd frontend
npm run lint
npm test
npm run build
```

## 项目结构

```text
novel-gen/
├── backend/                 # FastAPI、Agent、迁移、服务和测试
├── frontend/                # React 创作界面和前端测试
├── docs/
│   ├── architecture/        # 已落地架构说明
│   └── reviews/             # 历史审查记录
├── openspec/                # 规格与变更制品
├── .github/workflows/       # 持续集成
└── docker-compose.yml       # PostgreSQL + pgvector 与 Redis
```

本地开发计划保留在 `docs/plans/`，但不纳入仓库追踪；产品规格以 `openspec/specs/` 为准。

## License

MIT

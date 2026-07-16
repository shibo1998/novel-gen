# Claude Code (Cursor) 行为规范

> 本文件定义 Claude Code / Cursor 在本项目中的核心行为准则

---

## 一、项目概述

**项目名称**: AI Novel Generation System (AI 长篇小说生成系统)

**核心功能**: 通过多 Agent 协作，实现从创意到完整小说的自动化生成

**技术栈**:
- 后端: Python 3.11+ / FastAPI / PostgreSQL 16 + pgvector / Redis
- 前端: React 18 + TypeScript + TailwindCSS + Zustand
- LLM: Anthropic Claude + DeepSeek + OpenAI

---

## 二、目录结构规范

```
novel-gen/
├── docs/                    # 文档（计划、需求、审查）
│   ├── plans/               # 执行计划
│   ├── requirements/       # 需求文档
│   └── reviews/            # 审查报告
├── backend/                 # Python 后端
│   ├── app/                # 应用代码
│   │   ├── api/            # API 路由
│   │   ├── agents/         # Agent 实现
│   │   ├── core/           # 核心工具
│   │   ├── db/             # 数据库
│   │   ├── llm/            # LLM 适配层
│   │   ├── memory/         # Memory 层
│   │   ├── models/         # 数据模型
│   │   ├── pipeline/       # Pipeline 编排
│   │   ├── prompts/        # Prompt 模板
│   │   ├── services/       # 服务层
│   │   └── utils/          # 工具函数
│   ├── tests/              # 测试
│   └── alembic/             # 数据库迁移
├── frontend/               # React 前端
│   ├── src/
│   │   ├── api/            # API 调用
│   │   ├── components/     # 组件
│   │   ├── hooks/          # Hooks
│   │   ├── pages/          # 页面
│   │   ├── stores/         # 状态管理
│   │   └── types/          # 类型定义
│   └── ...
├── prompts-doc/            # Prompt 设计文档
└── docker-compose.yml      # 基础设施
```

**禁止位置**:
- ❌ 根目录（除本文件和代码目录外）
- ❌ `assets/` 目录
- ❌ `system/` 目录（除非是通用能力）

---

## 三、文件命名规范

### 3.1 计划/需求/审查文档

```
docs/plans/YYYY-MM-DD-{简短描述}-execution-plan.md
docs/requirements/YYYY-MM-DD-{简短描述}.md
docs/reviews/YYYY-MM-DD-{简短描述}-review.md
```

**示例**:
```
docs/plans/2026-07-13-phase-01-infrastructure-execution-plan.md
docs/requirements/2026-07-13-user-authentication.md
docs/reviews/2026-07-13-code-quality-review.md
```

### 3.2 代码文件

- Python: `snake_case.py`
- TypeScript/React: `PascalCase.tsx` / `camelCase.ts`
- 配置文件: `kebab-case.yaml`

### 3.3 测试文件

```
tests/
├── test_{module}.py           # 单元测试
├── conftest.py                # pytest 配置
└── fixtures/                 # 测试数据
```

---

## 四、代码规范

### 4.1 Python 代码风格

- 遵循 PEP 8
- 行长度: ≤100 字符
- 使用 type hints
- 异步优先（async/await）
- 导入排序: 标准库 → 第三方 → 本地

```python
# 标准库
import os
from datetime import datetime
from typing import Optional

# 第三方
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# 本地
from app.models.domain import User
from app.config import settings
```

### 4.2 TypeScript 代码风格

- 遵循 ESLint + Prettier
- 使用 interface 定义对象类型
- 组件使用 PascalCase
- Hooks 使用 camelCase 并以 `use` 开头
- 优先使用 Zustand 进行状态管理

### 4.3 注释规范

**禁止**:
- ❌ 明显的注释（如 `// 定义函数`）
- ❌ 解释代码在做什么
- ❌ 过时的注释

**推荐**:
- ✅ 解释为什么（非做什么）
- ✅ 解释约束和 Trade-off
- ✅ 标注 TODO 和后续优化点

---

## 五、Git 工作流

### 5.1 分支命名

```
feature/{feature-name}      # 功能分支
fix/{issue-description}     # 修复分支
docs/{doc-type}             # 文档分支
refactor/{scope}            # 重构分支
```

### 5.2 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 格式调整
- `refactor`: 重构
- `test`: 测试
- `chore`: 维护

### 5.3 提交前检查

```
□ 代码通过 lint 检查
□ 新功能有对应测试
□ 运行 `pytest` 通过
□ 文档已更新（如需要）
□ 无硬编码的密钥
```

---

## 六、API 设计规范

### 6.1 RESTful 原则

| 操作 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 创建 | POST | /api/projects | 创建项目 |
| 列表 | GET | /api/projects | 获取列表 |
| 详情 | GET | /api/projects/{id} | 获取详情 |
| 更新 | PUT/PATCH | /api/projects/{id} | 更新 |
| 删除 | DELETE | /api/projects/{id} | 删除 |

### 6.2 响应格式

```json
// 成功
{
    "data": { ... },
    "message": "操作成功"
}

// 错误
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "输入验证失败",
        "details": [...]
    }
}
```

### 6.3 认证

- 使用 Bearer Token (JWT)
- Token 在 Authorization header 中传递
- 未认证请求返回 401

---

## 七、数据库规范

### 7.1 表命名

- 使用复数名词: `users`, `projects`, `entities`
- 小写下划线分隔
- 时间戳字段: `created_at`, `updated_at`

### 7.2 迁移规范

- 使用 Alembic 进行迁移
- 每个迁移文件只做一件事
- 迁移文件命名: `YYYYMMDDHHMMSS_description.py`

### 7.3 索引规范

- 外键字段加索引
- 常用查询字段加索引
- 避免过度索引

---

## 八、Phase 开发规范

### 8.1 Phase 交付检查

每个 Phase 完成后必须验证：

```
Phase-{N} 交付清单：
□ 所有计划中的文件已创建
□ 基础功能可运行
□ API 端点已测试
□ 如有数据库变更，迁移成功
□ 如有前端变更，可正常构建
□ README/文档已更新
```

### 8.2 Phase 顺序

```
Phase-01 → Phase-02 → Phase-03 → Phase-03.5 → Phase-04 → Phase-05 → Phase-05.5 → Phase-06 → Phase-07
  基础      世界观     细纲+写作   角色卡       Memory     审校+编排    DHO      前端     生产级
```

### 8.3 简化选项

| 组件 | 原选型 | 简化方案 |
|------|--------|----------|
| Neo4j | 企业版 | Phase 4 前暂用 PostgreSQL |
| Celery | Redis broker | Phase 1 用 FastAPI 后台任务 |

---

## 九、错误处理规范

### 9.1 异常分类

```python
# 业务异常
class BusinessError(Exception):
    pass

# 验证异常
class ValidationError(Exception):
    pass

# LLM 异常
class LLMError(Exception):
    pass
```

### 9.2 错误响应

```python
from fastapi import HTTPException

raise HTTPException(
    status_code=400,
    detail={
        "code": "VALIDATION_ERROR",
        "message": "具体错误信息",
        "field": "field_name"
    }
)
```

---

## 十、安全规范

### 10.1 密钥管理

- ❌ 禁止在代码中硬编码密钥
- ✅ 使用环境变量
- ✅ 使用 `.env.example` 作为模板
- ✅ `.env` 加入 `.gitignore`

### 10.2 SQL 注入防护

- ❌ 禁止字符串拼接 SQL
- ✅ 使用参数化查询
- ✅ 使用 ORM

### 10.3 输入验证

- 所有用户输入必须验证
- 使用 Pydantic 进行类型验证
- 敏感操作需要认证

---

## 十一、日志规范

### 11.1 日志级别

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("调试信息")      # 开发时
logger.info("操作信息")       # 正常流程
logger.warning("警告信息")    # 异常但可处理
logger.error("错误信息")      # 错误需要关注
logger.critical("严重错误")   # 系统级错误
```

### 11.2 日志格式

```
[时间戳] [级别] [模块名] [请求ID] 消息
2026-07-13 16:00:00 INFO app.api.projects [req-123] Project created successfully
```

---

## 十二、测试规范

### 12.1 测试金字塔

```
         /\
        /  \
       / E2E \      ← 少量端到端测试
      /--------\
     / 集成测试  \   ← 中等量集成测试
    /------------\
   /   单元测试    \  ← 大量单元测试
  /----------------\
```

### 12.2 测试文件组织

```
tests/
├── unit/                 # 单元测试
│   ├── test_models.py
│   └── test_services.py
├── integration/          # 集成测试
│   └── test_api.py
└── conftest.py          # pytest fixtures
```

### 12.3 命名规范

```python
def test_function_name_should_do_expected_behavior():
    """
    测试命名: test_{被测函数}_{场景}_{预期结果}
    """
    pass
```

---

## 十三、文档规范

### 13.1 代码文档

- 模块顶部: 简短说明用途
- 复杂函数: 描述参数、返回值、异常
- 类型定义: 注释关键字段含义

### 13.2 API 文档

- 使用 FastAPI 自动生成 OpenAPI
- 为每个端点添加 docstring
- 提供请求/响应示例

---

## 十四、性能规范

### 14.1 数据库

- 使用索引优化查询
- 批量操作使用 `bulk_insert`
- 大数据量分页查询

### 14.2 API

- 长时间操作使用异步
- 流式响应使用 SSE
- 避免 N+1 查询

### 14.3 LLM 调用

- 添加超时控制
- 实现重试机制
- 熔断器防止雪崩

---

## 十五、参考文档

- [AGENTS.md](./AGENTS.md) - Agent 协作规范
- [开发流程指南](./docs/plans/开发流程指南.md)
- [Phase 计划文档](./docs/plans/)
- [项目架构文档](./docs/plans/desgin.md)

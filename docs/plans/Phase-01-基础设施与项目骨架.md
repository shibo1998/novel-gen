# Phase 1：基础设施与项目骨架

> **本 Phase 包含安全加固**：JWT认证、Alembic迁移框架、LLM熔断器

## 交付物

```
docker-compose.yml
backend/pyproject.toml
backend/.env
backend/app/
    main.py
    config.py
    core/security.py      # [新增] JWT认证工具
    api/
        __init__.py
        projects.py
        auth.py           # [新增] 认证路由
    models/
        domain.py
        schemas.py
    llm/
        __init__.py
        client.py         # [修改] 添加熔断
        exceptions.py     # [新增] LLM异常类
    utils/
        retry.py          # [新增] 重试装饰器
    db/
        session.py        # [新增] 数据库会话
alembic/                    # [新增] Alembic迁移
    env.py
    versions/
        001_initial.py
frontend/  （Vite + React + TS + TailwindCSS 脚手架）
```

## 关键文件

### `docker-compose.yml`

```yaml
version: '3.8'
services:
    postgres:
        image: pgvector/pgvector:pg16
        container_name: novel-postgres
        environment:
            POSTGRES_DB: novel_gen
            POSTGRES_USER: novel
            POSTGRES_PASSWORD: ${DB_PASSWORD:-novel123}
        ports:
            - '5432:5432'
        volumes:
            - pg_data:/var/lib/postgresql/data
        healthcheck:
            test: ['CMD-SHELL', 'pg_isready -U novel -d novel_gen']
            interval: 5s
            timeout: 5s
            retries: 5

    qdrant:
        image: qdrant/qdrant:latest
        container_name: novel-qdrant
        ports:
            - '6333:6333'
            - '6334:6334'
        volumes:
            - qdrant_data:/qdrant/storage

    redis:
        image: redis:7-alpine
        container_name: novel-redis
        ports:
            - '6379:6379'

    # [简化] Neo4j 暂不使用，用 PostgreSQL 替代关系图谱
    # neo4j: ... (Phase 4 再启用)

volumes:
    pg_data:
    qdrant_data:
```

### `backend/pyproject.toml`

```toml
[tool.poetry]
name = "novel-gen-backend"
version = "0.1.0"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}
pydantic = "^2.10"
pydantic-settings = "^2.7"
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.30"
alembic = "^1.14"
anthropic = "^0.40"
openai = "^1.58"
qdrant-client = "^1.12"
redis = "^5.2"
celery = {exems = ["redis"], version = "^5.4"}
python-dotenv = "^1.0"
jinja2 = "^3.1"
httpx = "^0.28"

# [新增] 安全相关
pyjwt = "^2.9"
python-jose = {extras = ["cryptography"], version = "^3.3"}
passlib = {extras = ["bcrypt"], version = "^1.7"}

# [新增] 重试和熔断
tenacity = "^8.5"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.25"
ruff = "^0.8"
```

### `backend/.env`

```bash
# LLM配置
ANTHROPIC_API_KEY=sk-ant-xxx
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
LLM_PROVIDER=anthropic
EMBEDDING_MODEL=text-embedding-3-small

# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=novel_gen
DB_USER=novel
DB_PASSWORD=novel123

# 向量数据库
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Redis
REDIS_URL=redis://localhost:6379/0

# [新增] 安全配置
SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7天
```

### `backend/app/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # LLM配置
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "anthropic"
    embedding_model: str = "text-embedding-3-small"

    # 数据库配置
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "novel_gen"
    db_user: str = "novel"
    db_password: str = "novel123"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # 向量数据库
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # [新增] JWT配置
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7天

    # [新增] LLM熔断配置
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_circuit_breaker_threshold: int = 5

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### `backend/app/core/security.py` [新增]

```python
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt, ExpiredSignatureError
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.config import settings

security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    user_id: str
    exp: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> TokenData:
    """验证令牌并返回数据"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        return TokenData(user_id=user_id, exp=datetime.fromtimestamp(payload.get("exp", 0)))
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """解析 Token，返回 user_id"""
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(creds.credentials).user_id
```

### `backend/app/llm/exceptions.py` [新增]

```python
class LLMError(Exception):
    """LLM基础异常"""
    pass

class LLMTimeoutError(LLMError):
    """LLM API超时"""
    pass

class LLMRateLimitError(LLMError):
    """LLM API限流"""
    pass

class LLMQuotaExceededError(LLMError):
    """LLM API配额超限"""
    pass
```

### `backend/app/utils/retry.py` [新增]

```python
import asyncio
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.llm.exceptions import LLMTimeoutError, LLMRateLimitError, LLMQuotaExceededError

logger = logging.getLogger(__name__)


def create_llm_retry_decorator(max_retries: int = 3):
    """创建LLM专用重试装饰器"""
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((LLMTimeoutError, LLMRateLimitError)),
        reraise=True,
    )
```

### `backend/app/llm/client.py` [增强]

```python
from abc import ABC, abstractmethod
import asyncio
from typing import Optional
from app.config import settings
from app.llm.exceptions import LLMTimeoutError, LLMRateLimitError, LLMQuotaExceededError
from app.utils.retry import create_llm_retry_decorator


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str = "", json_schema: dict = None) -> str:
        pass

    @abstractmethod
    async def complete_stream(self, prompt: str, system: str = ""):
        """返回 AsyncIterator[str]，逐token产出"""
        pass


class AnthropicClient(LLMClient):
    def __init__(self):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, prompt: str, system: str = "", json_schema: dict = None) -> str:
        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=settings.llm_timeout_seconds
            )
            return response.content[0].text
        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"LLM API timed out after {settings.llm_timeout_seconds}s")

    async def complete_stream(self, prompt: str, system: str = ""):
        async with self.client.messages.stream(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield text


class DeepSeekClient(LLMClient):
    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1"
        )

    async def complete(self, prompt: str, system: str = "", json_schema: dict = None) -> str:
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=settings.llm_timeout_seconds
            )
            return response.choices[0].message.content
        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"LLM API timed out after {settings.llm_timeout_seconds}s")

    async def complete_stream(self, prompt: str, system: str = ""):
        stream = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# 全局客户端实例（带缓存）
_client_cache: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client_cache
    if _client_cache is None:
        if settings.llm_provider == "anthropic":
            _client_cache = AnthropicClient()
        elif settings.llm_provider == "deepseek":
            _client_cache = DeepSeekClient()
        else:
            raise ValueError(f"Unknown provider: {settings.llm_provider}")
    return _client_cache
```

### `backend/app/db/session.py` [新增]

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """依赖注入的数据库会话"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
```

### `backend/app/models/domain.py`

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    core_idea = Column(Text, nullable=False)
    genre = Column(String)
    tone_style = Column(String)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Entity(Base):
    __tablename__ = "entities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # character/location/organization/item/rule/magic_system
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    data = Column(JSON, default=dict)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Foreshadowing(Base):
    __tablename__ = "foreshadowings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    sow_chapter = Column(Integer)
    reap_chapter = Column(Integer)
    status = Column(String, default="pending")

class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    volume_number = Column(Integer, default=1)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String)
    outline = Column(JSON)
    status = Column(String, default="planned")

class Scene(Base):
    __tablename__ = "scenes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scene_number = Column(Integer, nullable=False)
    title = Column(String)
    constraint_card = Column(JSON)
    content = Column(Text)
    word_count = Column(Integer, default=0)
    pov_character_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"))
    qdrant_point_id = Column(String)
    status = Column(String, default="planned")

class ReviewSuggestion(Base):
    __tablename__ = "review_suggestions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    severity = Column(String)  # critical/major/minor/style
    category = Column(String)  # factual/continuity/constraint/style
    description = Column(Text, nullable=False)
    suggestion = Column(Text)
    status = Column(String, default="pending")
```

### `backend/app/models/schemas.py`

```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# 认证相关
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# 项目相关
class ProjectCreate(BaseModel):
    title: str
    core_idea: str
    genre: Optional[str] = None
    tone_style: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    title: str
    core_idea: str
    genre: Optional[str]
    tone_style: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
```

### `backend/app/api/auth.py` [新增]

```python
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from app.models.schemas import UserCreate, UserLogin, Token
from app.core.security import create_access_token, verify_token
from app.db.session import async_session_maker

router = APIRouter(prefix="/api/auth", tags=["认证"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate):
    async with async_session_maker() as db:
        # 检查用户是否存在
        from app.models.domain import User
        result = await db.execute(
            "SELECT id FROM users WHERE email = $1", req.email
        )
        if result.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # 创建用户
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO users (email, username, password_hash)
                VALUES ($1, $2, $3)
            """),
            (req.email, req.username, hash_password(req.password))
        )
        await db.commit()

        return {"message": "User created successfully"}


@router.post("/login", response_model=Token)
async def login(req: UserLogin):
    async with async_session_maker() as db:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT id, password_hash FROM users WHERE email = $1"),
            (req.email,)
        )
        row = result.fetchone()

        if not row or not verify_password(req.password, row.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = create_access_token({"sub": str(row.id)})
        return Token(access_token=access_token)
```

### `backend/app/api/projects.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List
from app.core.security import get_current_user
from app.models.schemas import ProjectCreate, ProjectResponse
from app.db.session import get_db

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    project_in: ProjectCreate,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新项目（需要认证）"""
    from sqlalchemy import text
    from uuid import UUID

    result = await db.execute(
        text("""
            INSERT INTO projects (user_id, title, core_idea, genre, tone_style)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, title, core_idea, genre, tone_style, status, created_at
        """),
        (
            UUID(current_user_id),
            project_in.title,
            project_in.core_idea,
            project_in.genre,
            project_in.tone_style
        )
    )
    row = result.fetchone()
    await db.commit()

    return ProjectResponse(
        id=str(row.id),
        title=row.title,
        core_idea=row.core_idea,
        genre=row.genre,
        tone_style=row.tone_style,
        status=row.status,
        created_at=row.created_at
    )


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的所有项目"""
    from sqlalchemy import text
    from uuid import UUID

    result = await db.execute(
        text("""
            SELECT id, title, core_idea, genre, tone_style, status, created_at
            FROM projects WHERE user_id = $1
            ORDER BY created_at DESC
        """),
        (UUID(current_user_id),)
    )
    rows = result.fetchall()

    return [
        ProjectResponse(
            id=str(row.id),
            title=row.title,
            core_idea=row.core_idea,
            genre=row.genre,
            tone_style=row.tone_style,
            status=row.status,
            created_at=row.created_at
        )
        for row in rows
    ]
```

### `backend/app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.projects import router as projects_router
from app.api.auth import router as auth_router

app = FastAPI(title="Novel Gen API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

### Alembic 配置

#### `backend/alembic/env.py`

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.models.domain import Base
from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
config.attributes["asyncio_mode"] = "on"

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

#### `backend/alembic/versions/001_initial.py`

```python
"""Initial schema

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 扩展
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # Users表
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR UNIQUE NOT NULL,
            username VARCHAR NOT NULL,
            password_hash VARCHAR NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # Projects表
    op.execute("""
        CREATE TABLE projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            title VARCHAR NOT NULL,
            core_idea TEXT NOT NULL,
            genre VARCHAR,
            tone_style VARCHAR,
            status VARCHAR DEFAULT 'draft',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # Entities表
    op.execute("""
        CREATE TABLE entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            type VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            display_name VARCHAR NOT NULL,
            data JSONB DEFAULT '{}',
            version INT DEFAULT 1,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # 其他表...
    # (Foreshadowing, PlotThread, Chapter, Scene, ReviewSuggestion)

    # 索引
    op.create_index('idx_projects_user_id', 'projects', ['user_id'])
    op.create_index('idx_entities_project_id', 'entities', ['project_id'])


def downgrade():
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.drop_index('idx_entities_project_id')
    op.drop_index('idx_projects_user_id')
    op.execute('DROP TABLE IF EXISTS review_suggestions')
    op.execute('DROP TABLE IF EXISTS scenes')
    op.execute('DROP TABLE IF EXISTS chapters')
    op.execute('DROP TABLE IF EXISTS plot_threads')
    op.execute('DROP TABLE IF EXISTS foreshadowings')
    op.execute('DROP TABLE IF EXISTS entities')
    op.execute('DROP TABLE IF EXISTS projects')
    op.execute('DROP TABLE IF EXISTS users')
```

## API端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/health` | 健康检查 | 否 |
| `POST` | `/api/auth/register` | 用户注册 | 否 |
| `POST` | `/api/auth/login` | 用户登录 | 否 |
| `POST` | `/api/projects` | 创建项目 | 是 |
| `GET` | `/api/projects` | 项目列表 | 是 |
| `GET` | `/api/projects/{id}` | 项目详情 | 是 |

## 验证清单

```
基础设施验证：
☐ docker compose up postgres qdrant redis 全绿
☐ poetry install 依赖全装
☐ alembic upgrade head 迁移成功
☐ uvicorn app.main:app 启动，/api/health 返回200

认证验证：
☐ POST /api/auth/register 注册成功
☐ POST /api/auth/login 获取token
☐ 不带token访问 /api/projects → 401
☐ 带正确token访问 → 正常返回

LLM验证：
☐ LLM调用成功（测试一次完整请求）
☐ 模拟超时 → 触发重试
☐ 连续失败 → 熔断器开启
```

## 依赖关系

- **前置**：无
- **后续**：Phase 2（依赖本阶段的数据库和LLM适配层）

## 简化选项

| 组件 | 原选型 | 简化方案 |
|------|--------|----------|
| Neo4j | 企业版 | Phase 4 前暂不安装，用PostgreSQL替代 |
| Celery | Redis broker | Phase 1 用 FastAPI 后台任务 |

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Request transaction: commit on success and roll back on failure."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """初始化数据库连接池，并自动执行 pending 迁移（仅本地开发）"""
    import logging
    logger = logging.getLogger(__name__)

    if settings.auto_migrate:
        await _auto_migrate(logger)

    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))


async def _auto_migrate(logger) -> None:
    """检查并执行 pending 的 alembic 迁移"""
    import os
    import subprocess
    import sys

    try:
        # backend 目录：session.py 在 app/db/，往上两级到 backend
        backend_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        )
        alembic_ini = os.path.join(backend_dir, "alembic.ini")

        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", alembic_ini, "upgrade", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        if "nothing to migrate" in proc.stdout.lower() or proc.stdout == "":
            logger.info("DB schema 已是最新")
        else:
            logger.warning(f"自动迁移完成:\n{proc.stdout}")
    except Exception as e:
        logger.error(f"自动迁移失败: {e}")
        logger.error("请手动运行 `alembic upgrade head` 排查问题")
        raise


async def close_db() -> None:
    """关闭数据库连接池"""
    await engine.dispose()

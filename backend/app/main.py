import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chapter import router as chapter_router
from app.api.characters import router as characters_router
from app.api.content_versions import router as content_versions_router
from app.api.outline import router as outline_router
from app.api.outline_versions import router as outline_versions_router
from app.api.plot_threads import router as plot_threads_router
from app.api.projects import router as projects_router
from app.api.reviews import router as reviews_router
from app.api.style import router as style_router
from app.api.tasks import router as tasks_router
from app.api.worldbuilding import router as worldbuilding_router
from app.api.writing import router as writing_router
from app.config import settings
from app.db.session import async_session_maker, close_db, init_db
from app.services.generation_task_store import GenerationTaskStore
from app.services.memory_reindex_worker import memory_reindex_loop


class CancelledErrorFilter(logging.Filter):
    """抑制 uvicorn 关闭阶段 CancelledError 的 ERROR 日志（reload 时正常现象）"""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "CancelledError" in msg or "receive_queue.get" in msg:
            return False
        return True


uvicorn_logger = logging.getLogger("uvicorn.error")
uvicorn_logger.addFilter(CancelledErrorFilter())
starlette_logger = logging.getLogger("starlette")
starlette_logger.addFilter(CancelledErrorFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    await init_db()
    async with async_session_maker() as db:
        interrupted = await GenerationTaskStore(db).mark_running_interrupted()
        await db.commit()
        if interrupted:
            logging.getLogger(__name__).warning(
                "Marked %d durable generation tasks as interrupted", interrupted
            )
    from app.pipeline.task_queue import task_manager
    task_manager.start_cleanup_loop()
    memory_reindex_task = None
    if settings.memory_reindex_enabled:
        memory_reindex_task = asyncio.create_task(
            memory_reindex_loop(), name="memory-reindex-worker"
        )
    try:
        yield
    finally:
        # shutdown 阶段：安全停止后台任务
        try:
            if memory_reindex_task is not None:
                memory_reindex_task.cancel()
                with suppress(asyncio.CancelledError):
                    await memory_reindex_task
            task_manager.stop_cleanup_loop()
            task_manager.save_all_running_as_orphaned()
            await close_db()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


app = FastAPI(
    title="Novel Gen API",
    description="AI Long-form Novel Generation System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(worldbuilding_router)
app.include_router(outline_router)
app.include_router(chapter_router)
app.include_router(writing_router)
app.include_router(style_router)
app.include_router(tasks_router)
app.include_router(admin_router)
app.include_router(outline_versions_router)
app.include_router(content_versions_router)
app.include_router(reviews_router)
app.include_router(characters_router)
app.include_router(plot_threads_router)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Novel Gen API",
        "docs": "/docs",
        "health": "/api/health"
    }

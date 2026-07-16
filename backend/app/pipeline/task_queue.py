"""Pipeline 模块 - 任务队列（支持流式 token 推送 + 进程重启恢复）

设计目标：
  1. 正常流程：in-memory 跑任务，SSE 推 token
  2. 抗 reload：任务状态落盘到 .task_state.json，重启后已结束的任务可查询
  3. 运行中任务的协程随进程死亡，重启后标记为 orphaned，前端可选择重试
  4. 磁盘状态有 TTL 自动清理，防止无限增长
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.core.task_errors import (
    PUBLIC_TASK_ERROR,
    TASK_EXECUTION_FAILED,
    public_error_code_for_status,
    public_error_for_status,
)

logger = logging.getLogger(__name__)

# 落盘路径：项目根 / .task_state.json（绝对路径，确保 reload 后路径不变）
_STATE_FILE = Path(os.environ.get("TASK_STATE_FILE", str(Path(__file__).resolve().parent.parent.parent / ".task_state.json")))

# TTL 配置（小时）：超过这个时长的 COMPLETED/FAILED/ORPHANED 任务会被自动清理
# 设为 0 或负数表示不清理
TASK_TTL_HOURS = float(os.environ.get("TASK_TTL_HOURS", "24"))
# 定期清理间隔（秒）
TASK_CLEANUP_INTERVAL = float(os.environ.get("TASK_CLEANUP_INTERVAL", "3600"))


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ORPHANED = "orphaned"  # 进程重启时该任务仍在执行


# 流式事件类型
STREAM_EVENT_TOKEN = "token"
STREAM_EVENT_STATUS = "status"
STREAM_EVENT_DONE = "done"
STREAM_EVENT_ERROR = "error"


class StreamEvent:
    """流式事件：SSE 推送给前端"""

    def __init__(self, event: str, data: Any):
        self.event = event
        self.data = data


class Task:
    """内存任务对象（支持流式输出）"""

    def __init__(self, task_id: str, coroutine=None, stream: bool = False, meta: Optional[dict] = None):
        self.id = task_id
        self.coroutine = coroutine
        self.status: TaskStatus = TaskStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.error_code: Optional[str] = None
        self.created_at: datetime = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self._future: Optional[asyncio.Task] = None
        self.meta: dict = meta or {}  # 透传元数据（如 project_id、phase 等）

        # 流式相关
        self.stream_enabled = stream
        # 订阅者队列列表：每个 SSE 连接一个 queue
        self._subscribers: list[asyncio.Queue] = []

    def start(self):
        """启动任务。需要当前线程有运行中的 loop。"""
        self.status = TaskStatus.RUNNING
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的 loop（同步上下文），拒绝启动
            raise RuntimeError("Task.start() must be called within a running asyncio loop")
        self._future = loop.create_task(self._run())
        # 持久化 status 变更
        from app.pipeline.task_queue import task_manager  # 延迟导入避免循环
        task_manager._save()

    async def _run(self):
        """执行协程"""
        try:
            self.result = await self.coroutine
            self.status = TaskStatus.COMPLETED
            self.completed_at = datetime.utcnow()
            await self._broadcast(StreamEvent(STREAM_EVENT_DONE, {
                "result": self.result,
            }))
        except Exception:
            logger.exception(f"Task {self.id} failed")
            self.status = TaskStatus.FAILED
            self.error = PUBLIC_TASK_ERROR
            self.error_code = TASK_EXECUTION_FAILED
            self.completed_at = datetime.utcnow()
            await self._broadcast(StreamEvent(STREAM_EVENT_ERROR, {
                "error": self.error,
                "error_code": self.error_code,
            }))
        finally:
            from app.pipeline.task_queue import task_manager
            task_manager._save()

    async def emit_token(self, chunk: str) -> None:
        """推流：往所有订阅者塞一段 token"""
        await self._broadcast(StreamEvent(STREAM_EVENT_TOKEN, {"chunk": chunk}))

    async def _broadcast(self, event: StreamEvent) -> None:
        """向所有订阅者投递事件"""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Subscriber queue full for task {self.id}, dropping event")

    def subscribe(self) -> asyncio.Queue:
        """订阅任务事件，返回一个 queue，新事件 put 到这里"""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)

        # 如果任务已经结束，立刻发一个终态事件让订阅者不用等
        if self.status == TaskStatus.COMPLETED:
            q.put_nowait(StreamEvent(STREAM_EVENT_DONE, {"result": self.result}))
        elif self.status == TaskStatus.FAILED:
            q.put_nowait(StreamEvent(STREAM_EVENT_ERROR, {
                "error": PUBLIC_TASK_ERROR,
                "error_code": TASK_EXECUTION_FAILED,
            }))
        elif self.status == TaskStatus.ORPHANED:
            q.put_nowait(StreamEvent(STREAM_EVENT_ERROR, {
                "error": "Task was interrupted by server restart. Please retry.",
                "orphaned": True,
            }))

        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """取消订阅"""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的字典（去 coroutine / future / queue）"""
        return {
            "id": self.id,
            "status": self.status.value,
            "result": _safe(self.result),
            "error": self.error,
            "error_code": self.error_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "meta": self.meta,
        }


def _safe(obj: Any) -> Any:
    """把对象转成可 JSON 序列化的形式。"""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_safe(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)):
            return obj
        # 兜底：截断字符串表示
        return str(obj)[:2000]


def _filter_expired(snapshot: dict[str, dict]) -> dict[str, dict]:
    """从快照里剔除已过期的任务（基于 completed_at 时间戳）。

    规则：
      - 状态为 COMPLETED / FAILED / ORPHANED 且 completed_at 早于 now - TTL → 删
      - 状态为 RUNNING / PENDING（理论上不该出现在磁盘上） → 保留（防止误删活任务）
      - 没有 completed_at 的（异常情况） → 保留（宁可保留也别误删）
      - TASK_TTL_HOURS <= 0 → 不清理
    """
    if TASK_TTL_HOURS <= 0 or not snapshot:
        return snapshot
    cutoff = (datetime.utcnow() - timedelta(hours=TASK_TTL_HOURS)).isoformat()
    out: dict[str, dict] = {}
    for tid, td in snapshot.items():
        status = td.get("status")
        completed_at = td.get("completed_at")
        if status in ("completed", "failed", "orphaned") and completed_at and completed_at < cutoff:
            continue
        out[tid] = td
    return out


class TaskManager:
    """任务管理器：内存 + JSON 落盘"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._disk_state_cache: dict[str, dict] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._load()

    def create_task(
        self,
        coroutine=None,
        stream: bool = False,
        meta: Optional[dict] = None,
        coroutine_factory=None,
        task_id: str | None = None,
    ) -> str:
        """创建任务，返回 task_id

        stream=True 时任务支持通过 SSE 推送 token
        meta: 透传元数据（如 {"project_id": "...", "phase": "outline"}）
        """
        task_id = task_id or str(uuid.uuid4())
        if coroutine_factory is not None:
            coroutine = coroutine_factory(task_id)
        if coroutine is None:
            raise ValueError("coroutine or coroutine_factory is required")
        task = Task(task_id, coroutine, stream=stream, meta=meta)
        self._tasks[task_id] = task
        try:
            task.start()
        except RuntimeError as e:
            # 没有运行 loop（不应该发生，因为这是从 FastAPI 路由调用的）
            logger.error(f"Failed to start task {task_id}: {e}")
            raise
        return task_id

    def update_meta(self, task_id: str, **changes: Any) -> None:
        """Update durable progress metadata for a running task."""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.meta.update(_safe(changes))
        self._save()

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务对象（含订阅能力）"""
        return self._tasks.get(task_id)

    def find_active_task(self, **meta_match: Any) -> Optional[Task]:
        """Find a pending/running task whose metadata matches every supplied field."""
        for task in self._tasks.values():
            if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                continue
            if all(task.meta.get(key) == value for key, value in meta_match.items()):
                return task
        return None

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态摘要。如果进程已重启且任务不在内存，但状态文件中有，返回降级版。"""
        task = self._tasks.get(task_id)
        if task:
            return {
                "task_id": task.id,
                "status": task.status.value,
                "result": _safe(task.result),
                "error": public_error_for_status(task.status),
                "error_code": public_error_code_for_status(task.status),
                "meta": task.meta,
            }
        # 进程重启兜底：查状态文件
        disk_state = self._disk_state.get(task_id)
        if disk_state:
            return {
                "task_id": disk_state["id"],
                "status": disk_state["status"],
                "result": disk_state.get("result"),
                "error": public_error_for_status(disk_state["status"]),
                "error_code": public_error_code_for_status(disk_state["status"]),
                "meta": disk_state.get("meta", {}),
            }
        return None

    # ─── 落盘相关 ───

    @property
    def _disk_state(self) -> dict[str, dict]:
        """缓存的磁盘状态（启动时加载）。修改时不会自动写盘，调用 _save 才写。"""
        return self._disk_state_cache

    def _load(self):
        """启动时加载：把磁盘上 running/pending 标为 orphaned，completed/failed 保留。"""
        self._disk_state_cache = {}
        try:
            if _STATE_FILE.exists():
                with open(_STATE_FILE, "r", encoding="utf-8") as f:
                    self._disk_state_cache = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load task state file: {e}")
            return

        if not self._disk_state_cache:
            return

        now = datetime.utcnow().isoformat()
        orphaned_count = 0
        for tid, td in self._disk_state_cache.items():
            if td.get("status") in ("running", "pending"):
                td["status"] = "orphaned"
                td["error"] = "Task was interrupted by server restart."
                td["completed_at"] = now
                orphaned_count += 1
                logger.warning(f"Task {tid} marked as orphaned (was running/pending)")
        logger.info(f"Loaded {len(self._disk_state_cache)} tasks from state file ({orphaned_count} orphaned)")
        # 启动时也清一遍（让 TTL 立即生效，不需要等 cleanup_loop）
        cleaned = _filter_expired(self._disk_state_cache)
        if len(cleaned) != len(self._disk_state_cache):
            logger.info(f"Startup cleanup: removed {len(self._disk_state_cache) - len(cleaned)} expired tasks")
            self._disk_state_cache = cleaned
        # 同步写回
        self._save_dict(self._disk_state_cache)

    def _save(self):
        """立即写盘。合并：内存里 RUNNING/COMPLETED/FAILED + 磁盘里已 ORPHANED/COMPLETED/FAILED。"""
        snapshot = dict(self._disk_state_cache)
        for tid, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING):
                snapshot[tid] = task.to_dict()
        # 每次写盘顺手清一遍过期的，文件大小可控
        snapshot = _filter_expired(snapshot)
        self._disk_state_cache = snapshot
        self._save_dict(snapshot)

    def cleanup_expired(self) -> int:
        """主动清理过期任务（COMPLETED/FAILED/ORPHANED 且完成时间超过 TTL）。

        不清理 RUNNING/PENDING（这表示任务还在跑，理论上不可能出现，但稳妥起见）。
        返回清理条数。
        """
        if TASK_TTL_HOURS <= 0:
            return 0
        before = len(self._disk_state_cache)
        self._disk_state_cache = _filter_expired(self._disk_state_cache)
        removed = before - len(self._disk_state_cache)
        if removed:
            self._save_dict(self._disk_state_cache)
            logger.info(f"Cleanup: removed {removed} expired tasks (TTL={TASK_TTL_HOURS}h)")
        return removed

    async def _cleanup_loop(self):
        """后台周期清理任务，每 TASK_CLEANUP_INTERVAL 秒跑一次。"""
        if TASK_TTL_HOURS <= 0:
            return
        logger.info(
            f"Cleanup loop started: TTL={TASK_TTL_HOURS}h, interval={TASK_CLEANUP_INTERVAL}s"
        )
        while True:
            try:
                await asyncio.sleep(TASK_CLEANUP_INTERVAL)
                self.cleanup_expired()
            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.exception(f"Cleanup loop error: {e}")
                # 出错也不要让 loop 死掉，等下一轮
                await asyncio.sleep(60)

    def start_cleanup_loop(self):
        """启动后台清理协程（应从 FastAPI lifespan startup 调用）。"""
        if TASK_TTL_HOURS <= 0:
            logger.info("Cleanup disabled (TASK_TTL_HOURS <= 0)")
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running loop, cannot start cleanup loop")
            return
        self._cleanup_task = loop.create_task(self._cleanup_loop())

    def stop_cleanup_loop(self):
        """停止后台清理协程（从 FastAPI lifespan shutdown 调用）。"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    def _save_dict(self, data: dict):
        try:
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                f.flush()
                try:
                    import os
                    os.fsync(f.fileno())
                except (AttributeError, OSError):
                    pass
        except Exception as e:
            logger.warning(f"Failed to save task state file: {e}")

    def save_all_running_as_orphaned(self):
        """shutdown 钩子调用：把所有仍在运行的 task 标记为 orphaned 并写盘。"""
        any_change = False
        for task in self._tasks.values():
            if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                task.status = TaskStatus.ORPHANED
                task.error = "Task was interrupted by server shutdown."
                task.completed_at = datetime.utcnow()
                # 同步标记到磁盘缓存
                self._disk_state_cache[task.id] = task.to_dict()
                any_change = True
                logger.warning(f"Task {task.id} marked orphaned by shutdown hook")
        if any_change:
            self._save_dict(self._disk_state_cache)


# 全局任务管理器
task_manager = TaskManager()

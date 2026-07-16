import asyncio
import json
import logging
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.worldbuilding import WorldbuildingAgent
from app.core.security import get_current_user
from app.db.session import async_session_maker, get_db
from app.models.domain import Entity, Project
from app.models.schemas import (
    TaskStatus,
    WorldbuildingRequest,
    WorldbuildingResponse,
    WorldbuildingResult,
)
from app.pipeline.compliance import build_rewrite_prompt, scan_result, scan_text
from app.pipeline.task_queue import (
    STREAM_EVENT_DONE,
    STREAM_EVENT_ERROR,
    STREAM_EVENT_STATUS,
    StreamEvent,
    Task,
    task_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["世界观"])


def _sse_format(event: str, data: dict) -> str:
    """格式化为 SSE 文本帧"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _push_status(task_id: str, message: str, level: str = "info") -> None:
    """推一条状态文本给前端（合规提示用）。"""
    task = task_manager.get_task(task_id)
    if task is None:
        return
    # 复用 token 通道，事件名仍是 token，前端按 chunk 累计
    await task.emit_token(f"\n\n> 🔧 {message}\n\n")


async def _run_with_compliance(
    agent: WorldbuildingAgent,
    inputs: dict,
    task_id: str,
    on_token,
) -> dict:
    """生成 + 合规扫描 + 最多 2 次重写的循环。"""
    max_rewrite = 2

    # 首次流式生成
    wb_result = await agent.run_stream(inputs, on_token=on_token)

    for attempt in range(1, max_rewrite + 1):
        issues = scan_result(wb_result)
        if not issues:
            return wb_result

        # 有问题 → 重写
        issue_summary = "、".join(i["term"] for i in issues[:5])
        if len(issues) > 5:
            issue_summary += f"等 {len(issues)} 项"
        await _push_status(
            task_id,
            f"第 {attempt}/{max_rewrite} 轮合规修订：检测到不合规词「{issue_summary}」",
        )

        rewrite_prompt = build_rewrite_prompt(issues)
        if not rewrite_prompt:
            continue

        # 重写不分流（用户不关心过程，只要最终结果干净）
        raw_rewrite = await agent.complete_stream_text(
            rewrite_prompt,
            system=agent._system_prompt(),
            project_id=inputs.get("project_id"),
        )
        try:
            wb_result = agent._parse_json(raw_rewrite)
            wb_result = agent._validate(wb_result)
        except Exception as e:
            logger.warning(f"Rewrite attempt {attempt} parse failed: {e}")
            break

    # 最后再扫一次。如果还有残留，记录日志并强制过滤 - 但保留原 result 不丢用户数据
    issues = scan_result(wb_result)
    if issues:
        logger.warning(
            f"After {max_rewrite} rewrite attempts, worldbuilding still has {len(issues)} compliance issues: "
            f"{[i['term'] for i in issues]}"
        )
        await _push_status(
            task_id,
            f"⚠️ 经过 {max_rewrite} 轮修订后仍残留 {len(issues)} 项敏感词，将保留原始内容等待人工审核",
        )
    return wb_result


@router.post("/{project_id}/worldbuilding", response_model=WorldbuildingResponse)
async def trigger_worldbuilding(
    project_id: UUID,
    request: WorldbuildingRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发世界观生成任务（流式）"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    project_data = {
        "project_id": str(project.id),
        "core_idea": project.core_idea,
        "genre": project.genre or "玄幻",
        "tone_style": project.tone_style or "严肃",
    }

    async def run_generation():
        """异步执行世界观生成 - 使用独立的 db session"""
        async with async_session_maker() as session:
            agent = WorldbuildingAgent()

            def on_token(chunk: str) -> None:
                task = task_manager.get_task(task_id)
                if task is not None:
                    asyncio.create_task(task.emit_token(chunk))

            wb_result = await _run_with_compliance(
                agent,
                {
                    "core_idea": project_data["core_idea"],
                    "genre": project_data["genre"],
                    "tone_style": project_data["tone_style"],
                },
                task_id,
                on_token,
            )

            setting_document = wb_result.get("setting_document", "")
            constraints = wb_result.get("constraints", {"hard": [], "soft": []})
            conflict_seeds = wb_result.get("conflict_seeds", [])

            proj_result = await session.execute(
                select(Project).where(Project.id == UUID(project_data["project_id"]))
            )
            proj = proj_result.scalar_one_or_none()
            if not proj:
                logger.error(f"Project {project_data['project_id']} disappeared")
                return

            for rule in constraints.get("hard", []):
                entity = Entity(
                    project_id=UUID(project_data["project_id"]),
                    type="rule",
                    name=rule[:50],
                    display_name=rule[:100],
                    description=f"世界硬约束：{rule}",
                    data={"rule_type": "hard", "source": "worldbuilding"}
                )
                session.add(entity)

            for seed in conflict_seeds:
                entity = Entity(
                    project_id=UUID(project_data["project_id"]),
                    type="conflict_seed",
                    name=seed.get("name", ""),
                    display_name=seed.get("name", ""),
                    description=seed.get("description", ""),
                    data={
                        "stake": seed.get("stake", ""),
                        "source": "worldbuilding"
                    }
                )
                session.add(entity)

            proj.status = "worldbuilt"
            proj.data = {
                "setting_document": setting_document,
                "constraints": constraints,
                "conflict_seeds": conflict_seeds,
            }

            await session.commit()
            return wb_result

    # 创建后台任务（启用流式）
    task_id = task_manager.create_task(
        run_generation(),
        stream=True,
        meta={
            "project_id": str(project_id),
            "kind": "worldbuilding",
            "phase": "worldbuilding",
        },
    )
    return WorldbuildingResponse(task_id=task_id, status="pending")


@router.get("/{project_id}/worldbuilding", response_model=WorldbuildingResult)
async def get_worldbuilding(
    project_id: UUID,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取世界观结果"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == UUID(current_user_id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    data = project.data or {}
    if not data or not data.get("setting_document"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worldbuilding not generated yet"
        )
    return WorldbuildingResult(
        setting_document=data.get("setting_document", ""),
        constraints=data.get("constraints", {"hard": [], "soft": []}),
        conflict_seeds=data.get("conflict_seeds", [])
    )


async def _task_event_stream(task: Task) -> AsyncIterator[str]:
    """SSE 事件流生成器：把 task 上的事件转成 SSE 帧"""
    queue = task.subscribe()
    try:
        # 立刻发一个 status=running 让前端确认订阅成功
        yield _sse_format(STREAM_EVENT_STATUS, {"status": task.status.value})

        while True:
            try:
                # 设超时，避免永久卡死
                event: StreamEvent = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                # 5 分钟没动静，主动断开
                yield _sse_format(STREAM_EVENT_ERROR, {"error": "Stream timeout"})
                break

            yield _sse_format(event.event, event.data)

            # 终态事件：发完就关流
            if event.event in (STREAM_EVENT_DONE, STREAM_EVENT_ERROR):
                break
    finally:
        task.unsubscribe(queue)


async def _ensure_task_owner(task: Task, current_user_id: str, db: AsyncSession) -> None:
    project_id = task.meta.get("project_id")
    if not project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project = (
        await db.execute(
            select(Project).where(
                Project.id == UUID(project_id),
                Project.user_id == UUID(current_user_id),
            )
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@router.get("/worldbuilding/stream/{task_id}")
async def worldbuilding_stream(
    task_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流：订阅世界观生成任务的实时 token"""
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    await _ensure_task_owner(task, current_user_id, db)

    return StreamingResponse(
        _task_event_stream(task),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 关闭缓冲
            "Connection": "keep-alive",
        },
    )


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(
    task_id: str,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务状态（用于非流式场景的兜底轮询）"""
    status_info = task_manager.get_task_status(task_id)
    if not status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await _ensure_task_owner(task, current_user_id, db)
    return TaskStatus(**status_info)


# ─────────────────────────────────────────────
# 合规预检 API（前端在创建项目 / 生成世界观前调用）
# ─────────────────────────────────────────────
class ComplianceCheckRequest(BaseModel):
    text: str


class ComplianceCheckResponse(BaseModel):
    compliant: bool
    issues: list  # [{ term, category, count }]


@router.post("/compliance/check", response_model=ComplianceCheckResponse)
async def compliance_check(
    body: ComplianceCheckRequest,
    current_user_id: str = Depends(get_current_user),
):
    """扫描输入文本中的真实国家/城市/品牌，返回 issues 列表。

    用于前端在用户提交 core_idea 时给出即时反馈。
    """
    issues = scan_text(body.text)
    return ComplianceCheckResponse(compliant=len(issues) == 0, issues=issues)

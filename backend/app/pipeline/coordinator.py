"""Coordinator 编排器 —— Phase 9 增强版（写→审→重试循环 + 毛刺注入）"""
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.reviewer import ReviewerAgent
from app.agents.writer import WriterAgent
from app.config import settings
from app.models.constraints import RevisionNote, SceneConstraint
from app.services.budget_guard import BudgetGuard
from app.services.metrics_collector import LLMCallMetrics, MetricsCollector
from app.services.pricing import estimate_cost
from app.services.style_analyzer import style_analyzer
from app.utils.tokens import count_tokens, count_tokens_pair

logger = logging.getLogger(__name__)


class Coordinator:
    """
    写作协调器 - 管理写作-审校循环 + 毛刺注入

    流程：
      1. WriterAgent 生成场景正文
      2. ReviewerAgent 审校（含 Phase 9 AI 味检测）
      3. 若有问题 → 注入反馈 → 重写（最多 MAX_REVISION_ATTEMPTS 次）
      4. 全部通过 → StyleAnalyzer.inject_human_roughness() 注入毛刺
      5. 落库
    """

    MAX_REVISION_ATTEMPTS = 3

    def __init__(self):
        self.writer = WriterAgent()
        self.reviewer = ReviewerAgent()

    def get_scene_key(
        self,
        project_id: str,
        chapter_number: int,
        scene_number: int,
    ) -> str:
        return f"{project_id}:{chapter_number}:{scene_number}"

    async def run_writing_flow(
        self,
        constraint: SceneConstraint,
        project_id: str,
        chapter_number: int,
        on_token=None,
        db: Optional[AsyncSession] = None,
        context_snapshot_id: Optional[str] = None,
        call_type: str = "initial",
    ) -> dict:
        """
        执行完整的写作-审校流程。

        Args:
            constraint: 场景约束卡
            project_id: 项目 ID（用于生成 scene_key）
            chapter_number: 章号（用于毛刺注入判断）
            on_token: 流式回调，每收到一段 token 调用一次

        Returns:
            {
                "content": str,          # 最终正文（含毛刺）
                "attempts": int,          # 尝试次数
                "passed": bool,          # 是否通过审校
                "issues": list,           # 最终问题列表
                "revision_count": int,    # 重写次数
            }
        """
        scene_key = self.get_scene_key(
            project_id,
            constraint.chapter_number,
            constraint.scene_number,
        )
        revision_history: list[RevisionNote] = []
        final_content = ""
        final_issues: list = []
        final_resolved_foreshadowing_ids: list[str] = []
        final_entity_changes: list[dict] = []
        revision_count = 0
        collector = MetricsCollector(db) if db is not None else None
        guard = BudgetGuard(collector)

        for attempt in range(1, self.MAX_REVISION_ATTEMPTS + 1):
            logger.info(
                "writing flow: scene=%s attempt=%d/%d",
                scene_key,
                attempt,
                self.MAX_REVISION_ATTEMPTS,
            )

            # ── 1. 写作 ────────────────────────────────────
            revision_notes_for_this_attempt = [
                {
                    "attempt": note.attempt,
                    "critical_issues": note.critical_issues,
                    "partial_content": note.partial_content,
                }
                for note in revision_history
            ]
            prompt_for_estimate = self.writer._build_prompt(
                constraint, revision_notes_for_this_attempt
            )
            estimated_cost = estimate_cost(
                settings.llm_model,
                count_tokens(prompt_for_estimate, settings.llm_model),
                count_tokens("汉" * constraint.word_budget, settings.llm_model),
            )
            await guard.check_call_budget(project_id, chapter_number, estimated_cost)

            writer_started = time.perf_counter()
            try:
                if on_token:
                    async def token_callback(chunk: str):
                        on_token(chunk)

                    content = await self.writer.write_scene_stream(
                        constraint,
                        revision_notes=revision_notes_for_this_attempt,
                        on_token=token_callback,
                    )
                else:
                    content = await self.writer.write_scene(
                        constraint,
                        revision_notes=revision_notes_for_this_attempt,
                    )
            except Exception as exc:
                if collector is not None:
                    await self._record_call(
                        collector, "writer", project_id, chapter_number, scene_key,
                        constraint.model_dump_json(), "", writer_started, attempt - 1,
                        call_type if attempt == 1 else "retry", context_snapshot_id, exc,
                    )
                raise
            if collector is not None:
                await self._record_call(
                    collector, "writer", project_id, chapter_number, scene_key,
                    constraint.model_dump_json(), content, writer_started, attempt - 1,
                    call_type if attempt == 1 else "retry", context_snapshot_id,
                )

            final_content = content

            # ── 2. 审校 ────────────────────────────────────
            review_started = time.perf_counter()
            review_result = await self.reviewer.review(content=content, constraint=constraint)
            if collector is not None:
                review_error = RuntimeError(review_result.get("error")) if review_result.get("status") == "error" else None
                await self._record_call(
                    collector, "reviewer", project_id, chapter_number, scene_key,
                    content, str(review_result), review_started, 0, "initial",
                    context_snapshot_id, review_error,
                )

            issues = review_result.get("issues", [])
            critical = [i for i in issues if i.get("severity") == "critical"]
            major = [i for i in issues if i.get("severity") == "major"]
            final_issues = issues
            final_resolved_foreshadowing_ids = review_result.get(
                "resolved_foreshadowing_ids", []
            )
            final_entity_changes = review_result.get("entity_changes", [])

            # 记录审校历史
            note = RevisionNote(
                attempt=attempt,
                critical_issues=issues,
            )
            revision_history.append(note)

            # ── 3. 判断：通过 or 重写 ────────────────────────
            if review_result.get("status") == "pass":
                logger.info("writing flow: scene=%s passed after %d attempts", scene_key, attempt)
                break

            if len(revision_history) >= self.MAX_REVISION_ATTEMPTS:
                logger.warning(
                    "writing flow: scene=%s failed after %d attempts, issues=%s",
                    scene_key,
                    attempt,
                    [i.get("name") for i in critical + major],
                )
                break

            revision_count += 1

        # ── 4. 毛刺注入（通过后执行） ─────────────────────
        inject_needed = (
            chapter_number % 5 == 0 or revision_count > 0
        )
        if inject_needed and final_content:
            try:
                final_content = await style_analyzer.inject_human_roughness(
                    final_content,
                    chapter_number,
                    force=(revision_count > 0),
                    project_id=project_id,
                    context_snapshot_id=context_snapshot_id,
                )
                logger.debug("injected roughness: scene=%s", scene_key)
            except Exception as e:
                logger.warning("inject_human_roughness failed: %s", e)

        return {
            "content": final_content,
            "attempts": len(revision_history),
            "passed": review_result.get("status") == "pass",
            "issues": final_issues,
            "revision_count": revision_count,
            "resolved_foreshadowing_ids": (
                final_resolved_foreshadowing_ids
                if review_result.get("status") == "pass"
                else []
            ),
            "entity_changes": final_entity_changes if review_result.get("status") == "pass" else [],
        }

    async def _record_call(
        self,
        collector: MetricsCollector,
        agent: str,
        project_id: str,
        chapter_number: int,
        event_id: str,
        prompt: str,
        output: str,
        started: float,
        retry_count: int,
        call_type: str,
        context_snapshot_id: Optional[str],
        error: Optional[Exception] = None,
    ) -> None:
        prompt_tokens, completion_tokens = count_tokens_pair(prompt, output, settings.llm_model)
        await collector.record_call(
            LLMCallMetrics(
                timestamp=datetime.utcnow(),
                agent=agent,
                chapter_number=chapter_number,
                event_id=event_id,
                model=settings.llm_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=(time.perf_counter() - started) * 1000,
                retry_count=retry_count,
                cost_estimate=estimate_cost(settings.llm_model, prompt_tokens, completion_tokens),
                success=error is None,
                error_type=type(error).__name__ if error else None,
                project_id=project_id,
                call_type=call_type,
                context_snapshot_id=context_snapshot_id,
            )
        )

    def inject_feedback(
        self,
        constraint: SceneConstraint,
        critical_issues: list[dict],
        previous_content: str,
    ) -> SceneConstraint:
        """将审校反馈注入约束卡，供下次重写使用"""
        feedback_parts = ["上一次生成有以下问题需要修复："]
        for i, issue in enumerate(critical_issues, 1):
            feedback_parts.append(
                f"{i}. {issue.get('category', 'unknown').upper()}: {issue.get('description', '')}"
            )
            if issue.get("suggestion"):
                feedback_parts.append(f"   建议：{issue['suggestion']}")

        feedback_parts.append(f"\n上一次内容片段：\n{previous_content[:500]}...\n请避免上述问题。")

        new_directives = list(constraint.prose_directives) if constraint.prose_directives else []
        new_directives.append(f"【审校反馈】{' '.join(feedback_parts)}")

        new_forbidden = list(constraint.forbidden_elements) if constraint.forbidden_elements else []
        for issue in critical_issues:
            if issue.get("forbidden_pattern"):
                new_forbidden.append(issue["forbidden_pattern"])

        return constraint.model_copy(
            update={"prose_directives": new_directives, "forbidden_elements": new_forbidden}
        )


# 全局实例
coordinator = Coordinator()

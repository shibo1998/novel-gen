"""Whole-chapter drafting with scene markers for storage compatibility."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from app.agents.template_environment import create_template_environment
from app.llm.client import collect_stream_text, get_llm_client
from app.models.constraints import SceneConstraint
from app.services.word_budget import CHAPTER_WORD_BUDGET

SCENE_MARKER_PATTERN = re.compile(r"<!--\s*SCENE:(\d+)\s*-->", re.IGNORECASE)
CHAPTER_BUDGET_MIN_RATIO = 0.92
CHAPTER_BUDGET_MAX_RATIO = 1.08


class ChapterSegmentationError(ValueError):
    """Raised when a chapter draft cannot be mapped to its planned scenes."""


def chapter_budget_range(target: int = CHAPTER_WORD_BUDGET) -> tuple[int, int]:
    return round(target * CHAPTER_BUDGET_MIN_RATIO), round(target * CHAPTER_BUDGET_MAX_RATIO)


def count_chapter_characters(content: str) -> int:
    """Count prose characters while excluding markers, headings, and whitespace."""
    without_markers = SCENE_MARKER_PATTERN.sub("", content)
    without_headings = re.sub(r"(?m)^#{1,6}\s+.*$", "", without_markers)
    return len(re.sub(r"\s+", "", without_headings))


def split_chapter_draft(
    content: str,
    expected_scene_numbers: Iterable[int],
) -> dict[int, str]:
    """Remove scene markers and return ordered, non-empty scene prose."""
    expected = list(expected_scene_numbers)
    matches = list(SCENE_MARKER_PATTERN.finditer(content))
    actual = [int(match.group(1)) for match in matches]
    if actual != expected:
        raise ChapterSegmentationError(
            f"scene markers must be exactly {expected}, received {actual}"
        )

    prefix = content[: matches[0].start()].strip() if matches else ""
    segments: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[match.end() : end].strip()
        if index == 0 and prefix:
            body = f"{prefix}\n\n{body}".strip()
        if not body or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", body):
            raise ChapterSegmentationError(f"scene {actual[index]} has no prose")
        segments[actual[index]] = body
    return segments


def _unique_dicts(items: Iterable[dict[str, Any]], key: str | None = None) -> list[dict]:
    seen: set[str] = set()
    result = []
    for item in items:
        identity = str(item.get(key)) if key and item.get(key) is not None else json.dumps(
            item, ensure_ascii=False, sort_keys=True, default=str
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def merge_chapter_context(constraints: list[SceneConstraint]) -> dict[str, Any]:
    """Deduplicate context retrieved independently for each planned scene."""
    bible: dict[str, Any] = {}
    previous: list[dict] = []
    foreshadowings: list[dict] = []
    memories: list[dict] = []
    plot_threads: list[dict] = []
    summaries: list[str] = []
    world_rules: list[str] = []
    styles: list[dict] = []

    for constraint in constraints:
        bible.update(constraint.injected_bible or {})
        previous.extend(constraint.injected_previous or [])
        foreshadowings.extend(constraint.injected_foreshadowings or [])
        memories.extend(constraint.injected_memories or [])
        plot_threads.extend(constraint.injected_plot_threads or [])
        if constraint.injected_chapter_summaries:
            summaries.append(constraint.injected_chapter_summaries)
        if constraint.injected_world_rules:
            world_rules.append(constraint.injected_world_rules)
        if constraint.injected_style:
            styles.append(constraint.injected_style)

    return {
        "bible": bible,
        "previous": _unique_dicts(previous),
        "foreshadowings": _unique_dicts(foreshadowings, "id"),
        "memories": _unique_dicts(memories, "id"),
        "plot_threads": _unique_dicts(plot_threads, "id"),
        "chapter_summaries": list(dict.fromkeys(summaries)),
        "world_rules": list(dict.fromkeys(world_rules)),
        "styles": _unique_dicts(styles),
    }


def _chapter_system_prompt() -> str:
    return """你是正在连载中文长篇小说的作者。
一次写完当前整章，让人物状态、叙述声音和事件因果连续推进。
以章级委托中的事实为边界，叙述固定在各场景指定 POV 当下可感知和理解的范围内。
只输出约定格式的 Markdown 正文和场景边界标记。"""


class ChapterWriterAgent:
    """Generate or repair a complete chapter in one model call."""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = create_template_environment()

    def build_prompt(
        self,
        *,
        chapter_number: int,
        chapter_title: str,
        constraints: list[SceneConstraint],
        target_chars: int = CHAPTER_WORD_BUDGET,
        previous_content: str = "",
        issues: list[dict] | None = None,
    ) -> str:
        minimum, maximum = chapter_budget_range(target_chars)
        template = self.jinja.get_template("chapter_writer.j2")
        return template.render(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            constraints=constraints,
            context=merge_chapter_context(constraints),
            target_chars=target_chars,
            minimum_chars=minimum,
            maximum_chars=maximum,
            previous_content=previous_content,
            issues=issues or [],
        )

    async def write_chapter(
        self,
        *,
        chapter_number: int,
        chapter_title: str,
        constraints: list[SceneConstraint],
        target_chars: int = CHAPTER_WORD_BUDGET,
        previous_content: str = "",
        issues: list[dict] | None = None,
    ) -> str:
        prompt = self.build_prompt(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            constraints=constraints,
            target_chars=target_chars,
            previous_content=previous_content,
            issues=issues,
        )
        return await collect_stream_text(self.llm, prompt, system=_chapter_system_prompt())

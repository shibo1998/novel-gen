import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

from jinja2 import Environment, FileSystemLoader

from app.agents.style_rules import load_style_rules
from app.config import settings
from app.llm.client import get_llm_client
from app.llm.exceptions import LLMError
from app.services.llm_observability import LLMCallObserver


def _bracket_unbalanced(s: str) -> bool:
    """粗略判断 JSON 括号/引号是否配平（截断检测用，忽略字符串转义复杂度）。"""
    in_string = False
    escape = False
    counts = {"{": 0, "}": 0, "[": 0, "]": 0}
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in counts:
            counts[ch] += 1
    return counts["{"] != counts["}"] or counts["["] != counts["]"] or in_string


def _build_style_constraint() -> str:
    """从 chinese_style_rules.json 生成全局写作约束片段（注入 System Prompt）"""
    rules = load_style_rules()
    vocab = rules.get("vocabulary_banlist", {})
    hard = "、".join(vocab.get("hard_ban", [])[:12])
    soft = "、".join(vocab.get("soft_ban", [])[:12])

    return f"""
## 全局写作约束（Phase 9 自动注入，不可覆盖）

### 绝对禁止使用的句式/词汇
{hard}

### 严格限制的词汇（减少 90%）
{soft}

### 破折号限制
全文"——"不超过 3 处。能用句号或逗号的地方，不用破折号。

### 对话标签限制
禁止"淡淡道/冷冷道/沉声道"。用动作节拍替代一切对话标签。
"""


class BaseAgent(ABC):
    """Agent 基类，提供模板渲染和 LLM 调用能力"""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))
        self._style_constraint = _build_style_constraint()

    @property
    @abstractmethod
    def template_name(self) -> str:
        """返回模板文件名"""
        pass

    @abstractmethod
    def output_schema(self) -> dict:
        """返回 JSON Schema 用于 structured output"""
        pass

    async def complete_stream_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        *,
        project_id: str | None = None,
        chapter_number: int | None = None,
    ) -> str:
        """流式调用 LLM，累积全部 token，返回完整文本。"""
        await LLMCallObserver.check_budget(project_id, chapter_number, prompt=prompt)
        started = time.perf_counter()
        accumulated: list[str] = []
        try:
            async for chunk in self.llm.complete_stream(prompt, system=system):
                accumulated.append(chunk)
        except Exception as exc:
            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=prompt,
                output="".join(accumulated),
                started=started,
                chapter_number=chapter_number,
                error=exc,
            )
            raise
        output = "".join(accumulated)
        await LLMCallObserver.record(
            project_id=project_id,
            agent=self.__class__.__name__,
            prompt=prompt,
            output=output,
            started=started,
            chapter_number=chapter_number,
        )
        return output

    async def run(
        self,
        inputs: dict,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """执行 Agent，底层通过流式请求收集并验证结构化结果。"""
        template = self.jinja.get_template(self.template_name)
        prompt = template.render(**inputs)
        return await self._run_structured_stream(prompt, inputs, on_progress)

    async def run_stream(
        self,
        inputs: dict,
        on_token: Callable[[str], None],
    ) -> dict:
        """执行 Agent（流式）。"""
        template = self.jinja.get_template(self.template_name)
        prompt = template.render(**inputs)
        return await self._run_structured_stream(prompt, inputs, on_token)

    async def _run_structured_stream(
        self,
        prompt: str,
        inputs: dict,
        on_chunk: Optional[Callable[[str], None]],
    ) -> dict:
        """Run a structured request and retry a truncated JSON response as a new stream."""
        system = self._system_prompt()
        project_id = str(inputs["project_id"]) if inputs.get("project_id") else None
        chapter_number = inputs.get("chapter_number")
        max_attempts = max(1, settings.llm_max_retries)

        for attempt in range(max_attempts):
            attempt_prompt = (
                prompt
                if attempt == 0
                else self._structured_retry_prompt(prompt, attempt + 1)
            )
            await LLMCallObserver.check_budget(
                project_id,
                chapter_number,
                prompt=attempt_prompt,
            )
            started = time.perf_counter()
            accumulated: list[str] = []
            try:
                async for chunk in self.llm.complete_stream(
                    attempt_prompt,
                    system=system,
                ):
                    accumulated.append(chunk)
                    if on_chunk is not None:
                        try:
                            callback_result = on_chunk(chunk)
                            if asyncio.iscoroutine(callback_result):
                                await callback_result
                        except Exception:
                            pass
            except Exception as exc:
                await LLMCallObserver.record(
                    project_id=project_id,
                    agent=self.__class__.__name__,
                    prompt=attempt_prompt,
                    output="".join(accumulated),
                    started=started,
                    chapter_number=chapter_number,
                    error=exc,
                )
                raise

            raw = "".join(accumulated)
            try:
                result = self._validate(self._parse_json(raw))
            except Exception as exc:
                await LLMCallObserver.record(
                    project_id=project_id,
                    agent=self.__class__.__name__,
                    prompt=attempt_prompt,
                    output=raw,
                    started=started,
                    chapter_number=chapter_number,
                    error=exc,
                )
                if attempt + 1 < max_attempts and self._is_retryable_structured_error(exc):
                    continue
                raise

            await LLMCallObserver.record(
                project_id=project_id,
                agent=self.__class__.__name__,
                prompt=attempt_prompt,
                output=raw,
                started=started,
                chapter_number=chapter_number,
            )
            return result

        raise LLMError("Structured stream exhausted without a valid JSON result")

    @staticmethod
    def _is_retryable_structured_error(exc: Exception) -> bool:
        return isinstance(exc, (LLMError, ValueError, TypeError, KeyError))

    @staticmethod
    def _structured_retry_prompt(prompt: str, attempt_number: int) -> str:
        return f"""{prompt}

## 结构化输出恢复（第 {attempt_number} 次完整重试）
上一次响应被截断、JSON 语法无效或未通过结构校验。请从头重新输出完整 JSON，不要续写残片。
保持要求的字段和结构，但压缩长段说明、列表和重复内容；整个 JSON 控制在 2500 个汉字以内。
字符串中的换行必须写成转义序列 \\n，字符串内部的双引号必须转义，字段之间不得遗漏逗号。
不要输出 Markdown 代码围栏或 JSON 之外的文字。"""

    def _parse_json(self, raw: str) -> dict:
        """解析 JSON，处理 markdown 代码块与可能的截断。"""
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

            tail = raw[-200:] if len(raw) > 200 else raw
            looks_like_json = raw.lstrip().startswith(("{", "["))
            looks_truncated = looks_like_json and (
                not tail.rstrip().endswith(("}", "]"))
                or _bracket_unbalanced(raw)
            )
            hint = (
                "输出疑似被 max_tokens 截断（末尾 } / ] 缺失或括号不平衡）。"
                if looks_truncated
                else "JSON 语法错误，请检查 prompt 或模型输出格式。"
            )
            raise LLMError(f"{hint} original error: {e}; raw_len={len(raw)}") from e

    def _system_prompt(self) -> str:
        """
        子类可重写以自定义 base prompt。
        全局风格约束自动追加到末尾。
        """
        base = "你是一位专业的小说策划助手。输出必须是合法的JSON格式，不要包含任何JSON之外的文字。"
        return base + "\n" + self._style_constraint

    def _validate(self, data: dict) -> dict:
        """子类可重写以添加验证逻辑"""
        return data

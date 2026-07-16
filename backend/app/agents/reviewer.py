"""审校Agent —— Phase 9 增强版（中文去味检测）"""
import json
import re
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from app.agents.style_rules import load_style_rules
from app.llm.client import collect_stream_text, get_llm_client
from app.models.constraints import SceneConstraint


class ReviewerAgent:
    """审校Agent - 包含 AI 味检测（Phase 9 Layer 2）"""

    def __init__(self):
        self.llm = get_llm_client()
        self.jinja = Environment(loader=FileSystemLoader("app/prompts"))

    async def review(
        self,
        content: str,
        constraint: SceneConstraint,
        bible: Optional[dict] = None,
        previous_summaries: Optional[list] = None,
    ) -> dict:
        """完整审校流程：
        1. 原有事实/连贯性审校（LLM）
        2. AI 味检测（规则扫描，新增）
        3. 风格一致性检查
        """
        # 第一步：原有审校
        base_result = await self._base_review(content, constraint, bible, previous_summaries)

        # 第二步：AI 味检测
        ai_smell_issues = self._detect_ai_patterns(content)

        if base_result.get("status") == "error":
            return {
                "status": "error",
                "issues": ai_smell_issues,
                "error": base_result.get("error", "Reviewer unavailable"),
                "resolved_foreshadowing_ids": [],
                "entity_changes": [],
            }

        # 第三步：合并
        all_issues = base_result.get("issues", []) + ai_smell_issues
        resolved_foreshadowing_ids = self._validated_resolution_ids(base_result, constraint)
        entity_changes = self._validated_entity_changes(base_result, constraint)

        critical = [i for i in all_issues if i.get("severity") == "critical"]
        major = [i for i in all_issues if i.get("severity") == "major"]

        if critical:
            return {
                "status": "needs_rewrite",
                "issues": all_issues,
                "rewrite_hints": self._build_rewrite_hints(critical + major),
                "resolved_foreshadowing_ids": [],
                "entity_changes": [],
            }

        if len(major) >= 3:
            return {
                "status": "needs_rewrite",
                "issues": all_issues,
                "rewrite_hints": self._build_rewrite_hints(major),
                "resolved_foreshadowing_ids": [],
                "entity_changes": [],
            }

        return {
            "status": "pass",
            "issues": all_issues,
            "resolved_foreshadowing_ids": resolved_foreshadowing_ids,
            "entity_changes": entity_changes,
        }

    @staticmethod
    def _validated_resolution_ids(result: dict, constraint: SceneConstraint) -> list[str]:
        """Only accept resolution IDs that were injected into this scene's context."""
        allowed = {
            str(item.get("id"))
            for item in (constraint.injected_foreshadowings or [])
            if item.get("id")
        }
        requested = result.get("resolved_foreshadowing_ids", [])
        if not isinstance(requested, list):
            return []
        return list(dict.fromkeys(str(item) for item in requested if str(item) in allowed))

    @staticmethod
    def _validated_entity_changes(result: dict, constraint: SceneConstraint) -> list[dict]:
        allowed = set((constraint.injected_bible or {}).keys())
        requested = result.get("entity_changes", [])
        if not isinstance(requested, list):
            return []
        validated: list[dict] = []
        seen: set[str] = set()
        for item in requested[:20]:
            if not isinstance(item, dict):
                continue
            entity_name = item.get("entity_name")
            updates = item.get("updates")
            if (
                not isinstance(entity_name, str)
                or entity_name not in allowed
                or entity_name in seen
                or not isinstance(updates, dict)
                or not updates
            ):
                continue
            clean_updates = {
                key: value
                for key, value in updates.items()
                if isinstance(key, str) and key and not key.startswith("__")
            }
            if not clean_updates:
                continue
            validated.append(
                {
                    "entity_name": entity_name,
                    "updates": clean_updates,
                    "summary": str(item.get("summary") or "正文事件更新")[:500],
                }
            )
            seen.add(entity_name)
        return validated

    async def _base_review(
        self,
        content: str,
        constraint: SceneConstraint,
        bible: Optional[dict],
        previous_summaries: Optional[list],
    ) -> dict:
        """原有事实/连贯性审校"""
        template = self.jinja.get_template("reviewer.j2")
        prompt = template.render(
            content=content,
            chapter_number=constraint.chapter_number,
            scene_number=constraint.scene_number,
            constraint_card=constraint,
            bible=bible or constraint.injected_bible or {},
            previous_summaries=previous_summaries or constraint.injected_previous or [],
        )
        system = "你是一位专业审校员。严格检查，但不要过度挑剔minor问题。只报告真正影响阅读的问题。"

        try:
            raw = await collect_stream_text(self.llm, prompt, system=system)
            return self._parse_json(raw)
        except Exception as exc:
            return {"status": "error", "issues": [], "error": str(exc)}

    def _detect_ai_patterns(self, content: str) -> list[dict]:
        """
        扫描全文，返回所有命中的 AI 味问题列表。
        每个问题包含：id, name, severity, count, message, locations（上下文片段）
        """
        rules = load_style_rules()
        issues = []
        char_count = max(1, len(content.replace("\n", "").replace(" ", "")))

        # ── Hard Ban 检测 ─────────────────────────────────────
        for rule in rules["hard_ban_patterns"]["rules"]:
            pattern = rule["pattern"]
            matches = list(re.finditer(pattern, content))
            # threshold=0 → 1 个都不允许；threshold=1 → 超过 1 个才报
            if len(matches) > rule["threshold"]:
                issues.append({
                    "id": rule["id"],
                    "name": rule["name"],
                    "severity": "critical",
                    "count": len(matches),
                    "message": rule["message"],
                    "locations": [self._ctx(content, m) for m in matches[:5]],
                })

        # ── Soft Ban 检测 ─────────────────────────────────────
        for rule in rules["soft_ban_patterns"]["rules"]:
            if "pattern" not in rule:
                continue
            matches = list(re.finditer(rule["pattern"], content))
            threshold = rule.get("threshold", 0)
            if len(matches) > threshold:
                issues.append({
                    "id": rule["id"],
                    "name": rule["name"],
                    "severity": "major",
                    "count": len(matches),
                    "message": rule["message"],
                    "locations": [self._ctx(content, m) for m in matches[:5]],
                })

        # ── 对话标签比例 ─────────────────────────────────────
        dialogue_lines = re.findall(r"[「『\"'].+?[」』\"']", content)
        tag_count = len(re.findall(
            r"(?:说|道|问|答|喊|叫|吼|骂|嚷|呢喃|低语|耳语|嘀咕|嘟囔)[，。；：\n]",
            content,
        ))
        if dialogue_lines and tag_count / len(dialogue_lines) > 0.15:
            issues.append({
                "id": "DIALOGUE_TAG_RATE",
                "name": "对话标签比例",
                "severity": "major",
                "count": round(tag_count / len(dialogue_lines), 2),
                "message": f"对话标签比例 {tag_count/len(dialogue_lines):.0%}，超过 15%",
            })

        # ── 破折号密度 ────────────────────────────────────────
        em_dash_count = content.count("——")
        density = em_dash_count / (char_count / 1000)
        if density > 1:
            issues.append({
                "id": "EM_DASH_OVERUSE",
                "name": "中文破折号密度",
                "severity": "major",
                "count": round(density, 1),
                "message": f"破折号密度 {density:.1f}/千字，超过阈值 1/千字",
            })

        # ── 成语密度 ─────────────────────────────────────────
        chengyu_matches = re.findall(r"[\u4e00-\u9fff]{4}(?=[，。；：！？\n])", content)
        density = len(chengyu_matches) / (char_count / 500)
        if density > 3:
            issues.append({
                "id": "CHENGYU_DENSITY",
                "name": "成语密度",
                "severity": "major",
                "count": round(density, 1),
                "message": f"成语密度 {density:.1f}/500字，超过阈值 3/500字",
            })

        # ── 句式多样性 ───────────────────────────────────────
        sentences = re.split(r"[。！？\n]", content)
        lengths = [len(s) for s in sentences if 3 < len(s) < 200]
        if lengths:
            mean_len = sum(lengths) / len(lengths)
            variance = sum((length - mean_len) ** 2 for length in lengths) / len(lengths)
            std = variance ** 0.5
            if std < 5:
                issues.append({
                    "id": "SENTENCE_VARIANCE",
                    "name": "句式多样性",
                    "severity": "minor",
                    "count": round(std, 1),
                    "message": f"句子长度标准差 {std:.1f}，过于均匀",
                })

        return issues

    def _ctx(self, content: str, match: re.Match, width: int = 30) -> str:
        """提取匹配位置的上下文"""
        start = max(0, match.start() - width)
        end = min(len(content), match.end() + width)
        return content[start:end].replace("\n", " ")

    def _build_rewrite_hints(self, issues: list[dict]) -> str:
        """将检测到的问题转化为 Writer Agent 能理解的重写指令"""
        hints = ["## 重写指令：以下 AI 写作特征必须修复\n"]
        for issue in issues:
            name = issue.get("name") or issue.get("category") or issue.get("id") or "未分类问题"
            message = (
                issue.get("message")
                or issue.get("description")
                or issue.get("suggestion")
                or "请按审校要求修正"
            )
            hints.append(f"- [{issue.get('severity', 'major')}] {name}：{message}")
            if issue.get("suggestion") and issue.get("suggestion") != message:
                hints.append(f"  建议：{issue['suggestion']}")
            if issue.get("locations"):
                hints.append("  违规片段：")
                for loc in issue["locations"][:2]:
                    hints.append(f"  「...{loc}...」")
        hints.append("\n请重写整个段落。不要修补——重新生成。")
        return "\n".join(hints)

    def _parse_json(self, raw: str) -> dict:
        """解析 JSON，处理 markdown 代码块"""
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                result = json.loads(match.group(0))
            else:
                return {"status": "error", "issues": [], "error": "Reviewer returned invalid JSON"}

        if "status" not in result and "passed" in result:
            result["status"] = "pass" if result["passed"] else "needs_rewrite"
        return result

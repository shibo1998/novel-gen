"""Offline prompt contracts plus opt-in external-model acceptance tests."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from app.agents.writer import WriterAgent, _build_style_system
from app.models.constraints import SceneConstraint
from tests.golden_test_cases import GOLDEN_TEST_CASES

BASELINE_PATH = Path(__file__).parent / "baselines" / "prompt_regression_v1.json"


def _constraint(case: dict) -> SceneConstraint:
    event = case["event"]
    return SceneConstraint(
        chapter_number=15,
        scene_number=1,
        scene_title=case["name"],
        narrative_goal=event["consequence"],
        scene_function="turning_point",
        pov_character=event["pov"],
        characters_present=list(dict.fromkeys([event["actor"], event["pov"]])),
        character_emotional_states={event["actor"]: event["internal_state"]},
        opening_emotion=event["internal_state"],
        closing_emotion=event["tone"],
        emotional_beats=[event["trigger"], event["action"], event["result"]],
        reader_should_know=[event["result"]],
        reader_should_not_know=[],
        reader_experience_goal="前三段紧张，中段升级，结尾产生继续阅读的冲动",
        prose_directives=[f"保持{event['tone']}语气"],
        forbidden_elements=case["expected_patterns"].get("must_not_contain", []),
        word_budget=max(500, min(3000, event["estimated_words"])),
        injected_bible={event["actor"]: {"internal_state": event["internal_state"]}},
        injected_previous=[{"chapter": 14, "scene": 2, "summary": event["trigger"]}],
        injected_memories=[{"chapter": 3, "summary": "月圆时左手伤痕发烫"}],
    )


def _output_failures(output: str, case: dict) -> list[str]:
    failures = []
    for pattern in case["expected_patterns"].get("must_not_contain", []):
        if re.search(pattern, output):
            failures.append(f"forbidden pattern: {pattern}")
    checks = case["expected_patterns"].get("structural_checks", {})
    if "em_dash_count" in checks:
        maximum = int(re.sub(r"\D", "", checks["em_dash_count"]))
        if output.count("——") > maximum:
            failures.append(f"em dash count exceeds {maximum}")
    if "dialogue_ratio" in checks:
        quoted = re.findall(r'["「『](.*?)["」』]', output, re.DOTALL)
        ratio = sum(len(value) for value in quoted) / max(len(output), 1)
        threshold = float(re.sub(r"[^0-9.]", "", checks["dialogue_ratio"]))
        if checks["dialogue_ratio"].startswith(">") and ratio <= threshold:
            failures.append(f"dialogue ratio {ratio:.1%} <= {threshold:.1%}")
        if checks["dialogue_ratio"].startswith("<") and ratio >= threshold:
            failures.append(f"dialogue ratio {ratio:.1%} >= {threshold:.1%}")
    return failures


def test_prompt_baseline_contract_is_persisted_and_satisfied():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    prompt = WriterAgent()._build_prompt(_constraint(GOLDEN_TEST_CASES[0]))
    system = _build_style_system()

    assert baseline["schema_version"] == 4
    for section in baseline["required_sections"]:
        assert section in prompt
    for phrase in baseline["system_required_phrases"]:
        assert phrase in system
    assert "{{" not in prompt and "{%" not in prompt


@pytest.mark.parametrize("case", GOLDEN_TEST_CASES, ids=lambda case: case["name"])
def test_every_golden_case_renders_real_writer_prompt(case):
    prompt = WriterAgent()._build_prompt(_constraint(case))
    event = case["event"]

    assert event["trigger"] in prompt
    assert event["action"] in prompt
    assert event["result"] in prompt
    assert "前三段紧张，中段升级" in prompt
    assert "触发→感知→动作" in prompt


def test_writer_prompt_includes_a_bounded_word_budget_range():
    constraint = _constraint(GOLDEN_TEST_CASES[0])
    constraint.word_budget = 1200

    prompt = WriterAgent()._build_prompt(constraint)

    assert "目标字数：1200字" in prompt
    assert "合理范围：1080-1320字" in prompt
    assert "不得超过上限" in prompt


def test_writer_prompt_prefers_colloquial_web_fiction_without_mechanical_quotas():
    prompt = WriterAgent()._build_prompt(_constraint(GOLDEN_TEST_CASES[0]))

    assert "网文口语感" in prompt
    assert "对白允许不完整" in prompt
    assert "精确数字只有" in prompt
    assert "50% 的段落结尾" not in prompt


@pytest.mark.parametrize(
    ("scene_function", "required_phrase"),
    [
        ("establishing", "不做静态导览"),
        ("progression", "局势必须发生变化"),
        ("turning_point", "不可逆转折"),
        ("resolution", "写出后果"),
    ],
)
def test_writer_prompt_adapts_to_scene_function(scene_function, required_phrase):
    constraint = _constraint(GOLDEN_TEST_CASES[0])
    constraint.scene_function = scene_function

    prompt = WriterAgent()._build_prompt(constraint)

    assert required_phrase in prompt


def test_writer_template_loads_outside_backend_working_directory(monkeypatch):
    constraint = _constraint(GOLDEN_TEST_CASES[0])
    monkeypatch.chdir(Path(__file__).parents[2])

    prompt = WriterAgent()._build_prompt(constraint)

    assert constraint.narrative_goal in prompt
    assert "长期记忆检索" in prompt
    assert "月圆时左手伤痕发烫" in prompt


def test_output_contract_detector_rejects_known_regressions():
    case = GOLDEN_TEST_CASES[0]
    bad = "只见剑光掠过。林远眼中闪过怒意——他冲了上去——结局已定。"
    good = "剑光贴着林远的耳廓削过。他矮身踏进玄明怀中，左掌抵住对方肋下。"

    assert _output_failures(bad, case)
    assert _output_failures(good, case) == []


@pytest.mark.external_llm
@pytest.mark.skipif(
    os.getenv("RUN_LLM_ACCEPTANCE") != "1",
    reason="Set RUN_LLM_ACCEPTANCE=1 to run paid external-model acceptance tests",
)
@pytest.mark.parametrize("case", GOLDEN_TEST_CASES, ids=lambda case: case["name"])
async def test_external_writer_output_meets_golden_contract(case):
    output = await WriterAgent().write_scene(_constraint(case))
    assert _output_failures(output, case) == []

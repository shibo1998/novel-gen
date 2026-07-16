"""Shared loader for the Chinese prose style rules."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_style_rules() -> dict:
    rules_path = Path(__file__).parent.parent / "config" / "chinese_style_rules.json"
    try:
        with rules_path.open(encoding="utf-8") as rules_file:
            return json.load(rules_file)
    except FileNotFoundError:
        return {"vocabulary_banlist": {"hard_ban": [], "soft_ban": []}}

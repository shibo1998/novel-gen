"""Jinja environment rooted at the packaged prompt directory."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def create_template_environment() -> Environment:
    return Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

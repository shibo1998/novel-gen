from pathlib import Path

from app.agents.template_environment import create_template_environment


def test_packaged_templates_load_outside_backend_working_directory(monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[2])
    environment = create_template_environment()

    for template_name in (
        "chapter.j2",
        "character_dialogue.j2",
        "outline_replan.j2",
        "reviewer.j2",
        "writer.j2",
    ):
        assert environment.get_template(template_name).name == template_name

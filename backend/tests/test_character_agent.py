from app.agents.character import CharacterAgent
from app.schemas.character import CharacterProfile


def test_character_profile_default_factory_creates_independent_profiles():
    first = CharacterProfile()
    second = CharacterProfile()
    first.speech_profile.signature_patterns.append("沉默")

    assert second.speech_profile.signature_patterns == []


def test_character_agent_parses_fenced_json():
    parsed = CharacterAgent._parse('```json\n{"response": "好。"}\n```')
    assert parsed["response"] == "好。"

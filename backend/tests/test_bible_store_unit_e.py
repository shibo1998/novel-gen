from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.memory.bible_store import BibleStore


def _characters_result(characters):
    result = MagicMock()
    result.scalars.return_value.all.return_value = characters
    return result


async def test_character_alias_and_display_name_resolve_to_canonical_data():
    character = SimpleNamespace(
        id=uuid4(),
        name="李文渊",
        display_name="李医生",
        description="外科医生",
        data={"aliases": ["老李"], "profession": "doctor"},
    )
    db = AsyncMock()
    db.execute.return_value = _characters_result([character])
    store = BibleStore(db)

    characters = await store.get_characters(str(uuid4()), ["李医生", "老李"])
    single = await store.get_character(str(uuid4()), "老李")

    assert characters["李医生"]["profession"] == "doctor"
    assert characters["老李"]["profession"] == "doctor"
    assert single["name"] == "李文渊"

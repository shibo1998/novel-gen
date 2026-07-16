import pytest

from app.services.dho import DHOConflictError, DHOService


def test_dho_diff_reports_added_removed_and_modified_chapters():
    old = {"chapters": [{"number": 1, "title": "A"}, {"number": 2, "title": "B"}]}
    new = {"chapters": [{"number": 1, "title": "A"}, {"number": 2, "title": "B2"}, {"number": 3, "title": "C"}]}

    diff = DHOService.diff(old, new)

    assert [item["number"] for item in diff["chapters_added"]] == [3]
    assert diff["chapters_removed"] == []
    assert diff["chapters_modified"][0]["number"] == 2


def test_dho_rejects_changes_before_affected_boundary():
    old = {"chapters": [{"number": 1, "title": "locked"}, {"number": 2, "title": "future"}]}
    new = {"chapters": [{"number": 1, "title": "changed"}, {"number": 2, "title": "future-v2"}]}

    with pytest.raises(DHOConflictError, match="Written chapter 1"):
        DHOService._assert_written_chapters_unchanged(old, new, affected_from=2)


def test_dho_rejects_added_chapter_before_affected_boundary():
    old = {"chapters": [{"number": 2, "title": "future"}]}
    new = {"chapters": [{"number": 1, "title": "inserted"}, {"number": 2, "title": "future"}]}

    with pytest.raises(DHOConflictError, match="Written chapter 1"):
        DHOService._assert_written_chapters_unchanged(old, new, affected_from=2)


def test_dho_rejects_duplicate_candidate_chapter_numbers():
    candidate = {"chapters": [{"number": 2}, {"number": 2}]}

    with pytest.raises(DHOConflictError, match="unique"):
        DHOService._validate_candidate(candidate)


def test_dho_parses_fenced_json_candidate():
    parsed = DHOService._parse_json(
        '```json\n{"volumes": [], "chapters": [{"number": 2}], "foreshadowing_registry": []}\n```'
    )

    assert parsed["chapters"][0]["number"] == 2

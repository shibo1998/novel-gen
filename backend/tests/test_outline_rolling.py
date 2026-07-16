from types import SimpleNamespace

import pytest

from app.services.outline_rolling import (
    ChapterBatchPlan,
    OutlineBatchValidationError,
    OutlineStateError,
    allocate_chapter_ranges,
    select_next_batch,
    validate_generated_batch,
)


def test_allocate_chapter_ranges_covers_target_exactly():
    ranges = allocate_chapter_ranges(90, 4)

    assert [
        (item.volume_number, item.chapter_start, item.chapter_end)
        for item in ranges
    ] == [
        (1, 1, 23),
        (2, 24, 46),
        (3, 47, 68),
        (4, 69, 90),
    ]


def test_select_next_batch_rolls_by_five_and_crosses_volume_on_next_request():
    volumes = [
        SimpleNamespace(volume_number=1, chapter_start=1, chapter_end=7),
        SimpleNamespace(volume_number=2, chapter_start=8, chapter_end=12),
    ]

    first = select_next_batch(volumes, [])
    second = select_next_batch(
        volumes,
        [SimpleNamespace(volume_number=1, chapter_number=n) for n in range(1, 6)],
    )
    third = select_next_batch(
        volumes,
        [SimpleNamespace(volume_number=1, chapter_number=n) for n in range(1, 8)],
    )

    assert first == ChapterBatchPlan(1, 1, 5)
    assert second == ChapterBatchPlan(1, 6, 7)
    assert third == ChapterBatchPlan(2, 8, 12)


def test_select_next_batch_rejects_non_contiguous_state():
    volumes = [SimpleNamespace(volume_number=1, chapter_start=1, chapter_end=10)]
    chapters = [
        SimpleNamespace(volume_number=1, chapter_number=1),
        SimpleNamespace(volume_number=1, chapter_number=3),
    ]

    with pytest.raises(OutlineStateError, match="contiguous prefix"):
        select_next_batch(volumes, chapters)


def test_validate_generated_batch_requires_exact_range_and_volume():
    plan = ChapterBatchPlan(2, 24, 26)
    valid = {
        "chapters": [
            {"volume": 2, "number": 24},
            {"volume": 2, "number": 25},
            {"volume": 2, "number": 26},
        ]
    }
    assert validate_generated_batch(valid, plan) == valid["chapters"]

    with pytest.raises(OutlineBatchValidationError, match="Expected chapters"):
        validate_generated_batch(
            {"chapters": [{"volume": 2, "number": 24}, {"volume": 2, "number": 26}]},
            plan,
        )

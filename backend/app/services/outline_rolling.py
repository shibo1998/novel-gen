from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_CHAPTER_BATCH_SIZE = 5


class OutlineStateError(ValueError):
    """Persisted chapter state cannot be continued safely."""


class OutlineBatchValidationError(ValueError):
    """A generated chapter batch does not match its assigned contract."""


@dataclass(frozen=True)
class ChapterRange:
    volume_number: int
    chapter_start: int
    chapter_end: int

    @property
    def count(self) -> int:
        return self.chapter_end - self.chapter_start + 1


@dataclass(frozen=True)
class ChapterBatchPlan:
    volume_number: int
    chapter_start: int
    chapter_end: int

    @property
    def numbers(self) -> list[int]:
        return list(range(self.chapter_start, self.chapter_end + 1))


def allocate_chapter_ranges(total_chapters: int, volume_count: int) -> list[ChapterRange]:
    if total_chapters < 1:
        raise ValueError("total_chapters must be positive")
    if volume_count < 1:
        raise ValueError("volume_count must be positive")
    if volume_count > total_chapters:
        raise ValueError("volume_count cannot exceed total_chapters")

    base, remainder = divmod(total_chapters, volume_count)
    ranges: list[ChapterRange] = []
    chapter_start = 1
    for index in range(volume_count):
        count = base + (1 if index < remainder else 0)
        chapter_end = chapter_start + count - 1
        ranges.append(
            ChapterRange(
                volume_number=index + 1,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
            )
        )
        chapter_start = chapter_end + 1
    return ranges


def _value(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)


def select_next_batch(
    volumes: Sequence[Any],
    chapters: Iterable[Any],
    batch_size: int = DEFAULT_CHAPTER_BATCH_SIZE,
) -> ChapterBatchPlan | None:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    chapters_by_volume: dict[int, list[int]] = {}
    for chapter in chapters:
        volume_number = int(_value(chapter, "volume_number"))
        chapter_number = int(_value(chapter, "chapter_number"))
        chapters_by_volume.setdefault(volume_number, []).append(chapter_number)

    for volume in sorted(volumes, key=lambda item: int(_value(item, "volume_number"))):
        volume_number = int(_value(volume, "volume_number"))
        chapter_start = _value(volume, "chapter_start")
        chapter_end = _value(volume, "chapter_end")
        if chapter_start is None or chapter_end is None:
            raise OutlineStateError(f"Volume {volume_number} has no fixed chapter range")

        existing = sorted(chapters_by_volume.get(volume_number, []))
        expected_prefix = list(range(chapter_start, chapter_start + len(existing)))
        if existing != expected_prefix or (existing and existing[-1] > chapter_end):
            raise OutlineStateError(
                f"Volume {volume_number} chapters are not a contiguous prefix of "
                f"{chapter_start}-{chapter_end}"
            )

        next_start = chapter_start + len(existing)
        if next_start <= chapter_end:
            return ChapterBatchPlan(
                volume_number=volume_number,
                chapter_start=next_start,
                chapter_end=min(next_start + batch_size - 1, chapter_end),
            )

    return None


def validate_generated_batch(result: dict, plan: ChapterBatchPlan) -> list[dict]:
    chapters = result.get("chapters")
    if not isinstance(chapters, list):
        raise OutlineBatchValidationError("Generated result has no chapters list")

    numbers = [chapter.get("number") for chapter in chapters]
    if numbers != plan.numbers:
        raise OutlineBatchValidationError(
            f"Expected chapters {plan.chapter_start}-{plan.chapter_end}, got {numbers}"
        )

    wrong_volume = [
        chapter.get("number")
        for chapter in chapters
        if chapter.get("volume") != plan.volume_number
    ]
    if wrong_volume:
        raise OutlineBatchValidationError(
            f"Chapters {wrong_volume} do not belong to volume {plan.volume_number}"
        )
    return chapters

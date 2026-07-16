## Context

Reviewer already returns foreshadowing resolution IDs through a streamed structured response. The same response can carry entity deltas without adding another LLM call.

## Decisions

- Each change contains `entity_name`, `updates`, and `summary`.
- Only names included in `constraint.injected_bible` are accepted; unknown entities and empty/non-object updates are discarded.
- Only successful reviews apply changes, using `BibleVersionManager.apply_change()` in the scene transaction.
- Entity identity and core columns cannot be changed because updates are merged only into Bible snapshot data.

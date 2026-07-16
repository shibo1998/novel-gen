# outline-task-observability Specification

## Purpose
TBD - created by archiving change chapter-rolling-outline. Update Purpose after archive.
## Requirements
### Requirement: Outline tasks expose durable progress
The system SHALL persist task metadata containing the project ID, phase, human-readable message, completed chapter count, target chapter count, active volume, and active batch range.

#### Scenario: Skeleton generation is running
- **WHEN** the outline task is generating volume contracts
- **THEN** task polling reports phase `skeleton` and the project target chapter count

#### Scenario: Chapter batch is running
- **WHEN** the model is generating chapters 6 through 10 of volume 1
- **THEN** task polling reports phase `chapter_batch`, active volume 1, and batch range 6 through 10

### Requirement: Streaming LLM calls are bounded
The system MUST terminate a streaming LLM call after the configured timeout and mark its task failed with an actionable error.

#### Scenario: Provider stops producing data
- **WHEN** a streaming completion exceeds `llm_timeout_seconds`
- **THEN** the task becomes `failed` and its error states that the LLM timed out

### Requirement: Task IDs are isolated across concurrent jobs
The system MUST bind progress events to the task ID allocated for that coroutine without using mutable module-global task ID state.

#### Scenario: Two outline tasks overlap
- **WHEN** two projects start outline generation concurrently
- **THEN** each task's progress, completion, and failure metadata remains attached to its own task ID

### Requirement: Frontend displays task outcome
The frontend SHALL show current outline phase/progress while running and SHALL show the backend error when a task fails or is orphaned.

#### Scenario: Truncated model output
- **WHEN** polling returns `failed` with a max-token truncation error
- **THEN** the outline page stops its spinner and renders that error to the user

#### Scenario: Successful batch
- **WHEN** polling returns `completed`
- **THEN** the frontend reloads the outline and shows the next available chapter range action

### Requirement: Database schema matches runtime models
Migration 009 SHALL add missing `foreshadowings.status` storage idempotently and SHALL add JSON storage for volume contracts.

#### Scenario: Drifted database stamped at revision 008
- **WHEN** migration 009 runs against a database whose Alembic revision is 008 but whose `foreshadowings` table lacks `status`
- **THEN** the migration creates the column with default `pending` without losing existing rows

#### Scenario: Fresh database
- **WHEN** migration 009 runs against a database that already has `foreshadowings.status`
- **THEN** the migration completes without a duplicate-column failure


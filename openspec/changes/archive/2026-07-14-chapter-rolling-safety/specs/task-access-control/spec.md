## ADDED Requirements

### Requirement: Task polling verifies project ownership
The system MUST authenticate task polling and MUST return a project task only when the current user owns the task's project.

#### Scenario: Another user polls a task
- **WHEN** an authenticated user does not own the project in task metadata
- **THEN** the API returns HTTP 404 without exposing task status or errors

### Requirement: Orphaned tasks provide recovery guidance
The frontend SHALL explain whether an interrupted task should be regenerated or continued from persisted chapter state.

#### Scenario: Chapter batch interrupted after prior batches committed
- **WHEN** a chapter batch becomes orphaned
- **THEN** the UI states that saved chapters remain and offers the normal next-batch action


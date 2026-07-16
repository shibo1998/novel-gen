## Why

Post-implementation audit found that outline regeneration can delete existing work without honoring the request flag, concurrent initial tasks can overwrite each other, and task status endpoints do not consistently enforce project ownership.

## What Changes

- Make outline creation idempotent unless regeneration is explicitly requested.
- Refuse regeneration after chapter writing or scene creation has started.
- Allow only one active outline mutation task per project and operation class.
- Unify frontend polling on the authenticated `/api/tasks/{task_id}` endpoint.
- Validate task project ownership and give orphaned tasks an actionable recovery message.

## Capabilities

### New Capabilities

- `outline-regeneration-safety`: Explicit regeneration, written-content protection, and project-level active-task guards.
- `task-access-control`: Authenticated task polling with project ownership validation and recovery guidance.

### Modified Capabilities

None.

## Impact

Outline routes, worldbuilding task metadata, task manager lookup, task query APIs, frontend polling and outline controls.

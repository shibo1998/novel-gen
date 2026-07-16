## Context

The chapter rolling pipeline is functional, but its mutation and task-access boundaries need hardening before normal use.

## Goals / Non-Goals

**Goals:** Prevent accidental data loss, concurrent overwrite, and cross-project task disclosure.

**Non-Goals:** Add distributed locks, resumable Celery jobs, or automatic checkpoint replay.

## Decisions

- Existing outlines return 409 unless `regenerate=true`.
- Regeneration returns 409 if chapters contain written content or scenes exist.
- In-memory active-task guards reject duplicate outline generation/batch/append starts for the same project.
- Task metadata always includes project ID and kind for project mutations.
- `/api/tasks/{id}` requires authentication and verifies project ownership; frontend uses this path.
- Orphaned chapter batches guide users to continue from the next persisted range, while orphaned skeleton tasks guide regeneration.

## Risks / Trade-offs

- In-memory guards do not span multiple server instances → documented as a later distributed-queue concern.
- Old tasks without project metadata become unavailable through the secure endpoint → acceptable for expired diagnostic state.

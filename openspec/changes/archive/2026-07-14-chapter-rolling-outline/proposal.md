## Why

The outline pipeline is labelled as rolling planning but expands an entire volume in one LLM call. A 90-chapter project therefore requests roughly 23 detailed chapters at once, exceeds the 8,192-token output limit, and cannot complete; successful generations also fail to persist because the live database is missing a model-required column.

## What Changes

- Replace volume-sized detail generation with fixed five-chapter rolling batches.
- Persist a complete contract for every volume before generating chapter details, including its chapter range, conflict, character arc, opening state, ending state, and handoff hook.
- Allocate all chapter ranges once so they exactly cover the project's target chapter count without overlap or later growth.
- Add an API for planning the next chapter batch and retain the old volume-expansion endpoint as a compatibility wrapper.
- Add bounded LLM stream timeouts, task progress metadata, and user-visible failure messages.
- Repair the `foreshadowings.status` schema drift and add storage for volume contracts.
- Treat an ungenerated outline as an empty successful result while preserving 404 for a missing project.

## Capabilities

### New Capabilities

- `chapter-rolling-outline`: Complete volume contracts with chapter details generated and persisted in bounded sequential batches.
- `outline-task-observability`: Bounded execution, persisted phase/progress metadata, and actionable task failures.

### Modified Capabilities

None. This project has no existing OpenSpec capability documents.

## Impact

- Backend outline agents, prompts, route handlers, task status schemas, LLM streaming, SQLAlchemy models, and Alembic migrations.
- Frontend outline API bindings, types, polling behavior, error presentation, and outline controls.
- PostgreSQL schema and existing projects whose status says `outlined` but contain no volume/chapter rows.
- Existing `/volumes/expand/{vol_num}` clients remain supported, but the endpoint will generate only the next bounded chapter batch.

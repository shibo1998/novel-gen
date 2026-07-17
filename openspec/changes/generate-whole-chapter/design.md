## Context

The automatic chapter endpoint currently builds one enriched `SceneConstraint` per scene and invokes the scene coordinator in a loop. Each call owns its own prompt, review cycle, and length allowance. The final chapter is therefore assembled from independently generated prose, while `ChapterContentVersionService` creates intermediate versions during the loop.

Scene rows are also the current manual editing and activation surface. Removing them or introducing a new persistence model would require a database and frontend migration, so this change must separate generation boundaries from storage boundaries without removing scene compatibility.

## Goals / Non-Goals

**Goals:**

- Generate all planned scenes in one LLM drafting context under one 2500-character chapter budget.
- Review the complete chapter once per attempt and permit at most one repair attempt.
- Preserve ordered scene contracts as planning input and map the resulting prose back to existing scene rows.
- Create and evaluate one chapter content version after all scene updates are ready.
- Keep cost accounting, durable tasks, context snapshots, foreshadow resolution, and Bible updates working.

**Non-Goals:**

- Removing scene rows or the manual scene-writing endpoints.
- Changing the public task-oriented response of `write-chapter`.
- Guaranteeing an exact LLM character count without a repair pass.
- Adding a database migration or external dependency.

## Decisions

### Use one chapter writer call with hidden scene markers

The chapter writer receives every enriched scene contract in order and writes a continuous chapter. It emits `<!-- SCENE:n -->` boundary markers so the backend can map prose back to scene rows after the single call. Markers are removed before persistence.

This preserves the existing editing and version-activation model without asking the model to produce JSON or generating each scene independently. If markers are missing, duplicated, out of order, or delimit an empty scene, the result is a blocking format issue eligible for the single repair attempt.

Alternative considered: store the complete chapter only in `compiled_content`. Rejected for this change because the current writing UI and version activation restore scene contents.

### Treat scene budgets as manual-writing compatibility data

Automatic whole-chapter generation uses `CHAPTER_WORD_BUDGET` directly and ignores per-scene `word_budget`. Existing scene budget distribution remains available to manual scene generation, avoiding an unrelated schema migration.

Alternative considered: dynamically subtract prior scene output from later scene budgets. Rejected because it still restarts voice and context for every scene and pushes accumulated error into the final scene.

### Validate and repair at chapter level

The reviewer checks marker integrity, total prose characters, deterministic AI patterns, scene-contract coverage, continuity, and style against the complete chapter. The accepted range is 92%-108% of the configured chapter budget. An initial failure can trigger one full-chapter repair that receives the previous draft and concrete issues; there is no third drafting attempt.

Alternative considered: stop streaming at the character limit. Rejected because it can truncate a sentence or omit the chapter outcome.

### Persist only after the full result is ready

After parsing and review, the task transaction updates every scene, applies one shared chapter review result, creates one `ChapterContentVersion`, runs quality evaluation once, and records one durable draft attempt. No intermediate content version is created per scene.

### Reuse existing snapshots and observability

The endpoint continues to freeze context for each scene because retrieval can differ by scene. The ordered snapshot IDs form the chapter idempotency key. The chapter coordinator records writer and reviewer calls with a chapter event key and uses the existing budget guard.

## Risks / Trade-offs

- [The model omits scene markers] -> Treat marker integrity as blocking and use the one repair attempt; never persist ambiguous segmentation.
- [A full-chapter repair changes correct prose] -> Include the prior draft, preserve scene outcomes, and limit repairs to one pass with concrete issues.
- [Chapter prompts become large] -> Deduplicate shared context in the template and keep scene contracts compact; 2500-character output remains within existing model limits.
- [Scene review metadata becomes less granular] -> Store the chapter review result on each scene with the same chapter-level verdict; detailed per-scene review can remain a future diagnostic feature.
- [Existing completed tasks prevent intentional regeneration] -> Preserve current idempotency semantics; explicit force-regeneration remains out of scope.

## Migration Plan

1. Deploy the chapter writer, reviewer, parser, and tests.
2. Switch only the automatic `write-chapter` background task to the new coordinator.
3. Keep manual streaming and `write-auto` scene endpoints unchanged.
4. Roll back by restoring the previous per-scene loop; no persisted schema requires reversal.

## Open Questions

None for the initial implementation.

## Context

The current pipeline creates a compact whole-book skeleton, then asks one model call for every detailed chapter in the first volume. For a 90-chapter project and the recommended four volumes, that call targets 23 chapters with 3-5 events and 1-3 foreshadowing seeds per chapter. The resulting JSON exceeds the configured 8,192 output tokens. Later volume expansion also divides the total chapter count by remaining volume count instead of dividing remaining chapters, causing requested output to grow toward the final volume.

The live database is stamped at Alembic revision 008 but lacks `foreshadowings.status`, which runtime models and migration history assume exists. Task progress uses a module-global task ID and the polling schema discards task metadata. Streaming completions have no whole-stream timeout.

## Goals / Non-Goals

**Goals:**

- Make volume structure complete before prose-level chapter planning begins.
- Limit every chapter-detail model response to five exact chapters.
- Preserve sequential continuity and exact project chapter totals.
- Make tasks bounded, isolated, observable, and recoverable after partial progress.
- Repair the live schema without deleting user data.

**Non-Goals:**

- Generate chapter prose as part of outline planning.
- Replace the in-process task manager with a distributed queue.
- Automatically merge or rewrite existing user-edited chapter outlines.
- Remove the legacy volume expansion endpoint in this change.

## Decisions

### Persist volume contracts before chapter batches

The skeleton agent will output `opening_state`, `ending_state`, `handoff_hook`, and narrative constraints in addition to existing fields. The backend will allocate exact chapter ranges deterministically and store the full contract in `volumes.contract` JSON.

This keeps each volume complete even when only its first few chapters have details. Storing only a richer free-text summary was rejected because later batches need stable, machine-addressable anchors.

### Allocate exact chapter ranges once

For `T` target chapters and `N` volumes, each volume receives `T // N` chapters and the first `T % N` volumes receive one extra. Ranges are persisted and never recalculated from the number of remaining volumes.

Dynamic redistribution was rejected because it makes later batches unstable and can invalidate previously generated chapter numbers.

### Generate five chapters per batch

A shared batch service selects the earliest incomplete volume, computes the next missing contiguous range capped at five, renders only the active contract plus recent chapter context, validates the response, and commits the batch atomically.

Increasing `max_tokens` was rejected as the primary fix because output size still grows with volume size and provider limits vary. One chapter per call was rejected because it multiplies latency and cost without improving contract consistency enough to justify it.

### Separate skeleton and batch transactions

The new skeleton is generated before replacing existing rows. Once valid, all volume contracts and global foreshadowings are committed. The first chapter batch runs in a second transaction. If it fails, the complete skeleton remains available and the user can retry the next batch.

### Preserve legacy API compatibility

`POST /outline/expand-next` becomes the canonical endpoint. `POST /volumes/expand/{vol_num}` delegates to the same service and rejects out-of-order volume requests with HTTP 409. Existing response fields remain present.

### Bind task identity through a coroutine factory

Task creation will accept a factory receiving the allocated task ID. Outline jobs use that ID for progress updates, eliminating `_current_task_id` races. Task metadata is persisted on each phase transition and included in the API schema.

### Bound the complete stream

Each provider's entire streaming iteration is wrapped in `asyncio.timeout(settings.llm_timeout_seconds)`. Provider timeouts are translated into `LLMTimeoutError`; partial output is discarded and never parsed or persisted.

## Risks / Trade-offs

- [More LLM calls per novel] → Five-chapter batches add round trips but keep each call bounded and retryable.
- [Skeleton succeeds but first batch fails] → Persisted contracts allow retry without regenerating the whole book.
- [Model returns structurally valid but wrong chapter numbers] → Exact range validation rejects the full batch before commit.
- [Existing partial outlines conflict with new contracts] → Explicit regeneration replaces them; ordinary expansion continues from persisted ranges.
- [Migration history is unreliable] → Migration 009 uses PostgreSQL catalog checks and direct post-migration schema verification.

## Migration Plan

1. Back up schema metadata and inspect existing rows without mutation.
2. Apply migration 009 to add `foreshadowings.status` if absent and `volumes.contract` if absent.
3. Deploy backend model/API changes and verify health, task polling, and empty outline reads.
4. Deploy frontend changes.
5. Regenerate the affected project's outline, which safely replaces its stale `outlined` state with volume contracts and the first batch.

Rollback removes only `volumes.contract`; `foreshadowings.status` is retained during downgrade if it contains user state, avoiding destructive data loss.

## Open Questions

None blocking. Batch size is fixed at five for this change and can become configurable after production measurements.

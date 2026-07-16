## Context

Write-time embedding marks failures with `index_status=failed`. A manual backfill script exists, but runtime compensation is absent.

## Decisions

- Claim a small batch with `FOR UPDATE SKIP LOCKED` so concurrent workers do not process the same records.
- Embed the batch in one provider call and commit each claimed batch atomically.
- Run compensation in a lifespan-owned asyncio task. Provider failures are logged and retried on the next interval.
- Keep the manual backfill script for operator-driven bulk repair.

## Risks / Trade-offs

- Row locks are held during the embedding request, bounded by the configured small batch and provider timeout.
- Automatic retries add background provider load, controlled by batch and interval settings.

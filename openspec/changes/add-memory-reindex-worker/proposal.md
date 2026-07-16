## Why

Memory records degrade safely when embedding fails, but the documented `reindex_pending()` compensation and background worker do not exist. Failed records remain permanently unavailable to semantic recall unless an operator runs a script.

## What Changes

- Add bounded, concurrency-safe reindexing for unindexed memory records.
- Start a configurable periodic compensation worker with the application lifespan.
- Cancel the worker cleanly during shutdown and keep embedding outages non-fatal.

## Capabilities

### New Capabilities

- `memory-reindex`: Automatically retries failed semantic-memory indexing.

## Impact

Memory record storage, application lifespan, configuration, and unit tests are affected. No schema migration is required.

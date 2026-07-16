## Why

Generation failures currently persist and return raw exception text through task APIs and SSE events. Provider, database, and filesystem details can therefore leak to authenticated clients.

## What Changes

- Persist stable public task error codes and messages instead of exception text.
- Return sanitized errors from live tasks, durable task queries, and writing streams.
- Keep the original exception and traceback in server logs.
- Sanitize legacy durable task rows at the API boundary.

## Capabilities

### New Capabilities

- `task-error-safety`: Defines the public task failure contract across polling and streaming APIs.

## Impact

Task execution, durable task persistence, task status APIs, writing streams, and their regression tests are affected. No database migration is required.

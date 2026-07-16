## Why

`get_db` already owns request commit/rollback, but CRUD routes also commit internally. A later exception can therefore leave partial changes committed despite the request failing.

## What Changes

- Remove explicit commits from ordinary request-scoped CRUD and version routes.
- Use flush/refresh only when generated values are needed before response serialization.
- Retain explicit commits that publish state to background tasks or persist streaming checkpoints.

## Capabilities

### New Capabilities

- `request-transactions`: Defines one atomic transaction per ordinary API request.

## Impact

Authentication, projects, characters, versions, styles, reviews, plot threads, and outline revision routes are affected. No migration is required.

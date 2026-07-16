## Why

The temporal Story Bible can version entity state, but chapter generation never calls it. Character injuries, possessions, relationships, and other durable changes therefore disappear from future context unless edited manually.

## What Changes

- Extend the existing streamed Reviewer result with structured entity changes.
- Whitelist changes to entity names present in the scene's injected Bible context.
- Apply approved changes in the same transaction as scene confirmation.

## Capabilities

### New Capabilities

- `bible-chapter-events`: Persists reviewed chapter events into temporal Bible versions.

## Impact

Reviewer prompt/result validation, writing coordination, Bible persistence, and tests are affected. No additional model request or migration is required.

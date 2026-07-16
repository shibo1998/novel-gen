## Why

Budget checks read historical spend and then allow a call. Concurrent calls can all pass before any metric is written, exceeding chapter or project limits.

## What Changes

- Add persistent expiring cost reservations.
- Serialize reservation decisions per project and include active reservations in limits.
- Settle reservations with actual observed cost; abandoned reservations expire automatically.

## Capabilities

### New Capabilities

- `cost-reservations`: Atomically reserves LLM budget before provider calls.

## Impact

Database schema, budget/observability services, configuration, and tests are affected.

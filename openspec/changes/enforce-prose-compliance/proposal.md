## Why

Compliance scanning protects worldbuilding output but not persisted prose. Generated or manually saved scenes can be marked confirmed while containing blocked real-world terms.

## What Changes

- Centralize prose compliance evaluation and scene confirmation status.
- Apply the gate to manual, automatic, chapter, recovery, and review paths.
- Persist compliance issues in scene review metadata and return them to clients.

## Capabilities

### New Capabilities

- `prose-compliance`: Prevents non-compliant prose from entering confirmed state.

## Impact

Writing and recovery flows, scene review metadata, and tests are affected. No migration is required.

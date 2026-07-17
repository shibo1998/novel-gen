## Why

Automatic chapter writing currently invokes the LLM once per scene, so each scene can overshoot its local allowance, repeat setup, and restart narrative voice. The accumulated result can exceed the fixed chapter budget while still passing scene-level checks, and the independently generated prose weakens transitions across the chapter.

## What Changes

- Keep scene contracts as ordered planning metadata, but stop using them as independent automatic generation units.
- Add a chapter writer that receives all scene contracts and produces one continuous chapter in a single LLM call.
- Enforce one chapter-level character budget and run review against the complete chapter.
- Allow at most one targeted chapter repair for length or blocking prose issues.
- Persist the generated prose as one atomic chapter content version after chapter-level validation.
- Preserve the existing manual scene-writing endpoint and scene planning UI.

## Capabilities

### New Capabilities

- `whole-chapter-generation`: Generate, validate, repair, and persist a complete chapter from ordered scene contracts under one chapter-level budget.

### Modified Capabilities

None.

## Impact

- Backend writing agents, prompts, chapter generation orchestration, quality checks, and content-version persistence.
- The existing automatic `write-chapter` task changes from repeated scene calls to one chapter call without changing its task-oriented public entry contract.
- No database migration or new external dependency is required; scene rows remain the planning source and manual editing surface.

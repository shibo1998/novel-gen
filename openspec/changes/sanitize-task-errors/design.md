## Context

The application has both an in-memory task manager and durable generation tasks. Both currently retain raw exception strings, while several APIs return those values unchanged.

## Goals / Non-Goals

**Goals:**

- Use one stable public failure code and message across task transports.
- Preserve detailed diagnostics in server logs.
- Prevent old persisted exception text from leaking.

**Non-Goals:**

- A user-facing error taxonomy, observability backend migration, or database schema change.

## Decisions

- `TASK_EXECUTION_FAILED` is the stable code and `Task execution failed. Please retry.` is the public message.
- Failure state stores only the public contract. The exception type, message, and traceback are logged server-side.
- API serialization derives the public message from task status rather than trusting persisted text.
- Interruption/orphan messages remain distinct because they describe recoverability and contain no internal detail.

## Risks / Trade-offs

- Less detail is visible in the UI. Operators use correlated task IDs and server logs for diagnosis.

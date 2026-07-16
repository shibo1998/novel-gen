from typing import Any

TASK_EXECUTION_FAILED = "TASK_EXECUTION_FAILED"
TASK_INTERRUPTED = "TASK_INTERRUPTED"

PUBLIC_TASK_ERROR = "Task execution failed. Please retry."
PUBLIC_TASK_INTERRUPTED = "Task was interrupted and may be recovered."


def public_error_for_status(status: Any) -> str | None:
    value = getattr(status, "value", status)
    if value == "failed":
        return PUBLIC_TASK_ERROR
    if value in ("interrupted", "orphaned"):
        return PUBLIC_TASK_INTERRUPTED
    return None


def public_error_code_for_status(status: Any) -> str | None:
    value = getattr(status, "value", status)
    if value == "failed":
        return TASK_EXECUTION_FAILED
    if value in ("interrupted", "orphaned"):
        return TASK_INTERRUPTED
    return None

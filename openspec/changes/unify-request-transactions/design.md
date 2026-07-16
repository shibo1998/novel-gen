## Decisions

- `get_db` is the sole commit/rollback owner for normal request work.
- Routes may flush to obtain IDs and refresh ORM objects without committing.
- Writing streams and task launch routes retain explicit commits where another session/process must observe state before the request ends.

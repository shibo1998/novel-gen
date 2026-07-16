"""Shared primitives for immutable snapshot version services."""

import hashlib
import json

from sqlalchemy import func, select


class VersionedSnapshot:
    @staticmethod
    def digest(snapshot: dict | list) -> str:
        raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    async def next_number(db, model, scope_column, scope_id) -> int:
        current = (
            await db.execute(
                select(func.coalesce(func.max(model.version_number), 0)).where(
                    scope_column == scope_id
                )
            )
        ).scalar_one()
        return current + 1

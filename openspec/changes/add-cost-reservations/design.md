## Decisions

- Take a transaction-level PostgreSQL advisory lock derived from the project UUID while calculating spent plus active reserved cost. This serializes reservations without conflicting with business transactions that hold foreign-key locks on the project row.
- Store reservation identity in a ContextVar so existing Agent call signatures stay unchanged.
- Settle with actual cost for successful and failed provider calls; stale reservations stop counting after TTL.
- Observability and reservations remain in independent transactions so business rollback cannot erase spend controls.

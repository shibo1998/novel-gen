## 1. Database and Contracts

- [x] 1.1 Add idempotent Alembic migration 009 for `foreshadowings.status` and `volumes.contract`
- [x] 1.2 Update SQLAlchemy and API/frontend volume schemas for contract and partial planning state
- [x] 1.3 Add deterministic exact chapter-range allocation with unit tests

## 2. Chapter Batch Generation

- [x] 2.1 Extend the skeleton schema and prompt with complete volume contract fields
- [x] 2.2 Add the five-chapter batch prompt, agent, exact-range validation, and tests
- [x] 2.3 Persist skeleton/contracts separately from chapter batches
- [x] 2.4 Implement next-batch selection and atomic persistence across volume boundaries
- [x] 2.5 Add canonical next-batch API and make legacy volume expansion a compatibility wrapper
- [x] 2.6 Update append-volume generation to create a contract and at most one chapter batch

## 3. Task Reliability and Observability

- [x] 3.1 Replace the module-global task ID with task-bound coroutine factories
- [x] 3.2 Add persisted task phase/progress metadata to backend and frontend schemas
- [x] 3.3 Add whole-stream LLM timeout handling and regression tests

## 4. Frontend Chapter Rolling

- [x] 4.1 Add next-batch API binding and chapter/volume progress types
- [x] 4.2 Replace per-volume expansion controls with a sequential “plan next five chapters” action
- [x] 4.3 Display task phase, chapter counts, and backend failures on the outline page

## 5. Verification

- [x] 5.1 Run strict OpenSpec validation, backend tests/Ruff, and frontend lint/build
- [x] 5.2 Apply migration 009 and verify live PostgreSQL columns and revision
- [x] 5.3 Regenerate the current 90-chapter project and verify skeleton plus two chapter batches

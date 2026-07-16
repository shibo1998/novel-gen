## ADDED Requirements

### Requirement: Atomic LLM cost reservation
The system SHALL atomically reserve estimated cost before starting a project-scoped LLM call and SHALL include active reservations in chapter and project limits.

#### Scenario: Concurrent calls approach the limit
- **WHEN** one call has reserved the remaining budget
- **THEN** another call is rejected even before the first metric is settled

#### Scenario: Call completes
- **WHEN** a provider call records actual token usage
- **THEN** its reservation is settled with actual cost in the same observability transaction

#### Scenario: Process dies after reservation
- **WHEN** no metric settles a reservation before its TTL
- **THEN** the stale reservation no longer counts against future calls
